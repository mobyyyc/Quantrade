from datetime import date, timedelta
import json
import unittest

from quantrade_research.prediction_calibration import (
    MonthlyBasketObservation,
    build_prediction_context,
    summarize_basket_calibration,
)
from quantrade_research.quality import DataQualityError
from quantrade_research.regularized_training import FEATURE_COLUMNS, TrainingExample


def development_examples() -> tuple[TrainingExample, ...]:
    rows: list[TrainingExample] = []
    for session in range(420):
        score_date = date(2023, 1, 2) + timedelta(days=session)
        for security in range(25):
            signal = ((security * 5 + session * 3) % 101) / 100
            features = tuple(
                min(1.0, max(0.0, signal + (offset - 2) * 0.01))
                for offset in range(len(FEATURE_COLUMNS))
            )
            target = (signal - 0.5) * 0.08 + ((session % 7) - 3) * 0.001
            rows.append(TrainingExample(score_date, features, target))
    return tuple(rows)


def experiment_bytes(*, holdout_used: bool = False) -> bytes:
    return json.dumps({
        "holdout_used": holdout_used,
        "holdout_excluded_from_input": not holdout_used,
        "selected_candidate": {"family": "elastic_net", "l1_penalty": 0.001, "l2_penalty": 0.01},
        "final_development_model": {"family": "elastic_net", "l1_penalty": 0.001, "l2_penalty": 0.01},
    }).encode("utf-8")


class PredictionCalibrationTests(unittest.TestCase):
    def test_builds_deterministic_monthly_context_from_development_only(self) -> None:
        examples = development_examples()
        first = build_prediction_context(examples=examples, experiment_bytes=experiment_bytes())
        second = build_prediction_context(examples=examples, experiment_bytes=experiment_bytes())

        self.assertEqual(first, second)
        self.assertFalse(first["holdout_used"])
        self.assertGreaterEqual(first["monthly_formation_count"], 10)
        self.assertEqual(first["basket_calibration"]["status"], "supported")
        self.assertGreater(first["basket_calibration"]["slope"], 0)
        self.assertLessEqual(
            first["basket_empirical_error_range"]["lower_residual"],
            first["basket_empirical_error_range"]["upper_residual"],
        )

    def test_rejects_holdout_contamination(self) -> None:
        with self.assertRaisesRegex(DataQualityError, "exclude the locked holdout"):
            build_prediction_context(
                examples=development_examples(),
                experiment_bytes=experiment_bytes(holdout_used=True),
            )

    def test_records_unsupported_status_instead_of_forcing_negative_calibration(self) -> None:
        baskets = tuple(
            MonthlyBasketObservation(
                date(2023, month, 28),
                month / 1000,
                -month / 500,
            )
            for month in range(1, 11)
        )
        status, intercept, slope, residuals, observed_slope = summarize_basket_calibration(baskets)

        self.assertEqual(status, "unsupported_nonpositive_slope")
        self.assertIsNone(intercept)
        self.assertIsNone(slope)
        self.assertLess(observed_slope, 0)
        self.assertEqual(len(residuals), 10)


if __name__ == "__main__":
    unittest.main()
