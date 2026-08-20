from decimal import Decimal
import unittest

from quantrade_research.approval import ModelApprovalEvidence, evaluate_model_approval


def evidence(**overrides) -> ModelApprovalEvidence:
    values = {
        "data_capability_tier": "B",
        "walk_forward_fold_count": 3,
        "feature_coverage": Decimal("0.95"),
        "holdout_evaluated": True,
        "holdout_relative_return_after_20bps": Decimal("0.01"),
        "point_in_time_violations": 0,
        "unresolved_data_quality_issues": 0,
    }
    values.update(overrides)
    return ModelApprovalEvidence(**values)


class ModelApprovalTests(unittest.TestCase):
    def test_tier_b_can_pass_private_beta_but_not_public_claim(self) -> None:
        private = evaluate_model_approval(evidence(), scope="private_beta")
        public = evaluate_model_approval(evidence(), scope="public_performance_claim")
        self.assertTrue(private.approved)
        self.assertFalse(public.approved)
        self.assertFalse([result for result in public.results if result.gate == "data_capability"][0].passed)

    def test_fails_for_holdout_cost_or_integrity_violations(self) -> None:
        decision = evaluate_model_approval(
            evidence(holdout_relative_return_after_20bps=Decimal("-0.01"), point_in_time_violations=1),
            scope="private_beta",
        )
        self.assertFalse(decision.approved)
        failures = {result.gate for result in decision.results if not result.passed}
        self.assertEqual(failures, {"point_in_time_integrity", "cost_robustness"})


if __name__ == "__main__":
    unittest.main()
