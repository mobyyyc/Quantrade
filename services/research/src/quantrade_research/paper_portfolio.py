"""Persist a private research-only portfolio at the first open after a score run."""

from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal
from pathlib import Path

from .config import Settings
from .quality import DataQualityError
from .rebalance import NextOpenPrice, PortfolioState, build_next_open_rebalance_ledger
from .score_run import _dotenv_values


DEFAULT_STARTING_NAV = Decimal("100000")


def _settings(env_file: Path) -> Settings:
    import os
    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def publish_paper_portfolio(*, settings: Settings, score_date: date, starting_nav: Decimal = DEFAULT_STARTING_NAV) -> int:
    """Create one immutable paper-portfolio run from eligible dated score snapshots."""
    settings.require_runtime_storage()
    assert settings.database_url is not None
    if starting_nav <= 0:
        raise DataQualityError("paper portfolio starting NAV must be positive")
    import psycopg
    with psycopg.connect(settings.database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM quantrade.paper_portfolio_runs WHERE score_date = %s", (score_date,))
        if cursor.fetchone() is not None:
            raise DataQualityError(f"paper portfolio already exists for {score_date}")
        cursor.execute(
            """SELECT security_id::text FROM quantrade.score_snapshots
               WHERE score_date = %s AND eligible
               ORDER BY rank ASC LIMIT 20""",
            (score_date,),
        )
        target_ids = [row[0] for row in cursor.fetchall()]
        if len(target_ids) != 20:
            raise DataQualityError(f"paper portfolio requires 20 eligible scores; found {len(target_ids)}")
        cursor.execute(
            """SELECT MIN(session_date) FROM quantrade.daily_price_bars
               WHERE security_id = ANY(%s::uuid[]) AND session = 'regular' AND session_date > %s""",
            (target_ids, score_date),
        )
        execution_date = cursor.fetchone()[0]
        if execution_date is None:
            raise DataQualityError("next regular-session open is not available yet")
        cursor.execute(
            """SELECT security_id::text, session_date, open_price
               FROM quantrade.daily_price_bars
               WHERE security_id = ANY(%s::uuid[]) AND session_date = %s
                 AND session = 'regular' AND adjustment_basis = 'unadjusted'""",
            (target_ids, execution_date),
        )
        opens = [NextOpenPrice(*row) for row in cursor.fetchall()]
        from .rebalance import RebalanceTarget
        weight = Decimal("1") / Decimal(len(target_ids))
        ledger = build_next_open_rebalance_ledger(
            PortfolioState(starting_nav, ()), [RebalanceTarget(item, weight) for item in target_ids], opens,
            formation_date=score_date, execution_date=execution_date,
        )
        cursor.execute(
            """INSERT INTO quantrade.paper_portfolio_runs
               (score_date, execution_date, starting_nav, ending_cash, benchmark_ticker)
               VALUES (%s, %s, %s, %s, 'SPY') RETURNING paper_portfolio_run_id""",
            (score_date, execution_date, ledger.starting_nav, ledger.ending_cash),
        )
        run_id = cursor.fetchone()[0]
        for position in ledger.positions:
            cursor.execute("INSERT INTO quantrade.paper_portfolio_positions VALUES (%s, %s, %s)", (run_id, position.security_id, position.quantity))
        for trade in ledger.trades:
            cursor.execute(
                "INSERT INTO quantrade.paper_portfolio_trades VALUES (%s, %s, %s, %s, %s, %s)",
                (run_id, trade.security_id, trade.side, trade.quantity, trade.execution_price, trade.notional),
            )
        connection.commit()
    return len(ledger.positions)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish a private next-open paper portfolio")
    parser.add_argument("--score-date", type=date.fromisoformat, required=True)
    parser.add_argument("--starting-nav", type=Decimal, default=DEFAULT_STARTING_NAV)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()
    positions = publish_paper_portfolio(settings=_settings(args.env_file), score_date=args.score_date, starting_nav=args.starting_nav)
    print(f"paper_portfolio_positions={positions}")


if __name__ == "__main__":
    main()
