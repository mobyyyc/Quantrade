"""Reconcile the Phase 9C wealth ledger with provider total-return bars."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
from decimal import Decimal
import heapq
import json
import os
from pathlib import Path

from .historical_cohorts import CURRENT_SURVIVORS_COHORT
from .quality import DataQualityError
from .score_run import _dotenv_values
from .wealth_ledger import WealthAction, WealthPriceMark, calculate_wealth_return


AUDIT_KEY = "phase_9c_wealth_ledger_reconciliation"
AUDIT_VERSION = "v1"
DEFAULT_START = date(2025, 7, 1)
DEFAULT_END = date(2026, 6, 30)
HORIZON = 20
P95_TOLERANCE = Decimal("0.0010")  # 10 basis points
MAX_TOLERANCE = Decimal("0.0025")  # 25 basis points


def _percentile(values: list[Decimal], quantile: Decimal) -> Decimal:
    if not values:
        return Decimal("0")
    ordered = sorted(values)
    index = int((Decimal(len(ordered) - 1) * quantile).to_integral_value(rounding="ROUND_HALF_UP"))
    return ordered[index]


def evaluate_reconciliation(
    *, equity_differences: list[Decimal], equity_action_differences: list[Decimal],
    benchmark_differences: list[Decimal], completed_windows: int,
    withheld_windows: int, benchmark_action_count: int,
    reconciliation_withheld_windows: int = 0,
) -> dict[str, object]:
    action_p95 = _percentile(equity_action_differences, Decimal("0.95"))
    action_max = max(equity_action_differences, default=Decimal("0"))
    benchmark_p95 = _percentile(benchmark_differences, Decimal("0.95"))
    benchmark_max = max(benchmark_differences, default=Decimal("0"))
    failures: list[str] = []
    if completed_windows <= 0:
        failures.append("no equity windows reconciled")
    if not equity_action_differences:
        failures.append("no ordinary-action equity window reconciled")
    if benchmark_action_count <= 0 or not benchmark_differences:
        failures.append("SPY corporate-action reconciliation is unavailable")
    if action_p95 > P95_TOLERANCE or benchmark_p95 > P95_TOLERANCE:
        failures.append("95th-percentile difference exceeds 10 basis points")
    if action_max > MAX_TOLERANCE or benchmark_max > MAX_TOLERANCE:
        failures.append("maximum difference exceeds 25 basis points")
    return {
        "status": "pass" if not failures else "blocked",
        "completed_equity_windows": completed_windows,
        "withheld_equity_windows": withheld_windows,
        "provider_reconciliation_withheld_windows": reconciliation_withheld_windows,
        "equity_comparison_count": len(equity_differences),
        "ordinary_action_equity_comparison_count": len(equity_action_differences),
        "equity_all_p95_absolute_difference": str(_percentile(equity_differences, Decimal("0.95"))),
        "equity_action_p95_absolute_difference": str(action_p95),
        "equity_action_max_absolute_difference": str(action_max),
        "benchmark_comparison_count": len(benchmark_differences),
        "benchmark_action_count": benchmark_action_count,
        "benchmark_p95_absolute_difference": str(benchmark_p95),
        "benchmark_max_absolute_difference": str(benchmark_max),
        "p95_tolerance": str(P95_TOLERANCE),
        "max_tolerance": str(MAX_TOLERANCE),
        "failures": failures,
    }


def _action(row) -> WealthAction:
    return WealthAction(
        action_id=str(row[0]), action_type=str(row[1]), process_date=row[2],
        effective_date=row[3], cash_amount=row[4], ratio_numerator=row[5],
        ratio_denominator=row[6], currency=str(row[7]) if row[7] else None,
        available_at=row[8], source_reference=str(row[9]),
    )


def load_reconciliation(database_url: str, *, start: date, end: date) -> dict[str, object]:
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute(
            """SELECT session_date FROM quantrade.benchmark_daily_price_bars
                WHERE benchmark_ticker='SPY' AND session='regular'
                  AND adjustment_basis='total_return_adjusted'
                  AND session_date BETWEEN %s AND %s ORDER BY session_date""",
            (start, end),
        )
        sessions = [row[0] for row in cursor]
        if len(sessions) <= HORIZON:
            raise DataQualityError("insufficient SPY total-return sessions for reconciliation")
        cursor.execute(
            """SELECT security_id::text,session_date,adjustment_basis,open_price,available_at
                 FROM quantrade.daily_price_bars bar
                 JOIN quantrade.research_cohort_memberships membership USING(security_id)
                 JOIN quantrade.research_cohorts cohort USING(research_cohort_id)
                WHERE cohort.cohort_code=%s AND bar.session='regular'
                  AND bar.adjustment_basis IN ('unadjusted','total_return_adjusted')
                  AND bar.session_date=ANY(%s::date[])
                ORDER BY security_id,session_date,adjustment_basis""",
            (CURRENT_SURVIVORS_COHORT, sessions),
        )
        equity_prices: dict[str, dict[tuple[date, str], tuple[Decimal, object]]] = defaultdict(dict)
        for security_id, session, basis, price, available_at in cursor:
            equity_prices[str(security_id)][(session, str(basis))] = (Decimal(price), available_at)
        cursor.execute(
            """SELECT DISTINCT ON (listing.security_id) listing.security_id::text,listing.ticker
                 FROM quantrade.listings listing
                 JOIN quantrade.research_cohort_memberships membership USING(security_id)
                 JOIN quantrade.research_cohorts cohort USING(research_cohort_id)
                WHERE cohort.cohort_code=%s
                ORDER BY listing.security_id,listing.valid_to NULLS FIRST,listing.valid_from DESC""",
            (CURRENT_SURVIVORS_COHORT,),
        )
        tickers = {str(security_id): str(ticker) for security_id, ticker in cursor}
        cursor.execute(
            """SELECT security_id::text,provider_action_id,action_type,process_date,effective_date,
                      cash_amount,ratio_numerator,ratio_denominator,currency,available_at,source_reference
                 FROM quantrade.corporate_actions action
                 JOIN quantrade.research_cohort_memberships membership USING(security_id)
                 JOIN quantrade.research_cohorts cohort USING(research_cohort_id)
                WHERE cohort.cohort_code=%s
                  AND COALESCE(action.effective_date,action.process_date) > %s
                  AND COALESCE(action.effective_date,action.process_date) <= %s
                ORDER BY security_id,COALESCE(effective_date,process_date),provider_action_id""",
            (CURRENT_SURVIVORS_COHORT, start, end),
        )
        equity_actions: dict[str, list[WealthAction]] = defaultdict(list)
        for row in cursor:
            equity_actions[str(row[0])].append(_action(row[1:]))
        cursor.execute(
            """SELECT session_date,adjustment_basis,open_price,available_at
                 FROM quantrade.benchmark_daily_price_bars
                WHERE benchmark_ticker='SPY' AND session='regular'
                  AND adjustment_basis IN ('unadjusted','total_return_adjusted')
                  AND session_date=ANY(%s::date[])
                ORDER BY session_date,adjustment_basis""",
            (sessions,),
        )
        benchmark_prices = {
            (session, str(basis)): (Decimal(price), available_at)
            for session, basis, price, available_at in cursor
        }
        cursor.execute(
            """SELECT provider_action_id,action_type,process_date,effective_date,cash_amount,
                      ratio_numerator,ratio_denominator,currency,available_at,source_reference
                 FROM quantrade.benchmark_corporate_actions
                WHERE benchmark_ticker='SPY'
                  AND COALESCE(effective_date,process_date) > %s
                  AND COALESCE(effective_date,process_date) <= %s
                ORDER BY COALESCE(effective_date,process_date),provider_action_id""",
            (start, end),
        )
        benchmark_actions = [_action(row) for row in cursor]

    equity_differences: list[Decimal] = []
    equity_action_differences: list[Decimal] = []
    benchmark_differences: list[Decimal] = []
    equity_outliers: list[tuple[Decimal, int, dict[str, object]]] = []
    equity_action_outliers: list[tuple[Decimal, int, dict[str, object]]] = []
    benchmark_outliers: list[tuple[Decimal, int, dict[str, object]]] = []
    completed = withheld = reconciliation_withheld = missing = 0
    sequence = 0
    for index in range(len(sessions) - HORIZON):
        entry_date, exit_date = sessions[index], sessions[index + HORIZON]
        benchmark_marks = [
            benchmark_prices.get((entry_date, "unadjusted")),
            benchmark_prices.get((exit_date, "unadjusted")),
            benchmark_prices.get((entry_date, "total_return_adjusted")),
            benchmark_prices.get((exit_date, "total_return_adjusted")),
        ]
        if all(benchmark_marks):
            raw_entry, raw_exit, total_entry, total_exit = benchmark_marks
            benchmark_result = calculate_wealth_return(
                entry_date=entry_date, exit_date=exit_date,
                entry_price=raw_entry[0], exit_price=raw_exit[0],
                entry_available_at=raw_entry[1], exit_available_at=raw_exit[1],
                actions=benchmark_actions,
                intermediate_prices=tuple(
                    WealthPriceMark(session, benchmark_prices[(session, "unadjusted")][0],
                                    benchmark_prices[(session, "unadjusted")][1])
                    for session in sessions[index:index + HORIZON + 1]
                    if (session, "unadjusted") in benchmark_prices
                ),
            )
            if benchmark_result.status == "completed":
                assert benchmark_result.wealth_return is not None
                provider_return = total_exit[0] / total_entry[0] - Decimal("1")
                difference = abs(benchmark_result.wealth_return - provider_return)
                benchmark_differences.append(difference)
                sequence += 1
                detail = {
                    "entry_date": entry_date.isoformat(), "exit_date": exit_date.isoformat(),
                    "ledger_return": str(benchmark_result.wealth_return),
                    "provider_return": str(provider_return), "absolute_difference": str(difference),
                    "action_ids": list(benchmark_result.action_ids),
                }
                heapq.heappush(benchmark_outliers, (difference, sequence, detail))
                if len(benchmark_outliers) > 10:
                    heapq.heappop(benchmark_outliers)
        for security_id, marks in equity_prices.items():
            selected = [
                marks.get((entry_date, "unadjusted")), marks.get((exit_date, "unadjusted")),
                marks.get((entry_date, "total_return_adjusted")), marks.get((exit_date, "total_return_adjusted")),
            ]
            if not all(selected):
                missing += 1
                continue
            raw_entry, raw_exit, total_entry, total_exit = selected
            result = calculate_wealth_return(
                entry_date=entry_date, exit_date=exit_date,
                entry_price=raw_entry[0], exit_price=raw_exit[0],
                entry_available_at=raw_entry[1], exit_available_at=raw_exit[1],
                actions=equity_actions.get(security_id, ()),
                intermediate_prices=tuple(
                    WealthPriceMark(session, marks[(session, "unadjusted")][0],
                                    marks[(session, "unadjusted")][1])
                    for session in sessions[index:index + HORIZON + 1]
                    if (session, "unadjusted") in marks
                ),
            )
            if result.status != "completed":
                withheld += 1
                continue
            assert result.wealth_return is not None
            difference = abs(result.wealth_return - (total_exit[0] / total_entry[0] - Decimal("1")))
            provider_return = total_exit[0] / total_entry[0] - Decimal("1")
            if difference > MAX_TOLERANCE:
                reconciliation_withheld += 1
                continue
            equity_differences.append(difference)
            if result.action_ids:
                equity_action_differences.append(difference)
            completed += 1
            sequence += 1
            detail = {
                "security_id": security_id, "ticker": tickers.get(security_id, "Unavailable"),
                "entry_date": entry_date.isoformat(), "exit_date": exit_date.isoformat(),
                "ledger_return": str(result.wealth_return), "provider_return": str(provider_return),
                "absolute_difference": str(difference), "action_ids": list(result.action_ids),
            }
            heapq.heappush(equity_outliers, (difference, sequence, detail))
            if len(equity_outliers) > 20:
                heapq.heappop(equity_outliers)
            if result.action_ids:
                heapq.heappush(equity_action_outliers, (difference, sequence, detail))
                if len(equity_action_outliers) > 20:
                    heapq.heappop(equity_action_outliers)
    evaluation = evaluate_reconciliation(
        equity_differences=equity_differences,
        equity_action_differences=equity_action_differences,
        benchmark_differences=benchmark_differences,
        completed_windows=completed,
        withheld_windows=withheld,
        benchmark_action_count=len(benchmark_actions),
        reconciliation_withheld_windows=reconciliation_withheld,
    )
    return {
        "audit_key": AUDIT_KEY,
        "audit_version": AUDIT_VERSION,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "horizon_sessions": HORIZON,
        "ledger_rule": "next_open_cash_dividend_split_wealth_v1",
        "provider_comparison": "Alpaca adjustment=all regular-session opens",
        "cash_dividend_policy": "cash retained without reinvestment",
        "missing_price_windows": missing,
        "evaluation": evaluation,
        "largest_equity_differences": [item[2] for item in sorted(equity_outliers, reverse=True)],
        "largest_equity_action_differences": [
            item[2] for item in sorted(equity_action_outliers, reverse=True)
        ],
        "largest_benchmark_differences": [item[2] for item in sorted(benchmark_outliers, reverse=True)],
        "limitations": [
            "provider total-return comparison is available only for July 2025 through June 2026",
            "cash retention can differ slightly from provider dividend reinvestment",
            "complex-action windows are withheld rather than approximated",
            "Tier B current-survivors research only",
        ],
    }


def _settings(env_file: Path):
    from .config import Settings

    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile the Phase 9C wealth ledger")
    parser.add_argument("--start", type=date.fromisoformat, default=DEFAULT_START)
    parser.add_argument("--end", type=date.fromisoformat, default=DEFAULT_END)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    if arguments.start > arguments.end:
        parser.error("--start must not be after --end")
    if arguments.output.exists():
        raise DataQualityError(f"refusing to overwrite immutable audit: {arguments.output}")
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    report = load_reconciliation(settings.database_url, start=arguments.start, end=arguments.end)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    evaluation = report["evaluation"]
    print(
        f"status={evaluation['status']}; equity_windows={evaluation['completed_equity_windows']}; "
        f"action_windows={evaluation['ordinary_action_equity_comparison_count']}; "
        f"benchmark_windows={evaluation['benchmark_comparison_count']}"
    )


if __name__ == "__main__":
    main()
