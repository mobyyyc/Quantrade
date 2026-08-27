from datetime import date
import unittest

from quantrade_research.holdout_prediction_diagnostics import (
    PredictionObservation,
    build_prediction_diagnostics,
)


class HoldoutPredictionDiagnosticsTests(unittest.TestCase):
    def test_perfect_order_and_predictions_report_perfect_metrics(self) -> None:
        rows = tuple(
            PredictionObservation(
                date(2025, month, 28), f"security-{index}", f"T{index}", value, value,
            )
            for month in (7, 8)
            for index, value in enumerate((-.05, -.04, -.03, -.02, -.01, .01, .02, .03, .04, .05))
        )

        report = build_prediction_diagnostics(rows)
        metrics = report["all_completed_examples"]
        rank = report["cross_sectional_rank_quality"]

        self.assertEqual(metrics["mae"], 0)
        self.assertEqual(metrics["rmse"], 0)
        self.assertEqual(metrics["directional_accuracy"], 1)
        self.assertAlmostEqual(rank["mean_daily_spearman_ic"], 1)
        self.assertGreater(rank["top_minus_bottom_actual_spread"], 0)
        self.assertTrue(report["reporting_only_no_model_selection"])


if __name__ == "__main__":
    unittest.main()
