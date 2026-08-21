from datetime import date
from decimal import Decimal
import unittest

from quantrade_research.feature_diagnostics import FeatureOutcome
from quantrade_research.features import FeatureValue, baseline_feature_registry
from quantrade_research.quality import DataQualityError
from quantrade_research.score_run import _outcome


class ScoreRunOutcomeTests(unittest.TestCase):
    def test_calculated_value_is_a_available_feature_outcome(self) -> None:
        registry = baseline_feature_registry()
        formation_date = date(2026, 8, 21)
        definition = registry.get("momentum_12_1", "v1")

        outcome = _outcome(
            "security-1", formation_date, registry, "momentum_12_1",
            lambda: FeatureValue("security-1", formation_date, definition.key, definition.version,
                                 definition.definition_hash, Decimal("0.12")),
        )

        self.assertEqual(outcome.value, Decimal("0.12"))
        self.assertIsNone(outcome.unavailable_reason)

    def test_data_failure_is_an_explicit_unavailable_feature_outcome(self) -> None:
        outcome = _outcome(
            "security-1", date(2026, 8, 21), baseline_feature_registry(), "momentum_12_1",
            lambda: (_ for _ in ()).throw(DataQualityError("missing completed sessions")),
        )

        self.assertIsNone(outcome.value)
        self.assertEqual(outcome.unavailable_reason, "data_unavailable:missing completed sessions")
