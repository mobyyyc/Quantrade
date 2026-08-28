from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.monthly_feature_family_decision import (
    MAXIMUM_RANK_STABILITY_REGRESSION, MAXIMUM_TURNOVER, MINIMUM_AGGREGATE_COVERAGE,
)


class MonthlyFeatureFamilyDecisionTests(unittest.TestCase):
    def test_frozen_thresholds_match_protocol(self) -> None:
        self.assertEqual(MINIMUM_AGGREGATE_COVERAGE, 0.90)
        self.assertEqual(MAXIMUM_TURNOVER, 0.75)
        self.assertEqual(MAXIMUM_RANK_STABILITY_REGRESSION, 0.05)


if __name__ == "__main__":
    unittest.main()
