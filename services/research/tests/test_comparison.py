from decimal import Decimal
import unittest

from quantrade_research.approval import ModelApprovalEvidence, evaluate_model_approval
from quantrade_research.comparison import RegularizedLinearModelSpec, compare_regularized_candidate
from quantrade_research.evaluation import PerformanceMetrics
from quantrade_research.quality import DataQualityError


def metrics(relative_return: str) -> PerformanceMetrics:
    return PerformanceMetrics(
        10, Decimal("0.1"), Decimal("0.05"), Decimal(relative_return), Decimal("0.1"),
        Decimal("1"), Decimal("1"), Decimal("1"), Decimal("-0.05"), Decimal("2"),
    )


def approved_decision():
    return evaluate_model_approval(
        ModelApprovalEvidence("B", 3, Decimal("0.95"), True, Decimal("0.01"), 0, 0),
        scope="private_beta",
    )


class RegularizedComparisonTests(unittest.TestCase):
    def test_compares_ridge_candidate_only_after_baseline_approval(self) -> None:
        candidate = RegularizedLinearModelSpec("ridge_v1", "ridge", Decimal("0"), Decimal("1"), "a" * 64)
        comparison = compare_regularized_candidate(
            approved_decision(), metrics("0.05"), "a" * 64, candidate, metrics("0.08")
        )
        self.assertEqual(comparison.relative_return_delta, Decimal("0.03"))
        self.assertEqual(comparison.candidate_family, "ridge")

    def test_rejects_unapproved_baseline_and_unregularized_candidate(self) -> None:
        rejected = evaluate_model_approval(
            ModelApprovalEvidence("B", 1, Decimal("0.5"), False, None, 1, 0),
            scope="private_beta",
        )
        candidate = RegularizedLinearModelSpec("ridge_v1", "ridge", Decimal("0"), Decimal("1"), "a" * 64)
        with self.assertRaisesRegex(DataQualityError, "approved"):
            compare_regularized_candidate(rejected, metrics("0.05"), "a" * 64, candidate, metrics("0.08"))
        with self.assertRaisesRegex(DataQualityError, "positive L2"):
            RegularizedLinearModelSpec("not_regularized", "ridge", Decimal("0"), Decimal("0"), "a" * 64)

    def test_rejects_candidate_with_a_different_feature_registry(self) -> None:
        candidate = RegularizedLinearModelSpec("ridge_v1", "ridge", Decimal("0"), Decimal("1"), "b" * 64)
        with self.assertRaisesRegex(DataQualityError, "feature registry"):
            compare_regularized_candidate(
                approved_decision(), metrics("0.05"), "a" * 64, candidate, metrics("0.08")
            )


if __name__ == "__main__":
    unittest.main()
