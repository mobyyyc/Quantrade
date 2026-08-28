from decimal import Decimal
from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.monthly_model_dataset import centered_percentiles


class MonthlyModelDatasetTests(unittest.TestCase):
    def test_market_percentiles_are_centered_and_ties_are_stable(self) -> None:
        ranks = centered_percentiles(
            {"a": Decimal("1"), "b": Decimal("2"), "c": Decimal("2")}, higher_is_better=True,
        )
        self.assertEqual(ranks["a"], Decimal("-0.5"))
        self.assertEqual(ranks["b"], Decimal("0.25"))
        self.assertEqual(ranks["b"], ranks["c"])

    def test_lower_values_can_receive_favorable_rank(self) -> None:
        ranks = centered_percentiles(
            {"a": Decimal("1"), "b": Decimal("2"), "c": Decimal("3")}, higher_is_better=False,
        )
        self.assertEqual(ranks["a"], Decimal("0.5"))
        self.assertEqual(ranks["c"], Decimal("-0.5"))


if __name__ == "__main__":
    unittest.main()
