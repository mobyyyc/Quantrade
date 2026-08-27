"""Materialize conservative, immutable forward paper-portfolio checkpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .config import Settings
from .quality import DataQualityError


CHECKPOINT_HORIZONS = (5, 20, 60)


@dataclass(frozen=True, slots=True)
class PaperPortfolioPosition:
    security_id: str
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class PaperPortfolioOutcome:
    paper_portfolio_run_id: str
    horizon_sessions: int
    status: str
    outcome_date: date
    portfolio_return: Decimal | None = None
    benchmark_return: Decimal | None = None
    benchmark_relative_return: Decimal | None = None
    unavailable_reason: str | None = None


def calculate_paper_portfolio_return(
    *,
    starting_nav: Decimal,
    ending_cash: Decimal,
    positions: tuple[PaperPortfolioPosition, ...],
    closing_prices: dict[str, Decimal],
) -> Decimal:
    """Return the mark-to-market return, rejecting incomplete or invalid marks."""
    if starting_nav <= 0:
        raise DataQualityError("paper portfolio starting NAV must be positive")
    if ending_cash < 0:
        raise DataQualityError("paper portfolio ending cash cannot be negative")
    if not positions:
        raise DataQualityError("paper portfolio requires at least one position")
    security_ids = [position.security_id for position in positions]
    if len(set(security_ids)) != len(security_ids):
        raise DataQualityError("paper portfolio positions must be unique")
    if any(position.quantity <= 0 for position in positions):
        raise DataQualityError("paper portfolio quantities must be positive")
    missing = sorted(set(security_ids) - closing_prices.keys())
    if missing:
        raise DataQualityError(f"missing closing prices for: {', '.join(missing)}")
    if any(closing_prices[security_id] <= 0 for security_id in security_ids):
        raise DataQualityError("paper portfolio closing prices must be positive")
    ending_nav = ending_cash + sum(
        (position.quantity * closing_prices[position.security_id] for position in positions),
        Decimal("0"),
    )
    return ending_nav / starting_nav - Decimal("1")


def _withheld(run_id: str, horizon: int, outcome_date: date, reason: str) -> PaperPortfolioOutcome:
    return PaperPortfolioOutcome(run_id, horizon, "withheld", outcome_date, unavailable_reason=reason)


def materialize_due_paper_portfolio_outcomes(
    *, settings: Settings, as_of_date: date
) -> tuple[PaperPortfolioOutcome, ...]:
    """Write checkpoints only on their real 5th, 20th, or 60th benchmark session.

    A horizon counts the execution session as session one. Raw prices are used
    consistently with the raw next-open trades. An action on a held name causes
    a withheld checkpoint until the project has explicit position accounting for
    that action; it never becomes a silently adjusted performance claim.
    """
    settings.require_runtime_storage()
    assert settings.database_url is not None
    import psycopg

    materialized: list[PaperPortfolioOutcome] = []
    with psycopg.connect(settings.database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT paper_portfolio_run_id::text, execution_date, starting_nav, ending_cash, benchmark_ticker
               FROM quantrade.paper_portfolio_runs
               WHERE execution_date <= %s
                 AND formation_protocol = 'monthly_last_session_next_open_v1'
               ORDER BY execution_date ASC""",
            (as_of_date,),
        )
        runs = cursor.fetchall()
        for run_id, execution_date, starting_nav, ending_cash, benchmark_ticker in runs:
            cursor.execute(
                "SELECT horizon_sessions FROM quantrade.paper_portfolio_outcomes WHERE paper_portfolio_run_id = %s",
                (run_id,),
            )
            completed_horizons = {int(row[0]) for row in cursor.fetchall()}
            for horizon in CHECKPOINT_HORIZONS:
                if horizon in completed_horizons:
                    continue
                cursor.execute(
                    """SELECT session_date
                       FROM quantrade.benchmark_daily_price_bars
                       WHERE benchmark_ticker = %s
                         AND session = 'regular'
                         AND adjustment_basis = 'unadjusted'
                         AND session_date >= %s
                         AND session_date <= %s
                       ORDER BY session_date ASC
                       OFFSET %s LIMIT 1""",
                    (benchmark_ticker, execution_date, as_of_date, horizon - 1),
                )
                target_row = cursor.fetchone()
                if target_row is None:
                    continue
                outcome_date = target_row[0]
                cursor.execute(
                    """SELECT session_date, open_price, close_price
                       FROM quantrade.benchmark_daily_price_bars
                       WHERE benchmark_ticker = %s
                         AND session = 'regular'
                         AND adjustment_basis = 'unadjusted'
                         AND session_date IN (%s, %s)""",
                    (benchmark_ticker, execution_date, outcome_date),
                )
                benchmark_marks = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
                execution_mark = benchmark_marks.get(execution_date)
                closing_mark = benchmark_marks.get(outcome_date)
                if execution_mark is None or closing_mark is None or execution_mark[0] <= 0 or closing_mark[1] <= 0:
                    outcome = _withheld(str(run_id), horizon, outcome_date, "benchmark price unavailable for the checkpoint")
                else:
                    cursor.execute(
                        """SELECT security_id::text, quantity
                           FROM quantrade.paper_portfolio_positions
                           WHERE paper_portfolio_run_id = %s
                           ORDER BY security_id""",
                        (run_id,),
                    )
                    positions = tuple(PaperPortfolioPosition(str(row[0]), row[1]) for row in cursor.fetchall())
                    security_ids = [position.security_id for position in positions]
                    cursor.execute(
                        """SELECT COUNT(*)
                           FROM quantrade.corporate_actions
                           WHERE security_id = ANY(%s::uuid[])
                             AND COALESCE(effective_date, process_date) >= %s
                             AND COALESCE(effective_date, process_date) <= %s""",
                        (security_ids, execution_date, outcome_date),
                    )
                    action_count = int(cursor.fetchone()[0])
                    if action_count:
                        outcome = _withheld(str(run_id), horizon, outcome_date, "a held company had a corporate action; adjusted position accounting is required")
                    else:
                        cursor.execute(
                            """SELECT security_id::text, close_price
                               FROM quantrade.daily_price_bars
                               WHERE security_id = ANY(%s::uuid[])
                                 AND session_date = %s
                                 AND session = 'regular'
                                 AND adjustment_basis = 'unadjusted'""",
                            (security_ids, outcome_date),
                        )
                        closes = {str(row[0]): row[1] for row in cursor.fetchall()}
                        try:
                            portfolio_return = calculate_paper_portfolio_return(
                                starting_nav=starting_nav,
                                ending_cash=ending_cash,
                                positions=positions,
                                closing_prices=closes,
                            )
                        except DataQualityError:
                            outcome = _withheld(str(run_id), horizon, outcome_date, "one or more held-company closing prices are unavailable")
                        else:
                            benchmark_return = closing_mark[1] / execution_mark[0] - Decimal("1")
                            outcome = PaperPortfolioOutcome(
                                str(run_id), horizon, "completed", outcome_date,
                                portfolio_return, benchmark_return, portfolio_return - benchmark_return,
                            )
                cursor.execute(
                    """INSERT INTO quantrade.paper_portfolio_outcomes
                       (paper_portfolio_run_id, horizon_sessions, status, outcome_date,
                        portfolio_return, benchmark_return, benchmark_relative_return, unavailable_reason)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        outcome.paper_portfolio_run_id, outcome.horizon_sessions, outcome.status,
                        outcome.outcome_date, outcome.portfolio_return, outcome.benchmark_return,
                        outcome.benchmark_relative_return, outcome.unavailable_reason,
                    ),
                )
                materialized.append(outcome)
        connection.commit()
    return tuple(materialized)
