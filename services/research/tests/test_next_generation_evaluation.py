from dataclasses import replace
from decimal import Decimal
import unittest

from quantrade_research.next_generation_evaluation import (
    ChallengerMetrics,
    challenger_selection_key,
    evaluate_challenger,
)
from quantrade_research.quality import DataQualityError


def metrics(model_version: str, **overrides) -> ChallengerMetrics:
    values = {
        "model_version": model_version,
        "observation_count": 1000,
        "score_date_count": 100,
        "fold_count": 3,
        "monthly_formation_count": 18,
        "feature_coverage": Decimal("0.95"),
        "mean_daily_spearman_ic": Decimal("0.05"),
        "top_minus_bottom_spread": Decimal("0.03"),
        "positive_ic_share": Decimal("0.60"),
        "fold_mean_ics": (Decimal("0.03"), Decimal("0.05"), Decimal("0.07")),
        "consecutive_rank_correlation": Decimal("0.80"),
        "mean_monthly_turnover": Decimal("0.40"),
        "relative_return_after_20bps": Decimal("0.10"),
        "positive_month_share": Decimal("0.60"),
        "mae": Decimal("0.06"),
        "rmse": Decimal("0.08"),
    }
    values.update(overrides)
    return ChallengerMetrics(**values)


class NextGenerationEvaluationTests(unittest.TestCase):
    def test_eligible_challenger_must_pass_every_registered_gate(self) -> None:
        active = metrics("active")
        challenger = metrics(
            "challenger",
            mean_daily_spearman_ic=Decimal("0.055"),
            top_minus_bottom_spread=Decimal("0.028"),
            positive_ic_share=Decimal("0.57"),
            consecutive_rank_correlation=Decimal("0.75"),
            mean_monthly_turnover=Decimal("0.50"),
            positive_month_share=Decimal("0.55"),
            mae=Decimal("0.0612"),
            rmse=Decimal("0.0816"),
        )
        decision = evaluate_challenger(active, challenger)
        self.assertTrue(decision.freeze_eligible)
        self.assertTrue(all(result.passed for result in decision.results))

    def test_one_failed_gate_blocks_freeze(self) -> None:
        active = metrics("active")
        challenger = metrics("challenger", mean_daily_spearman_ic=Decimal("0.0549"))
        decision = evaluate_challenger(active, challenger)
        self.assertFalse(decision.freeze_eligible)
        self.assertEqual(
            {result.gate for result in decision.results if not result.passed},
            {"rank_ic_improvement"},
        )

    def test_common_sample_and_every_fold_are_mandatory(self) -> None:
        active = metrics("active")
        challenger = metrics(
            "challenger",
            observation_count=999,
            mean_daily_spearman_ic=Decimal("0.06"),
            fold_mean_ics=(Decimal("0.04"), Decimal("0"), Decimal("0.06")),
        )
        decision = evaluate_challenger(active, challenger)
        failures = {result.gate for result in decision.results if not result.passed}
        self.assertEqual(failures, {"common_sample", "fold_stability"})

    def test_deterministic_selection_prioritizes_ic_then_spread(self) -> None:
        lower_ic = metrics("a", mean_daily_spearman_ic=Decimal("0.06"), top_minus_bottom_spread=Decimal("0.05"))
        higher_ic = metrics("b", mean_daily_spearman_ic=Decimal("0.07"), top_minus_bottom_spread=Decimal("0.03"))
        equal_ic_better_spread = replace(higher_ic, model_version="c", top_minus_bottom_spread=Decimal("0.04"))
        ordered = sorted((lower_ic, higher_ic, equal_ic_better_spread), key=challenger_selection_key)
        self.assertEqual([item.model_version for item in ordered], ["c", "b", "a"])

    def test_invalid_metric_ranges_are_rejected(self) -> None:
        with self.assertRaisesRegex(DataQualityError, "coverage"):
            metrics("invalid", feature_coverage=Decimal("1.1"))
        with self.assertRaisesRegex(DataQualityError, "Spearman"):
            metrics("invalid", mean_daily_spearman_ic=Decimal("1.1"))


if __name__ == "__main__":
    unittest.main()
