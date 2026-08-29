from decimal import Decimal
import unittest

from quantrade_research.wealth_ledger_reconciliation import evaluate_reconciliation


class WealthLedgerReconciliationTests(unittest.TestCase):
    def test_passes_with_action_and_benchmark_evidence_inside_tolerances(self) -> None:
        report = evaluate_reconciliation(
            equity_differences=[Decimal("0"), Decimal("0.0002")],
            equity_action_differences=[Decimal("0.0002")],
            benchmark_differences=[Decimal("0.0001")],
            completed_windows=2, withheld_windows=1, benchmark_action_count=4,
        )
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["failures"], [])

    def test_blocks_missing_action_evidence_or_large_differences(self) -> None:
        report = evaluate_reconciliation(
            equity_differences=[Decimal("0.01")], equity_action_differences=[],
            benchmark_differences=[Decimal("0.01")], completed_windows=1,
            withheld_windows=0, benchmark_action_count=0,
        )
        self.assertEqual(report["status"], "blocked")
        self.assertGreaterEqual(len(report["failures"]), 3)


if __name__ == "__main__":
    unittest.main()
