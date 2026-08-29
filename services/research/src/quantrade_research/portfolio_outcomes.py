"""Materialize conservative, immutable forward paper-portfolio checkpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json

from .config import Settings
from .quality import DataQualityError
from .wealth_ledger import (
    PAPER_PORTFOLIO_LEDGER_RULE,
    WealthAction,
    WealthPriceMark,
    calculate_wealth_return,
)


CHECKPOINT_HORIZONS = (5, 20, 60)
RECONCILIATION_TOLERANCE = Decimal("0.0025")


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
    accounting_rule: str | None = None
    portfolio_ledger_sha256: str | None = None
    benchmark_ledger_sha256: str | None = None
    corporate_action_count: int | None = None
    data_cutoff_at: datetime | None = None


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


def _wealth_action(row) -> WealthAction:
    return WealthAction(
        action_id=str(row[0]), action_type=str(row[1]), process_date=row[2],
        effective_date=row[3], cash_amount=row[4], ratio_numerator=row[5],
        ratio_denominator=row[6], currency=str(row[7]) if row[7] else None,
        available_at=row[8], source_reference=str(row[9]),
    )


def _portfolio_digest(items: list[tuple[str, str, str]], ending_cash: Decimal) -> str:
    payload = {"positions": sorted(items), "ending_cash": str(ending_cash), "rule": PAPER_PORTFOLIO_LEDGER_RULE}
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def materialize_due_paper_portfolio_outcomes(
    *, settings: Settings, as_of_date: date
) -> tuple[PaperPortfolioOutcome, ...]:
    """Write checkpoints only on their real 5th, 20th, or 60th benchmark session.

    A horizon counts the execution session as session one. Raw entry-open and
    checkpoint-close prices are reconciled through explicit split and cash-
    dividend ledgers for both holdings and SPY. Complex or incomplete actions
    fail closed instead of being silently adjusted.
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
                    """SELECT session_date, open_price, close_price, available_at
                       FROM quantrade.benchmark_daily_price_bars
                       WHERE benchmark_ticker = %s
                         AND session = 'regular'
                         AND adjustment_basis = 'unadjusted'
                         AND session_date IN (%s, %s)""",
                    (benchmark_ticker, execution_date, outcome_date),
                )
                benchmark_marks = {row[0]: (row[1], row[2], row[3]) for row in cursor.fetchall()}
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
                        """SELECT security_id::text, session_date, open_price, close_price, available_at
                           FROM quantrade.daily_price_bars
                           WHERE security_id = ANY(%s::uuid[])
                             AND session_date BETWEEN %s AND %s
                             AND session = 'regular' AND adjustment_basis = 'unadjusted'
                           ORDER BY security_id, session_date""",
                        (security_ids, execution_date, outcome_date),
                    )
                    price_paths: dict[str, dict[date, tuple[Decimal, Decimal, datetime]]] = {}
                    for security_id, session_date, open_price, close_price, available_at in cursor:
                        price_paths.setdefault(str(security_id), {})[session_date] = (
                            open_price, close_price, available_at,
                        )
                    cursor.execute(
                        """SELECT security_id::text, session_date, open_price, close_price
                           FROM quantrade.daily_price_bars
                           WHERE security_id = ANY(%s::uuid[])
                             AND session_date IN (%s, %s)
                             AND session = 'regular' AND adjustment_basis = 'total_return_adjusted'""",
                        (security_ids, execution_date, outcome_date),
                    )
                    total_return_marks = {
                        (str(row[0]), row[1]): (row[2], row[3]) for row in cursor
                    }
                    cursor.execute(
                        """SELECT security_id::text, provider_action_id, action_type, process_date,
                                  effective_date, cash_amount, ratio_numerator, ratio_denominator,
                                  currency, available_at, source_reference
                           FROM quantrade.corporate_actions
                           WHERE security_id = ANY(%s::uuid[])
                             AND COALESCE(effective_date, process_date) > %s
                             AND COALESCE(effective_date, process_date) <= %s
                           ORDER BY security_id, COALESCE(effective_date, process_date), provider_action_id""",
                        (security_ids, execution_date, outcome_date),
                    )
                    actions_by_security: dict[str, list[WealthAction]] = {}
                    for row in cursor:
                        actions_by_security.setdefault(str(row[0]), []).append(_wealth_action(row[1:]))
                    cursor.execute(
                        """SELECT provider_action_id, action_type, process_date, effective_date,
                                  cash_amount, ratio_numerator, ratio_denominator, currency,
                                  available_at, source_reference
                           FROM quantrade.benchmark_corporate_actions
                           WHERE benchmark_ticker = %s
                             AND COALESCE(effective_date, process_date) > %s
                             AND COALESCE(effective_date, process_date) <= %s
                           ORDER BY COALESCE(effective_date, process_date), provider_action_id""",
                        (benchmark_ticker, execution_date, outcome_date),
                    )
                    benchmark_actions = [_wealth_action(row) for row in cursor]
                    cursor.execute(
                        """SELECT session_date, open_price, available_at
                           FROM quantrade.benchmark_daily_price_bars
                           WHERE benchmark_ticker = %s AND session = 'regular'
                             AND adjustment_basis = 'unadjusted'
                             AND session_date BETWEEN %s AND %s ORDER BY session_date""",
                        (benchmark_ticker, execution_date, outcome_date),
                    )
                    benchmark_path = tuple(WealthPriceMark(row[0], row[1], row[2]) for row in cursor)
                    expected_sessions = {mark.session_date for mark in benchmark_path}
                    cursor.execute(
                        """SELECT session_date, open_price, close_price
                           FROM quantrade.benchmark_daily_price_bars
                           WHERE benchmark_ticker = %s AND session = 'regular'
                             AND adjustment_basis = 'total_return_adjusted'
                             AND session_date IN (%s, %s)""",
                        (benchmark_ticker, execution_date, outcome_date),
                    )
                    benchmark_total_marks = {row[0]: (row[1], row[2]) for row in cursor}
                    benchmark_ledger = calculate_wealth_return(
                        entry_date=execution_date, exit_date=outcome_date,
                        entry_price=execution_mark[0], exit_price=closing_mark[1],
                        entry_available_at=execution_mark[2], exit_available_at=closing_mark[2],
                        actions=benchmark_actions, intermediate_prices=benchmark_path,
                        ledger_rule=PAPER_PORTFOLIO_LEDGER_RULE,
                    )
                    ledgers = []
                    ending_nav = ending_cash
                    failure = benchmark_ledger.unavailable_reason if benchmark_ledger.status != "completed" else None
                    benchmark_total_entry = benchmark_total_marks.get(execution_date)
                    benchmark_total_exit = benchmark_total_marks.get(outcome_date)
                    if not failure and (benchmark_total_entry is None or benchmark_total_exit is None):
                        failure = "benchmark total-return reconciliation marks are unavailable"
                    if not failure:
                        assert benchmark_ledger.wealth_return is not None
                        provider_benchmark_return = (
                            benchmark_total_exit[1] / benchmark_total_entry[0] - Decimal("1")
                        )
                        if abs(benchmark_ledger.wealth_return - provider_benchmark_return) > RECONCILIATION_TOLERANCE:
                            failure = "benchmark wealth ledger failed provider reconciliation"
                    for position in positions:
                        marks = price_paths.get(position.security_id, {})
                        entry = marks.get(execution_date)
                        exit_mark = marks.get(outcome_date)
                        if entry is None or exit_mark is None or set(marks) != expected_sessions:
                            failure = "one or more held-company price paths are unavailable"
                            break
                        ledger = calculate_wealth_return(
                            entry_date=execution_date, exit_date=outcome_date,
                            entry_price=entry[0], exit_price=exit_mark[1],
                            entry_available_at=entry[2], exit_available_at=exit_mark[2],
                            actions=actions_by_security.get(position.security_id, ()),
                            intermediate_prices=tuple(
                                WealthPriceMark(session, mark[0], mark[2])
                                for session, mark in sorted(marks.items())
                            ),
                            ledger_rule=PAPER_PORTFOLIO_LEDGER_RULE,
                        )
                        ledgers.append((position, ledger))
                        if ledger.status != "completed":
                            failure = ledger.unavailable_reason
                            break
                        total_entry = total_return_marks.get((position.security_id, execution_date))
                        total_exit = total_return_marks.get((position.security_id, outcome_date))
                        if total_entry is None or total_exit is None:
                            failure = "one or more held-company reconciliation marks are unavailable"
                            break
                        assert ledger.wealth_return is not None
                        provider_return = total_exit[1] / total_entry[0] - Decimal("1")
                        if abs(ledger.wealth_return - provider_return) > RECONCILIATION_TOLERANCE:
                            failure = "one or more held-company wealth ledgers failed provider reconciliation"
                            break
                        assert ledger.ending_quantity is not None and ledger.cash_distributions is not None
                        ending_nav += position.quantity * (
                            ledger.ending_quantity * exit_mark[1] + ledger.cash_distributions
                        )
                    if failure:
                        outcome = _withheld(str(run_id), horizon, outcome_date, failure)
                    else:
                        assert benchmark_ledger.wealth_return is not None
                        portfolio_return = ending_nav / starting_nav - Decimal("1")
                        digest_items = [
                            (position.security_id, str(position.quantity), ledger.digest)
                            for position, ledger in ledgers
                        ]
                        cutoff = max(
                            benchmark_ledger.data_cutoff_at,
                            *(ledger.data_cutoff_at for _, ledger in ledgers),
                        )
                        action_count = len(benchmark_ledger.action_ids) + sum(
                            len(ledger.action_ids) for _, ledger in ledgers
                        )
                        outcome = PaperPortfolioOutcome(
                            str(run_id), horizon, "completed", outcome_date,
                            portfolio_return, benchmark_ledger.wealth_return,
                            portfolio_return - benchmark_ledger.wealth_return, None,
                            PAPER_PORTFOLIO_LEDGER_RULE,
                            _portfolio_digest(digest_items, ending_cash), benchmark_ledger.digest,
                            action_count, cutoff,
                        )
                cursor.execute(
                    """INSERT INTO quantrade.paper_portfolio_outcomes
                       (paper_portfolio_run_id, horizon_sessions, status, outcome_date,
                        portfolio_return, benchmark_return, benchmark_relative_return, unavailable_reason,
                        accounting_rule, portfolio_ledger_sha256, benchmark_ledger_sha256,
                        corporate_action_count, data_cutoff_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        outcome.paper_portfolio_run_id, outcome.horizon_sessions, outcome.status,
                        outcome.outcome_date, outcome.portfolio_return, outcome.benchmark_return,
                        outcome.benchmark_relative_return, outcome.unavailable_reason,
                        outcome.accounting_rule, outcome.portfolio_ledger_sha256,
                        outcome.benchmark_ledger_sha256, outcome.corporate_action_count,
                        outcome.data_cutoff_at,
                    ),
                )
                materialized.append(outcome)
        connection.commit()
    return tuple(materialized)
