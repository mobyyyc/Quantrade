from dataclasses import replace
from datetime import date
from decimal import Decimal
import unittest

from quantrade_research.baseline import build_equal_weight_baseline
from quantrade_research.explanations import build_baseline_feature_contributions
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


class BaselineExplanationTests(unittest.TestCase):
    def test_explains_each_feature_with_fixed_weight_and_contribution(self) -> None:
        score_rows = build_equal_weight_baseline(
            ranks(), formation_date=FORMATION, universe_security_ids={"a", "b"}, registry=REGISTRY
        )
        rows = build_baseline_feature_contributions(
            score_rows, ranks(), formation_date=FORMATION,
            universe_security_ids={"a", "b"}, registry=REGISTRY,
        )
        a_rows = [row for row in rows if row.security_id == "a"]
        self.assertEqual([row.weight for row in a_rows], [Decimal("0.5"), Decimal("0.5")])
        self.assertEqual([row.contribution for row in a_rows], [Decimal("0.125"), Decimal("0.375")])
        self.assertEqual(sum(row.contribution for row in a_rows if row.contribution is not None), Decimal("0.5"))
        b_unavailable = [row for row in rows if row.security_id == "b" and row.contribution is None][0]
        self.assertEqual(b_unavailable.unavailable_reason, "insufficient_sector_peers")

    def test_rejects_score_that_does_not_match_the_rank_matrix(self) -> None:
        score_rows = list(build_equal_weight_baseline(
            ranks(), formation_date=FORMATION, universe_security_ids={"a", "b"}, registry=REGISTRY
        ))
        score_rows[0] = replace(score_rows[0], display_score=Decimal("40"))
        with self.assertRaisesRegex(DataQualityError, "does not match"):
            build_baseline_feature_contributions(
                score_rows, ranks(), formation_date=FORMATION,
                universe_security_ids={"a", "b"}, registry=REGISTRY,
            )


if __name__ == "__main__":
    unittest.main()
