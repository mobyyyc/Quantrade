from decimal import Decimal
import unittest

from quantrade_research.challenger_dataset import _percentiles


class ChallengerDatasetTests(unittest.TestCase):
    def test_candidate_percentiles_are_tie_aware_and_directional(self) -> None:
        values = [("a", Decimal("1")), ("b", Decimal("2")), ("c", Decimal("2"))]
        higher = _percentiles(values, higher_is_better=True)
        lower = _percentiles(values, higher_is_better=False)
        self.assertEqual(higher["a"], Decimal("0"))
        self.assertEqual(higher["b"], Decimal("0.75"))
        self.assertEqual(higher["b"], higher["c"])
        self.assertEqual(lower["a"], Decimal("1"))
        self.assertEqual(lower["b"], Decimal("0.25"))


if __name__ == "__main__":
    unittest.main()
