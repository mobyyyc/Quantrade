from datetime import date
import unittest

from quantrade_research.historical_training_export import HOLDOUT_END, HOLDOUT_START, dataset_partition


class HistoricalTrainingExportTests(unittest.TestCase):
    def test_partitions_the_locked_holdout_inclusively(self) -> None:
        self.assertEqual(dataset_partition(date(2025, 6, 30)), "development")
        self.assertEqual(dataset_partition(HOLDOUT_START), "holdout")
        self.assertEqual(dataset_partition(HOLDOUT_END), "holdout")


if __name__ == "__main__":
    unittest.main()
