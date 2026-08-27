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
MONTHLY_FORMATION_PROTOCOL = "monthly_last_session_next_open_v1"


def _settings(env_file: Path) -> Settings:
    import os
    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def is_monthly_formation(formation_date: date, next_session_date: date) -> bool:
    """Return whether the next market session begins a new calendar month."""
    return (formation_date.year, formation_date.month) != (
        next_session_date.year,
        next_session_date.month,
    )


def publish_paper_portfolio(*, settings: Settings, score_date: date, starting_nav: Decimal = DEFAULT_STARTING_NAV) -> int:
    """Create one immutable monthly portfolio from the active model's dated scores."""
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
            "SELECT model_version FROM quantrade.model_deployments ORDER BY deployed_at DESC LIMIT 1"
        )
        model_row = cursor.fetchone()
        if model_row is None:
            raise DataQualityError("paper portfolio requires an active model deployment")
        model_version = str(model_row[0])
        cursor.execute(
            """SELECT snapshot.security_id::text FROM quantrade.score_snapshots snapshot
               JOIN quantrade.daily_research_runs run
                 ON run.score_date = snapshot.score_date
                AND run.decision_at = snapshot.decision_at
                AND run.status = 'completed'
               WHERE snapshot.score_date = %s
                 AND snapshot.model_version = %s
                 AND snapshot.eligible
               ORDER BY snapshot.rank ASC LIMIT 20""",
            (score_date, model_version),
        )
        target_ids = [row[0] for row in cursor.fetchall()]
        if len(target_ids) != 20:
            raise DataQualityError(f"paper portfolio requires 20 eligible scores; found {len(target_ids)}")
        cursor.execute(
            """SELECT session_date
               FROM quantrade.benchmark_daily_price_bars
               WHERE benchmark_ticker = 'SPY'
                 AND session = 'regular'
                 AND adjustment_basis = 'unadjusted'
                 AND session_date > %s
               ORDER BY session_date ASC
               LIMIT 1""",
            (score_date,),
        )
        execution_row = cursor.fetchone()
        execution_date = execution_row[0] if execution_row is not None else None
        if execution_date is None:
            raise DataQualityError("next regular-session open is not available yet")
        if not is_monthly_formation(score_date, execution_date):
            raise DataQualityError("paper portfolio formation must be the final market session of a calendar month")
        cursor.execute(
            """SELECT security_id::text, session_date, open_price
               FROM quantrade.daily_price_bars
               WHERE security_id = ANY(%s::uuid[]) AND session_date = %s
                 AND session = 'regular' AND adjustment_basis = 'unadjusted'""",
            (target_ids, execution_date),
        )
        opens = [NextOpenPrice(*row) for row in cursor.fetchall()]
        if len(opens) != len(target_ids):
            raise DataQualityError("one or more next-open prices are unavailable for the monthly portfolio")
        from .rebalance import RebalanceTarget
        weight = Decimal("1") / Decimal(len(target_ids))
        ledger = build_next_open_rebalance_ledger(
            PortfolioState(starting_nav, ()), [RebalanceTarget(item, weight) for item in target_ids], opens,
            formation_date=score_date, execution_date=execution_date,
        )
        cursor.execute(
            """INSERT INTO quantrade.paper_portfolio_runs
               (score_date, execution_date, starting_nav, ending_cash, benchmark_ticker,
                model_version, formation_protocol)
               VALUES (%s, %s, %s, %s, 'SPY', %s, %s) RETURNING paper_portfolio_run_id""",
            (score_date, execution_date, ledger.starting_nav, ledger.ending_cash,
             model_version, MONTHLY_FORMATION_PROTOCOL),
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


def publish_due_paper_portfolios(*, settings: Settings, execution_date: date) -> tuple[date, ...]:
    """Publish the prior month's final score run only at its next market open.

    This intentionally does not backfill missed runs. A forward paper record is
    useful only when it is established at the next available market open.
    """
    settings.require_runtime_storage()
    assert settings.database_url is not None
    import psycopg
    with psycopg.connect(settings.database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """WITH active_model AS (
                 SELECT model_version
                 FROM quantrade.model_deployments
                 ORDER BY deployed_at DESC
                 LIMIT 1
               )
               SELECT s.score_date
               FROM quantrade.score_snapshots s
               CROSS JOIN active_model active
               JOIN quantrade.daily_research_runs run
                 ON run.score_date = s.score_date
                AND run.decision_at = s.decision_at
                AND run.status = 'completed'
               WHERE s.score_date < %s
                 AND s.model_version = active.model_version
                 AND s.eligible
                 AND s.score_date = (
                   SELECT MAX(bar.session_date)
                   FROM quantrade.benchmark_daily_price_bars bar
                   WHERE bar.benchmark_ticker = 'SPY'
                     AND bar.session = 'regular'
                     AND bar.adjustment_basis = 'unadjusted'
                     AND bar.session_date < %s
                     AND date_trunc('month', bar.session_date) = date_trunc('month', s.score_date)
                 )
                 AND NOT EXISTS (
                   SELECT 1
                   FROM quantrade.paper_portfolio_runs p
                   WHERE p.score_date = s.score_date
                     AND p.formation_protocol = %s
                 )
               GROUP BY s.score_date
               HAVING COUNT(*) >= 20
               ORDER BY s.score_date ASC""",
            (execution_date, execution_date, MONTHLY_FORMATION_PROTOCOL),
        )
        candidates = [row[0] for row in cursor.fetchall()]
        due_dates: list[date] = []
        for score_date in candidates:
            cursor.execute(
                """SELECT session_date
                   FROM quantrade.benchmark_daily_price_bars
                   WHERE benchmark_ticker = 'SPY'
                     AND session = 'regular'
                     AND adjustment_basis = 'unadjusted'
                     AND session_date > %s
                   ORDER BY session_date ASC
                   LIMIT 1""",
                (score_date,),
            )
            next_open_row = cursor.fetchone()
            next_open = next_open_row[0] if next_open_row is not None else None
            if next_open == execution_date:
                due_dates.append(score_date)
    published: list[date] = []
    for score_date in due_dates:
        publish_paper_portfolio(settings=settings, score_date=score_date)
        published.append(score_date)
    return tuple(published)


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
