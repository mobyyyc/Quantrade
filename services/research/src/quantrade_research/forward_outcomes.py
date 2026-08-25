"""Persist future-only stock-score labels for eventual ML training."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from .config import Settings
from .quality import DataQualityError


LABEL_HORIZONS = (5, 20, 60)
SPLIT_ADJUSTED = "split_adjusted"


@dataclass(frozen=True, slots=True)
class ForwardScoreOutcome:
    score_snapshot_id: str
    horizon_sessions: int
    status: str
    execution_date: date
    outcome_date: date
    security_entry_price: Decimal | None = None
    security_exit_price: Decimal | None = None
    benchmark_entry_price: Decimal | None = None
    benchmark_exit_price: Decimal | None = None
    security_return: Decimal | None = None
    benchmark_return: Decimal | None = None
    benchmark_relative_return: Decimal | None = None
    data_cutoff_at: datetime | None = None
    unavailable_reason: str | None = None


def calculate_forward_returns(
    *, security_entry_price: Decimal, security_exit_price: Decimal,
    benchmark_entry_price: Decimal, benchmark_exit_price: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    """Calculate a split-adjusted price-return label and its SPY-relative value."""
    values = (security_entry_price, security_exit_price, benchmark_entry_price, benchmark_exit_price)
    if any(value <= 0 for value in values):
        raise DataQualityError("forward outcome prices must be positive")
    security_return = security_exit_price / security_entry_price - Decimal("1")
    benchmark_return = benchmark_exit_price / benchmark_entry_price - Decimal("1")
    return security_return, benchmark_return, security_return - benchmark_return


def _withheld(
    score_snapshot_id: str, horizon: int, execution_date: date, outcome_date: date, reason: str,
) -> ForwardScoreOutcome:
    return ForwardScoreOutcome(
        score_snapshot_id, horizon, "withheld", execution_date, outcome_date,
        unavailable_reason=reason,
    )


def materialize_due_forward_score_outcomes(
    *, settings: Settings, as_of_date: date, benchmark_ticker: str = "SPY",
) -> tuple[ForwardScoreOutcome, ...]:
    """Write labels only when their future benchmark session has actually closed.

    A label begins at the close of the first regular SPY session after the score
    date (the execution session) and ends at the close of its 5th, 20th, or
    60th session. It deliberately uses split-adjusted *price* returns, not a
    total-return proxy. Missing future data becomes an immutable withheld label
    rather than a shifted window or imputed training example.
    """
    settings.require_runtime_storage()
    assert settings.database_url is not None
    import psycopg

    materialized: list[ForwardScoreOutcome] = []
    with psycopg.connect(settings.database_url) as connection, connection.cursor() as cursor:
        for horizon in LABEL_HORIZONS:
            cursor.execute(
                """SELECT ss.score_snapshot_id::text, ss.security_id::text, ss.score_date
                   FROM quantrade.score_snapshots ss
                   JOIN quantrade.daily_research_runs run
                     ON run.score_date = ss.score_date
                    AND run.decision_at = ss.decision_at
                    AND run.status = 'completed'
                   WHERE ss.eligible
                     AND ss.score_date < %s
                     AND NOT EXISTS (
                       SELECT 1 FROM quantrade.forward_score_outcomes outcome
                       WHERE outcome.score_snapshot_id = ss.score_snapshot_id
                         AND outcome.horizon_sessions = %s
                     )
                     AND (
                       SELECT COUNT(*) FROM quantrade.benchmark_daily_price_bars benchmark
                       WHERE benchmark.benchmark_ticker = %s
                         AND benchmark.session = 'regular'
                         AND benchmark.adjustment_basis = %s
                         AND benchmark.session_date > ss.score_date
                         AND benchmark.session_date <= %s
                     ) >= %s
                   ORDER BY ss.score_date ASC, ss.security_id ASC""",
                (as_of_date, horizon, benchmark_ticker, SPLIT_ADJUSTED, as_of_date, horizon),
            )
            candidates = cursor.fetchall()
            for score_snapshot_id, security_id, score_date in candidates:
                cursor.execute(
                    """SELECT session_date
                       FROM quantrade.benchmark_daily_price_bars
                       WHERE benchmark_ticker = %s
                         AND session = 'regular'
                         AND adjustment_basis = %s
                         AND session_date > %s
                         AND session_date <= %s
                       ORDER BY session_date ASC
                       LIMIT 1""",
                    (benchmark_ticker, SPLIT_ADJUSTED, score_date, as_of_date),
                )
                execution_date = cursor.fetchone()[0]
                cursor.execute(
                    """SELECT session_date
                       FROM quantrade.benchmark_daily_price_bars
                       WHERE benchmark_ticker = %s
                         AND session = 'regular'
                         AND adjustment_basis = %s
                         AND session_date > %s
                         AND session_date <= %s
                       ORDER BY session_date ASC
                       OFFSET %s LIMIT 1""",
                    (benchmark_ticker, SPLIT_ADJUSTED, score_date, as_of_date, horizon - 1),
                )
                outcome_date = cursor.fetchone()[0]
                cursor.execute(
                    """SELECT session_date, close_price, available_at
                       FROM quantrade.daily_price_bars
                       WHERE security_id = %s
                         AND session = 'regular'
                         AND adjustment_basis = %s
                         AND session_date IN (%s, %s)""",
                    (security_id, SPLIT_ADJUSTED, execution_date, outcome_date),
                )
                security_prices = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
                cursor.execute(
                    """SELECT session_date, close_price, available_at
                       FROM quantrade.benchmark_daily_price_bars
                       WHERE benchmark_ticker = %s
                         AND session = 'regular'
                         AND adjustment_basis = %s
                         AND session_date IN (%s, %s)""",
                    (benchmark_ticker, SPLIT_ADJUSTED, execution_date, outcome_date),
                )
                benchmark_prices = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
                security_start = security_prices.get(execution_date)
                security_end = security_prices.get(outcome_date)
                benchmark_start = benchmark_prices.get(execution_date)
                benchmark_end = benchmark_prices.get(outcome_date)
                if not all((security_start, security_end, benchmark_start, benchmark_end)):
                    outcome = _withheld(
                        str(score_snapshot_id), horizon, execution_date, outcome_date,
                        "split-adjusted price data is unavailable for the fixed forward window",
                    )
                else:
                    assert security_start and security_end and benchmark_start and benchmark_end
                    try:
                        security_return, benchmark_return, relative_return = calculate_forward_returns(
                            security_entry_price=security_start[0], security_exit_price=security_end[0],
                            benchmark_entry_price=benchmark_start[0], benchmark_exit_price=benchmark_end[0],
                        )
                    except DataQualityError:
                        outcome = _withheld(
                            str(score_snapshot_id), horizon, execution_date, outcome_date,
                            "split-adjusted price data contains a non-positive mark",
                        )
                    else:
                        outcome = ForwardScoreOutcome(
                            str(score_snapshot_id), horizon, "completed", execution_date, outcome_date,
                            security_start[0], security_end[0], benchmark_start[0], benchmark_end[0],
                            security_return, benchmark_return, relative_return,
                            max(security_start[1], security_end[1], benchmark_start[1], benchmark_end[1]),
                        )
                cursor.execute(
                    """INSERT INTO quantrade.forward_score_outcomes
                       (score_snapshot_id, horizon_sessions, status, execution_date, outcome_date,
                        adjustment_basis, security_entry_price, security_exit_price,
                        benchmark_entry_price, benchmark_exit_price, security_return,
                        benchmark_return, benchmark_relative_return, data_cutoff_at, unavailable_reason)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        outcome.score_snapshot_id, outcome.horizon_sessions, outcome.status,
                        outcome.execution_date, outcome.outcome_date, SPLIT_ADJUSTED,
                        outcome.security_entry_price, outcome.security_exit_price,
                        outcome.benchmark_entry_price, outcome.benchmark_exit_price,
                        outcome.security_return, outcome.benchmark_return,
                        outcome.benchmark_relative_return, outcome.data_cutoff_at,
                        outcome.unavailable_reason,
                    ),
                )
                materialized.append(outcome)
        connection.commit()
    return tuple(materialized)
