from datetime import date
import unittest

from quantrade_research.holdout_evaluation import (
    HoldoutRow,
    build_selection_manifest,
    require_locked_holdout_confirmation,
)
from quantrade_research.quality import DataQualityError
from quantrade_research.regularized_training import LinearModel


def model() -> LinearModel:
    return LinearModel("elastic_net", 0.001, 0.01, (0.0,) * 6, (1.0,) * 6, 0.0, (1.0, 0, 0, 0, 0, 0))


def rows() -> tuple[HoldoutRow, ...]:
    return tuple(
        HoldoutRow(date(2025, 7, 31), f"id-{index:02d}", f"T{index:02d}", 25 - index, (index / 100,) * 6)
        for index in range(25)
    )


class HoldoutEvaluationTests(unittest.TestCase):
    def test_requires_explicit_confirmation_before_holdout_access(self) -> None:
        with self.assertRaisesRegex(DataQualityError, "confirm-locked-holdout"):
            require_locked_holdout_confirmation(False)

    def test_selects_shared_top_twenty_with_stable_ties(self) -> None:
        manifest = build_selection_manifest(rows(), model())
        self.assertFalse(manifest["holdout_performance_evaluated"])
        formation = manifest["formations"][0]
        self.assertEqual(formation["shared_eligible_count"], 25)
        self.assertEqual(len(formation["baseline"]), 20)
        self.assertEqual(len(formation["elastic_net"]), 20)
        self.assertEqual(formation["baseline"][0]["security_id"], "id-24")
        self.assertEqual(formation["elastic_net"][0]["security_id"], "id-24")

    def test_rejects_incomplete_shared_formation(self) -> None:
        with self.assertRaisesRegex(DataQualityError, "fewer than 20"):
            build_selection_manifest(rows()[:19], model())


if __name__ == "__main__":
    unittest.main()
