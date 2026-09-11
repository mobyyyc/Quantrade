import unittest

from quantrade_research.live_eligibility_rollout import audit_rows
from quantrade_research.quality import DataQualityError


class LiveEligibilityRolloutTests(unittest.TestCase):
    def test_classifies_new_and_still_excluded_rows(self) -> None:
        rows = (
            ("1", "OLD", True, "momentum", 0.7, None),
            ("1", "OLD", True, "volatility", 0.6, None),
            ("2", "NEW", False, "momentum", 0.4, None),
            ("2", "NEW", False, "volatility", 0.3, None),
            ("3", "OUT", False, "momentum", None, "insufficient history"),
            ("3", "OUT", False, "volatility", 0.2, None),
        )

        result = audit_rows(rows, required_feature_keys=("momentum", "volatility"))

        self.assertEqual(result["previously_eligible_count"], 1)
        self.assertEqual(result["corrected_eligible_count"], 2)
        self.assertEqual(result["newly_eligible_securities"], ["NEW [2]"])
        self.assertEqual(result["still_excluded_count"], 1)
        self.assertEqual(
            result["still_excluded"],
            {"OUT [3]": ["momentum:insufficient history"]},
        )
        self.assertEqual(
            result["still_excluded_reasons"],
            {"momentum:insufficient history": 1},
        )

    def test_rejects_regression_for_previously_eligible_row(self) -> None:
        with self.assertRaisesRegex(DataQualityError, "previously eligible"):
            audit_rows(
                (("1", "OLD", True, "momentum", None, "missing"),),
                required_feature_keys=("momentum",),
            )


if __name__ == "__main__":
    unittest.main()
