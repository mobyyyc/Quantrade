from datetime import date
from decimal import Decimal
import unittest

from quantrade_research.active_model import ActiveModelArtifact
from quantrade_research.features import baseline_feature_registry
from quantrade_research.ml_scoring import build_model_scores
from quantrade_research.ranking import SectorPercentileRank


FORMATION = date(2026, 8, 26)


class ModelScoringTests(unittest.TestCase):
    def test_preserves_raw_relative_return_before_cross_sectional_normalization(self) -> None:
        registry = baseline_feature_registry()
        columns = tuple(f"{definition.key}_percentile" for definition in registry.definitions())
        model = ActiveModelArtifact(
            "model-v1", "0.1", registry.registry_hash, columns,
            tuple(0.0 for _ in columns), tuple(1.0 for _ in columns), 0.01,
            (0.02,) + tuple(0.0 for _ in columns[1:]),
        )
        ranks = tuple(
            SectorPercentileRank(
                security_id, FORMATION, definition.key, definition.version,
                definition.definition_hash, "technology", 2, percentile,
            )
            for definition in registry.definitions()
            for security_id, percentile in (("a", Decimal("0.75")), ("b", Decimal("0.25")))
        )

        scores = build_model_scores(
            ranks=ranks, formation_date=FORMATION, universe_security_ids=("a", "b"),
            registry=registry, model=model,
        )
        by_security = {score.security_id: score for score in scores}

        self.assertEqual(by_security["a"].predicted_relative_return, Decimal("0.025000000000"))
        self.assertEqual(by_security["b"].predicted_relative_return, Decimal("0.015000000000"))
        self.assertEqual(by_security["a"].display_score, Decimal("100.00"))
        self.assertEqual(by_security["b"].display_score, Decimal("0.00"))
