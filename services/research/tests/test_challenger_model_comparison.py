from datetime import date, timedelta
from decimal import Decimal
import math
import unittest

from quantrade_research.challenger_model_comparison import (
    ComparisonExample,
    Prediction,
    build_metrics,
    fit_gradient_boosted_stumps,
    fit_pairwise_ranker,
    fit_robust_linear,
)


def example(index: int, *, outlier: bool = False) -> ComparisonExample:
    value = index / 30
    target = 10.0 if outlier else value * 0.1
    features = tuple(value for _ in range(8))
    return ComparisonExample(
        date(2024, 1, 31),
        f"security-{index}",
        features[:6],
        features,
        target,
        target + 0.02,
        0.02,
    )


class ChallengerModelComparisonTests(unittest.TestCase):
    def test_all_three_candidate_families_fit_finite_ordered_predictions(self) -> None:
        rows = [example(index, outlier=index == 29) for index in range(30)]
        models = (
            fit_robust_linear(rows, l2_penalty=0.1, huber_delta=1.5),
            fit_gradient_boosted_stumps(rows, estimators=5, learning_rate=0.1),
            fit_pairwise_ranker(rows, l2_penalty=0.01, epochs=3),
        )
        for model in models:
            low = model.predict(rows[0].challenger_features)
            high = model.predict(rows[-1].challenger_features)
            self.assertTrue(math.isfinite(low) and math.isfinite(high))
            self.assertGreater(high, low)

    def test_metrics_cover_ranking_stability_costs_and_error(self) -> None:
        predictions: list[Prediction] = []
        start = date(2024, 1, 31)
        for fold in range(1, 4):
            for day_offset in range(2):
                score_date = start + timedelta(days=(fold - 1) * 31 + day_offset)
                for index in range(20):
                    target = index / 100
                    predictions.append(Prediction(
                        fold, score_date, f"security-{index:02d}", target, target,
                        target + 0.01, 0.01,
                    ))
        metrics = build_metrics(
            "candidate", predictions, feature_coverage=Decimal("0.95"),
        )
        self.assertEqual(metrics.fold_count, 3)
        self.assertEqual(metrics.mean_daily_spearman_ic, Decimal("1.0"))
        self.assertEqual(metrics.mae, Decimal("0.0"))
        self.assertEqual(metrics.mean_monthly_turnover, Decimal("0.0"))
        self.assertEqual(metrics.point_in_time_violations, 0)


if __name__ == "__main__":
    unittest.main()
