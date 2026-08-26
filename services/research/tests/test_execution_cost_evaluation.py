from datetime import date
from decimal import Decimal
import unittest

from quantrade_research.execution_cost_evaluation import (
    ExecutionPeriod,
    cost_adjusted_return,
    evaluate_manifest,
    evaluate_period,
)
from quantrade_research.quality import DataQualityError


IDS = tuple(f"id-{index:02d}" for index in range(20))


def period(*, actions=frozenset()) -> ExecutionPeriod:
    return ExecutionPeriod(
        date(2025, 7, 31), date(2025, 8, 1), date(2025, 8, 29),
        {security_id: Decimal("100") for security_id in IDS},
        {security_id: Decimal("110") for security_id in IDS},
        Decimal("500"), Decimal("550"), actions,
    )


def manifest() -> dict[str, object]:
    positions = [{"security_id": security_id} for security_id in IDS]
    return {
        "status": "selection_manifest_prepared",
        "holdout_performance_evaluated": False,
        "portfolio_size": 20,
        "formations": [{"formation_date": "2025-07-31", "baseline": positions, "elastic_net": positions}],
    }


class ExecutionCostEvaluationTests(unittest.TestCase):
    def test_applies_entry_and_exit_costs_to_frozen_equal_weight_basket(self) -> None:
        result = evaluate_period(baseline_ids=IDS, candidate_ids=IDS, period=period())
        self.assertEqual(result["baseline_gross_return"], "0.1")
        self.assertEqual(Decimal(result["cost_cases_bps"]["5"]["baseline_return"]), cost_adjusted_return(Decimal("0.10"), Decimal("5")))
        self.assertEqual(result["cost_cases_bps"]["5"]["benchmark_return"], "0.1")

    def test_rejects_missing_price_or_unhandled_corporate_action(self) -> None:
        broken = period(actions=frozenset({"id-00"}))
        with self.assertRaisesRegex(DataQualityError, "corporate action"):
            evaluate_period(baseline_ids=IDS, candidate_ids=IDS, period=broken)
        missing = period()
        entry = dict(missing.entry_prices)
        entry.pop("id-00")
        with self.assertRaisesRegex(DataQualityError, "missing frozen"):
            evaluate_period(
                baseline_ids=IDS, candidate_ids=IDS,
                period=ExecutionPeriod(missing.formation_date, missing.execution_date, missing.exit_date, entry, missing.exit_prices, missing.benchmark_entry_price, missing.benchmark_exit_price),
            )

    def test_manifest_cannot_rerank_or_accept_unknown_formation(self) -> None:
        result = evaluate_manifest(manifest(), (period(),))
        self.assertTrue(result["holdout_performance_evaluated"])
        unknown = ExecutionPeriod(date(2025, 8, 31), date(2025, 9, 1), date(2025, 9, 30), period().entry_prices, period().exit_prices, Decimal("1"), Decimal("1"))
        with self.assertRaisesRegex(DataQualityError, "not in the frozen manifest"):
            evaluate_manifest(manifest(), (unknown,))


if __name__ == "__main__":
    unittest.main()
