from datetime import date
from decimal import Decimal
import unittest

from quantrade_research.baseline import BASELINE_MODEL_VERSION, build_equal_weight_baseline
from quantrade_research.features import BASELINE_FEATURE_DEFINITIONS, FeatureRegistry
from quantrade_research.quality import DataQualityError
from quantrade_research.ranking import SectorPercentileRank


FORMATION = date(2026, 8, 20)
REGISTRY = FeatureRegistry(BASELINE_FEATURE_DEFINITIONS[:2])


def ranks() -> list[SectorPercentileRank]:
    result: list[SectorPercentileRank] = []
    values = {"a": (Decimal("0.25"), Decimal("0.75")), "b": (Decimal("0.5"), None)}
    for definition in REGISTRY.definitions():
        for security_id, (momentum, relative_strength) in values.items():
            value = momentum if definition.key == "momentum_12_1" else relative_strength
            result.append(
                SectorPercentileRank(
                    security_id, FORMATION, definition.key, definition.version,
                    definition.definition_hash, "technology", 2, value,
                    None if value is not None else "insufficient_sector_peers",
                )
            )
    return result


class CompositeBaselineTests(unittest.TestCase):
    def test_averages_all_required_ranks_equally(self) -> None:
        scores = build_equal_weight_baseline(
            ranks(), formation_date=FORMATION, universe_security_ids={"a", "b"}, registry=REGISTRY
        )
        by_security = {score.security_id: score for score in scores}
        self.assertEqual(by_security["a"].normalized_score, Decimal("0.5"))
        self.assertEqual(by_security["a"].display_score, Decimal("50.0"))
        self.assertEqual(by_security["a"].model_version, BASELINE_MODEL_VERSION)
        self.assertEqual(by_security["a"].feature_registry_hash, REGISTRY.registry_hash)

    def test_marks_any_missing_required_rank_ineligible(self) -> None:
        scores = build_equal_weight_baseline(
            ranks(), formation_date=FORMATION, universe_security_ids={"a", "b"}, registry=REGISTRY
        )
        score = {item.security_id: item for item in scores}["b"]
        self.assertFalse(score.eligible)
        self.assertIn("relative_strength_6m@v1", score.unavailable_reason)

    def test_requires_complete_explicit_rank_matrix(self) -> None:
        with self.assertRaisesRegex(DataQualityError, "missing explicit"):
            build_equal_weight_baseline(
                ranks()[:-1], formation_date=FORMATION, universe_security_ids={"a", "b"}, registry=REGISTRY
            )


if __name__ == "__main__":
    unittest.main()
