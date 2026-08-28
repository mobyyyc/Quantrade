from datetime import date
from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.monthly_model_comparison import spearman


class MonthlyModelComparisonTests(unittest.TestCase):
    def test_spearman_detects_order_and_reverse_order(self) -> None:
        self.assertAlmostEqual(spearman([("a", 1, 1), ("b", 2, 2), ("c", 3, 3)]), 1.0)
        self.assertAlmostEqual(spearman([("a", 1, 3), ("b", 2, 2), ("c", 3, 1)]), -1.0)

    def test_spearman_handles_prediction_ties_deterministically(self) -> None:
        value = spearman([("a", 1, 1), ("b", 1, 2), ("c", 2, 3)])
        self.assertGreater(value, 0)


if __name__ == "__main__":
    unittest.main()
