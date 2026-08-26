from datetime import date
import unittest

from quantrade_research.corporate_action_coverage import (
    CorporateActionCoverageEvidence,
    evaluate_corporate_action_coverage,
)


class CorporateActionCoverageTests(unittest.TestCase):
    def test_accepts_completed_raw_backed_cohort_run_with_actions(self) -> None:
        report = evaluate_corporate_action_coverage(CorporateActionCoverageEvidence(
            start_date=date(2025, 7, 1), end_date=date(2026, 6, 30),
            action_count=42, completed_run_count=1, requested_chunks=110,
            completed_chunks=110, chunks_without_raw_document=0,
        ))
        self.assertTrue(report["coverage_ready"])
        self.assertEqual(report["failures"], [])

    def test_blocks_when_the_backfill_is_missing_or_not_raw_backed(self) -> None:
        report = evaluate_corporate_action_coverage(CorporateActionCoverageEvidence(
            start_date=date(2025, 7, 1), end_date=date(2026, 6, 30),
            action_count=1, completed_run_count=0, requested_chunks=110,
            completed_chunks=109, chunks_without_raw_document=1,
        ))
        self.assertFalse(report["coverage_ready"])
        self.assertEqual(len(report["failures"]), 3)

    def test_blocks_when_the_requested_period_has_no_actions(self) -> None:
        report = evaluate_corporate_action_coverage(CorporateActionCoverageEvidence(
            start_date=date(2025, 7, 1), end_date=date(2026, 6, 30),
            action_count=0, completed_run_count=1, requested_chunks=110,
            completed_chunks=110, chunks_without_raw_document=0,
        ))
        self.assertFalse(report["coverage_ready"])
        self.assertIn("no corporate-action records", report["failures"][0])


if __name__ == "__main__":
    unittest.main()
