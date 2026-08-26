from datetime import date, timedelta
import unittest

from quantrade_research.historical_training_export import HOLDOUT_START
from quantrade_research.quality import DataQualityError
from quantrade_research.regularized_training import (
    FEATURE_COLUMNS,
    TrainingExample,
    build_time_ordered_folds,
    fit_regularized_model,
    run_development_experiment,
)


def examples(session_count: int = 100) -> tuple[TrainingExample, ...]:
    values = []
    for day in range(session_count):
        values.extend(
            TrainingExample(
                date(2021, 1, 1) + timedelta(days=day),
                tuple(((day * (offset + 3)) % 97) / 100 for offset in range(len(FEATURE_COLUMNS))),
                ((day * 7) % 43) / 1000,
            )
            for _ in range(2)
        )
    return tuple(values)


class RegularizedTrainingTests(unittest.TestCase):
    def test_folds_keep_exact_twenty_session_purge(self) -> None:
        source = tuple(
            TrainingExample(date(2021, 1, 1) + timedelta(days=day), (day / 100,) * 6, day / 1000)
            for day in range(70)
        )
        folds = build_time_ordered_folds(source, fold_count=2, validation_sessions=10, purge_sessions=20)
        self.assertEqual(len(folds), 2)
        self.assertEqual((folds[0].validation_start_date - folds[0].training_end_date).days, 21)
        self.assertLess(folds[0].validation_end_date, folds[1].validation_start_date)

    def test_regularized_fits_are_finite_and_deterministic(self) -> None:
        source = examples()
        first = fit_regularized_model(source, family="ridge", l1_penalty=0, l2_penalty=0.1)
        second = fit_regularized_model(source, family="ridge", l1_penalty=0, l2_penalty=0.1)
        self.assertEqual(first.coefficients, second.coefficients)
        self.assertEqual(len(first.coefficients), len(FEATURE_COLUMNS))

    def test_requires_development_data_before_locked_holdout(self) -> None:
        contaminated = (TrainingExample(HOLDOUT_START, (0.1,) * 6, 0.1),)
        with self.assertRaisesRegex(DataQualityError, "need at least"):
            build_time_ordered_folds(contaminated)

    def test_experiment_is_explicitly_development_only(self) -> None:
        result = run_development_experiment(examples(450))
        self.assertFalse(result["holdout_used"])
        self.assertEqual(result["purge_sessions"], 20)
        self.assertIn(result["selected_candidate"]["family"], {"ridge", "elastic_net"})


if __name__ == "__main__":
    unittest.main()
