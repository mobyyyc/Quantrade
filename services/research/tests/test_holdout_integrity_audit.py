import unittest

from quantrade_research.holdout_integrity_audit import evaluate_holdout_integrity
from quantrade_research.quality import DataQualityError


COMPLETE = {"status": "execution_cost_evaluation_complete", "holdout_performance_evaluated": True}
ACCOUNTED = {**COMPLETE, "corporate_action_position_accounting": "verified"}


class HoldoutIntegrityAuditTests(unittest.TestCase):
    def test_blocks_approval_without_corporate_action_coverage(self) -> None:
        audit = evaluate_holdout_integrity(evaluation_document=COMPLETE, corporate_action_count=0)
        self.assertFalse(audit["approval_eligible"])
        self.assertEqual(audit["approval_status"], "blocked_integrity")
        self.assertEqual(audit["failures"][0]["gate"], "corporate_action_coverage")

    def test_blocks_approval_when_saved_evaluation_has_no_action_accounting(self) -> None:
        audit = evaluate_holdout_integrity(evaluation_document=COMPLETE, corporate_action_count=3)
        self.assertFalse(audit["approval_eligible"])
        self.assertEqual(audit["failures"][0]["gate"], "corporate_action_position_accounting")

    def test_allows_remaining_policy_review_when_coverage_and_accounting_exist(self) -> None:
        audit = evaluate_holdout_integrity(evaluation_document=ACCOUNTED, corporate_action_count=3)
        self.assertTrue(audit["approval_eligible"])
        self.assertEqual(audit["approval_status"], "eligible_for_policy_review")

    def test_rejects_incomplete_evaluation_document(self) -> None:
        with self.assertRaisesRegex(DataQualityError, "incomplete"):
            evaluate_holdout_integrity(evaluation_document={}, corporate_action_count=1)


if __name__ == "__main__":
    unittest.main()
