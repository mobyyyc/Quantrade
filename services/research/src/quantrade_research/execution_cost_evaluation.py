"""Frozen-selection, next-open portfolio and cost evaluation primitives.

This module never ranks securities. It accepts the selection manifest produced
by ``holdout_evaluation`` plus one explicit set of entry/exit prices, so the
eventual database adapter cannot tune a basket after results are visible.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from typing import Iterable, Mapping

from .holdout_evaluation import PORTFOLIO_SIZE, require_locked_holdout_confirmation
from .quality import DataQualityError


COST_CASES_BPS = (Decimal("1"), Decimal("5"), Decimal("10"), Decimal("20"))


@dataclass(frozen=True, slots=True)
class ExecutionPeriod:
    formation_date: date
    execution_date: date
    exit_date: date
    entry_prices: Mapping[str, Decimal]
    exit_prices: Mapping[str, Decimal]
    benchmark_entry_price: Decimal
    benchmark_exit_price: Decimal
    corporate_action_security_ids: frozenset[str] = frozenset()


def _return_before_costs(security_ids: Iterable[str], period: ExecutionPeriod) -> Decimal:
    selected = tuple(security_ids)
    if len(selected) != PORTFOLIO_SIZE or len(set(selected)) != PORTFOLIO_SIZE:
        raise DataQualityError(f"portfolio requires exactly {PORTFOLIO_SIZE} unique frozen selections")
    affected = sorted(set(selected) & period.corporate_action_security_ids)
    if affected:
        raise DataQualityError(
            "held corporate action requires position accounting: " + ", ".join(affected)
        )
    missing_entry = sorted(security_id for security_id in selected if security_id not in period.entry_prices)
    missing_exit = sorted(security_id for security_id in selected if security_id not in period.exit_prices)
    if missing_entry or missing_exit:
        raise DataQualityError(
            "missing frozen selection price marks: " + ", ".join(missing_entry + missing_exit)
        )
    ratios: list[Decimal] = []
    for security_id in selected:
        entry = period.entry_prices[security_id]
        exit_price = period.exit_prices[security_id]
        if entry <= 0 or exit_price <= 0:
            raise DataQualityError(f"non-positive next-open price for {security_id}")
        ratios.append(exit_price / entry)
    return sum(ratios, Decimal("0")) / Decimal(PORTFOLIO_SIZE) - Decimal("1")


def cost_adjusted_return(gross_return: Decimal, one_way_cost_bps: Decimal) -> Decimal:
    """Apply equal entry and exit costs to a fully rebalanced, all-cash portfolio."""
    if one_way_cost_bps < 0:
        raise DataQualityError("one-way cost cannot be negative")
    cost = one_way_cost_bps / Decimal("10000")
    return (Decimal("1") + gross_return) * (Decimal("1") - cost) ** 2 - Decimal("1")


def benchmark_return(period: ExecutionPeriod) -> Decimal:
    if period.benchmark_entry_price <= 0 or period.benchmark_exit_price <= 0:
        raise DataQualityError("benchmark next-open prices must be positive")
    return period.benchmark_exit_price / period.benchmark_entry_price - Decimal("1")


def evaluate_period(*, baseline_ids: Iterable[str], candidate_ids: Iterable[str], period: ExecutionPeriod) -> dict[str, object]:
    """Evaluate two already-frozen baskets under identical execution assumptions."""
    if not (period.formation_date < period.execution_date <= period.exit_date):
        raise DataQualityError("period requires formation before execution and execution on/before exit")
    baseline_gross = _return_before_costs(baseline_ids, period)
    candidate_gross = _return_before_costs(candidate_ids, period)
    benchmark_gross = benchmark_return(period)
    cost_cases = {
        str(cost_bps): {
            "baseline_return": str(cost_adjusted_return(baseline_gross, cost_bps)),
            "candidate_return": str(cost_adjusted_return(candidate_gross, cost_bps)),
            "benchmark_return": str(benchmark_gross),
            "baseline_relative_return": str(cost_adjusted_return(baseline_gross, cost_bps) - benchmark_gross),
            "candidate_relative_return": str(cost_adjusted_return(candidate_gross, cost_bps) - benchmark_gross),
        }
        for cost_bps in COST_CASES_BPS
    }
    return {
        "formation_date": period.formation_date.isoformat(),
        "execution_date": period.execution_date.isoformat(),
        "exit_date": period.exit_date.isoformat(),
        "baseline_gross_return": str(baseline_gross),
        "candidate_gross_return": str(candidate_gross),
        "benchmark_return": str(benchmark_gross),
        "cost_cases_bps": cost_cases,
    }


def cumulative_return(period_returns: Iterable[Decimal]) -> Decimal:
    nav = Decimal("1")
    for value in period_returns:
        nav *= Decimal("1") + value
    return nav - Decimal("1")


def load_selection_manifest(path: Path) -> dict[str, object]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest["status"] != "selection_manifest_prepared":
            raise DataQualityError("selection manifest has an invalid status")
        if manifest["holdout_performance_evaluated"] is not False:
            raise DataQualityError("selection manifest is not safe for its first evaluation")
        if manifest["portfolio_size"] != PORTFOLIO_SIZE:
            raise DataQualityError("selection manifest portfolio size differs from the frozen protocol")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid holdout selection manifest") from error
    return manifest


def _ids(formation: dict[str, object], key: str) -> tuple[str, ...]:
    try:
        rows = formation[key]
        return tuple(str(row["security_id"]) for row in rows)  # type: ignore[index]
    except (KeyError, TypeError) as error:
        raise DataQualityError(f"selection manifest is missing {key} positions") from error


def _parse_period(document: dict[str, object]) -> ExecutionPeriod:
    try:
        return ExecutionPeriod(
            date.fromisoformat(str(document["formation_date"])),
            date.fromisoformat(str(document["execution_date"])),
            date.fromisoformat(str(document["exit_date"])),
            {str(key): Decimal(str(value)) for key, value in dict(document["entry_prices"]).items()},
            {str(key): Decimal(str(value)) for key, value in dict(document["exit_prices"]).items()},
            Decimal(str(document["benchmark_entry_price"])),
            Decimal(str(document["benchmark_exit_price"])),
            frozenset(str(value) for value in document.get("corporate_action_security_ids", [])),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise DataQualityError("invalid execution-period input") from error


def evaluate_manifest(manifest: dict[str, object], periods: Iterable[ExecutionPeriod]) -> dict[str, object]:
    """Evaluate manifest formations only; unrecognized dates and reranking are forbidden."""
    formation_by_date = {
        str(formation["formation_date"]): formation
        for formation in manifest["formations"]  # type: ignore[index]
    }
    results: list[dict[str, object]] = []
    for period in periods:
        formation = formation_by_date.get(period.formation_date.isoformat())
        if formation is None:
            raise DataQualityError(f"execution period is not in the frozen manifest: {period.formation_date}")
        results.append(evaluate_period(
            baseline_ids=_ids(formation, "baseline"), candidate_ids=_ids(formation, "elastic_net"), period=period,
        ))
    if not results:
        raise DataQualityError("execution evaluation requires at least one frozen formation period")
    summaries: dict[str, dict[str, str]] = {}
    for cost_bps in COST_CASES_BPS:
        key = str(cost_bps)
        baseline = [Decimal(item["cost_cases_bps"][key]["baseline_return"]) for item in results]  # type: ignore[index]
        candidate = [Decimal(item["cost_cases_bps"][key]["candidate_return"]) for item in results]  # type: ignore[index]
        benchmark = [Decimal(item["cost_cases_bps"][key]["benchmark_return"]) for item in results]  # type: ignore[index]
        baseline_cumulative = cumulative_return(baseline)
        candidate_cumulative = cumulative_return(candidate)
        benchmark_cumulative = cumulative_return(benchmark)
        summaries[key] = {
            "baseline_cumulative_return": str(baseline_cumulative),
            "candidate_cumulative_return": str(candidate_cumulative),
            "benchmark_cumulative_return": str(benchmark_cumulative),
            "baseline_relative_return": str(baseline_cumulative - benchmark_cumulative),
            "candidate_relative_return": str(candidate_cumulative - benchmark_cumulative),
        }
    return {
        "status": "execution_cost_evaluation_complete",
        "holdout_performance_evaluated": True,
        "formation_period_count": len(results),
        "periods": results,
        "cost_case_summaries_bps": summaries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate frozen baseline and elastic-net selections with supplied next-open prices")
    parser.add_argument("--selection-manifest", type=Path, required=True)
    parser.add_argument("--period-input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm-locked-holdout", action="store_true")
    arguments = parser.parse_args()
    require_locked_holdout_confirmation(arguments.confirm_locked_holdout)
    if arguments.output.exists():
        raise DataQualityError(f"refusing to overwrite immutable holdout evaluation: {arguments.output}")
    manifest = load_selection_manifest(arguments.selection_manifest)
    try:
        documents = json.loads(arguments.period_input.read_text(encoding="utf-8"))
        periods = tuple(_parse_period(item) for item in documents["periods"])
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid execution-period input document") from error
    result = evaluate_manifest(manifest, periods)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"formation_periods={result['formation_period_count']}; holdout_performance_evaluated=true")


if __name__ == "__main__":
    main()
