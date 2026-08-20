from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import unittest

from quantrade_research.feature_diagnostics import FeatureOutcome
from quantrade_research.features import BASELINE_FEATURE_DEFINITIONS, FeatureRegistry
from quantrade_research.quality import DataQualityError
from quantrade_research.ranking import SectorClassification, build_sector_aware_percentile_ranks


FORMATION = date(2026, 8, 20)
DECISION = datetime(2026, 8, 20, 20, tzinfo=timezone.utc)
REGISTRY = FeatureRegistry((BASELINE_FEATURE_DEFINITIONS[0], BASELINE_FEATURE_DEFINITIONS[4]))


def outcomes() -> list[FeatureOutcome]:
    values = {
        "a": ("1", "0.2"),
        "b": ("3", "0.4"),
        "c": ("2", "0.3"),
    }
    result: list[FeatureOutcome] = []
    for definition in REGISTRY.definitions():
        for security_id, (momentum, risk) in values.items():
            value = momentum if definition.key == "momentum_12_1" else risk
            result.append(
                FeatureOutcome(
                    security_id, FORMATION, definition.key, definition.version,
                    definition.definition_hash, Decimal(value),
                )
            )
    return result


def sectors() -> list[SectorClassification]:
    return [
        SectorClassification("a", "technology", FORMATION, DECISION),
        SectorClassification("b", "technology", FORMATION, DECISION),
        SectorClassification("c", "utilities", FORMATION, DECISION),
    ]


class SectorAwareRankingTests(unittest.TestCase):
    def test_ranks_within_sector_and_orients_lower_risk_as_better(self) -> None:
        ranks = build_sector_aware_percentile_ranks(
            outcomes(), sectors(), formation_date=FORMATION, decision_at=DECISION,
            universe_security_ids={"a", "b", "c"}, registry=REGISTRY,
        )
        by_identity = {(item.security_id, item.feature_key): item for item in ranks}
        self.assertEqual(by_identity[("a", "momentum_12_1")].percentile, Decimal("0"))
        self.assertEqual(by_identity[("b", "momentum_12_1")].percentile, Decimal("1"))
        self.assertEqual(by_identity[("a", "trailing_volatility_60d")].percentile, Decimal("1"))
        self.assertEqual(by_identity[("b", "trailing_volatility_60d")].percentile, Decimal("0"))
        self.assertEqual(
            by_identity[("c", "momentum_12_1")].unavailable_reason,
            "insufficient_sector_peers",
        )

    def test_rejects_future_or_missing_sector_classification(self) -> None:
        future = sectors()
        future[0] = SectorClassification("a", "technology", FORMATION, DECISION + timedelta(seconds=1))
        with self.assertRaisesRegex(DataQualityError, "unavailable"):
            build_sector_aware_percentile_ranks(
                outcomes(), future, formation_date=FORMATION, decision_at=DECISION,
                universe_security_ids={"a", "b", "c"}, registry=REGISTRY,
            )
        with self.assertRaisesRegex(DataQualityError, "missing sector"):
            build_sector_aware_percentile_ranks(
                outcomes(), sectors()[:-1], formation_date=FORMATION, decision_at=DECISION,
                universe_security_ids={"a", "b", "c"}, registry=REGISTRY,
            )

    def test_requires_explicit_outcomes_for_every_registered_feature(self) -> None:
        with self.assertRaisesRegex(DataQualityError, "missing explicit"):
            build_sector_aware_percentile_ranks(
                outcomes()[:-1], sectors(), formation_date=FORMATION, decision_at=DECISION,
                universe_security_ids={"a", "b", "c"}, registry=REGISTRY,
            )


if __name__ == "__main__":
    unittest.main()
