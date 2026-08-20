from datetime import date, timedelta
import unittest

from quantrade_research.quality import DataQualityError
from quantrade_research.validation import (
    WalkForwardFold,
    assert_walk_forward_plan_is_chronological,
    build_expanding_window_folds,
)


START = date(2026, 1, 1)


class WalkForwardValidationTests(unittest.TestCase):
    def test_builds_expanding_history_with_strictly_future_validation(self) -> None:
        dates = [START + timedelta(days=index) for index in range(8)]
        folds = build_expanding_window_folds(
            dates, minimum_training_observations=3, validation_observations=2
        )
        self.assertEqual(len(folds), 2)
        self.assertEqual(folds[0].training_dates, tuple(dates[:3]))
        self.assertEqual(folds[0].validation_dates, tuple(dates[3:5]))
        self.assertEqual(folds[1].training_dates, tuple(dates[:5]))
        self.assertEqual(folds[1].validation_dates, tuple(dates[5:7]))
        assert_walk_forward_plan_is_chronological(folds)

    def test_rejects_duplicate_dates_and_insufficient_history(self) -> None:
        with self.assertRaisesRegex(DataQualityError, "unique"):
            build_expanding_window_folds(
                [START, START], minimum_training_observations=1, validation_observations=1
            )
        with self.assertRaisesRegex(DataQualityError, "not enough"):
            build_expanding_window_folds(
                [START, START + timedelta(days=1)],
                minimum_training_observations=2,
                validation_observations=1,
            )

    def test_rejects_non_expanding_or_overlapping_manual_plan(self) -> None:
        dates = [START + timedelta(days=index) for index in range(5)]
        invalid = (
            WalkForwardFold(1, tuple(dates[:2]), tuple(dates[2:3])),
            WalkForwardFold(2, tuple(dates[:2]), tuple(dates[3:4])),
        )
        with self.assertRaisesRegex(DataQualityError, "include prior validation"):
            assert_walk_forward_plan_is_chronological(invalid)


if __name__ == "__main__":
    unittest.main()
