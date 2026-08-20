from datetime import date
from decimal import Decimal
import unittest

from quantrade_research.feature_diagnostics import FeatureOutcome, build_feature_diagnostics
from quantrade_research.features import BASELINE_FEATURE_DEFINITIONS, FeatureRegistry
from quantrade_research.quality import DataQualityError


CURRENT_DATE = date(2026, 8, 20)
PRIOR_DATE = date(2026, 7, 31)
REGISTRY = FeatureRegistry(BASELINE_FEATURE_DEFINITIONS[:2])


def outcomes(formation_date: date, values: dict[str, tuple[str | None, str | None]]) -> list[FeatureOutcome]:
    result: list[FeatureOutcome] = []
    for definition in REGISTRY.definitions():
        for security_id, (momentum, relative_strength) in values.items():
            raw_value, reason = (momentum, None) if definition.key == "momentum_12_1" else (relative_strength, None)
            if raw_value is None:
                reason = "insufficient_history"
            result.append(
                FeatureOutcome(
                    security_id, formation_date, definition.key, definition.version,
                    definition.definition_hash, Decimal(raw_value) if raw_value is not None else None, reason,
                )
            )
    return result


class FeatureDiagnosticsTests(unittest.TestCase):
    def test_reports_coverage_missingness_correlation_and_turnover(self) -> None:
        current = outcomes(CURRENT_DATE, {"a": ("3", "6"), "b": ("2", "4"), "c": (None, None)})
        prior = outcomes(PRIOR_DATE, {"a": ("1", "2"), "b": ("4", "8"), "c": (None, None)})
        report = build_feature_diagnostics(
            current,
            formation_date=CURRENT_DATE,
            universe_security_ids={"a", "b", "c"},
            registry=REGISTRY,
            prior_outcomes=prior,
            prior_formation_date=PRIOR_DATE,
            top_n=1,
        )
        self.assertEqual(report.coverage[0].coverage, Decimal("2") / Decimal("3"))
        self.assertEqual(report.missingness[0].reason, "insufficient_history")
        self.assertEqual(report.missingness[0].security_count, 1)
        self.assertEqual(report.correlations[0].paired_security_count, 2)
        self.assertEqual(report.correlations[0].correlation, Decimal("1"))
        self.assertEqual(report.turnover[0].retained_count, 0)
        self.assertEqual(report.turnover[0].turnover, Decimal("1"))

    def test_requires_explicit_outcomes_and_matching_definition_hashes(self) -> None:
        incomplete = outcomes(CURRENT_DATE, {"a": ("3", "6")})[:-1]
        with self.assertRaisesRegex(DataQualityError, "missing explicit"):
            build_feature_diagnostics(
                incomplete,
                formation_date=CURRENT_DATE,
                universe_security_ids={"a"},
                registry=REGISTRY,
            )
        invalid = outcomes(CURRENT_DATE, {"a": ("3", "6")})
        invalid[0] = FeatureOutcome("a", CURRENT_DATE, "momentum_12_1", "v1", "0" * 64, Decimal("3"))
        with self.assertRaisesRegex(DataQualityError, "hash"):
            build_feature_diagnostics(
                invalid,
                formation_date=CURRENT_DATE,
                universe_security_ids={"a"},
                registry=REGISTRY,
            )

    def test_zero_variance_correlation_is_reported_not_invented(self) -> None:
        report = build_feature_diagnostics(
            outcomes(CURRENT_DATE, {"a": ("1", "3"), "b": ("1", "4")}),
            formation_date=CURRENT_DATE,
            universe_security_ids={"a", "b"},
            registry=REGISTRY,
        )
        self.assertIsNone(report.correlations[0].correlation)
        self.assertEqual(report.correlations[0].unavailable_reason, "zero_variance")

    def test_turnover_uses_lower_values_for_lower_is_better_features(self) -> None:
        risk_registry = FeatureRegistry((BASELINE_FEATURE_DEFINITIONS[4],))
        definition = risk_registry.definitions()[0]

        def risk_outcomes(formation_date: date, values: dict[str, str]) -> list[FeatureOutcome]:
            return [
                FeatureOutcome(security_id, formation_date, definition.key, definition.version,
                               definition.definition_hash, Decimal(value))
                for security_id, value in values.items()
            ]

        report = build_feature_diagnostics(
            risk_outcomes(CURRENT_DATE, {"a": "1", "b": "2", "c": "3"}),
            formation_date=CURRENT_DATE,
            universe_security_ids={"a", "b", "c"},
            registry=risk_registry,
            prior_outcomes=risk_outcomes(PRIOR_DATE, {"a": "2", "b": "1", "c": "3"}),
            prior_formation_date=PRIOR_DATE,
            top_n=1,
        )
        self.assertEqual(report.turnover[0].retained_count, 0)


if __name__ == "__main__":
    unittest.main()
