import unittest
from datetime import date
from decimal import Decimal

from quantrade_research.model_health import (
    build_alerts,
    feature_health,
    population_stability_index,
    rank_health,
)


class ModelHealthTests(unittest.TestCase):
    def test_population_stability_is_zero_for_identical_distributions(self) -> None:
        values = tuple(Decimal(index) / Decimal(1000) for index in range(1000))
        self.assertEqual(population_stability_index(values, values), Decimal("0E-16"))

    def test_feature_health_flags_missingness_and_distribution_drift(self) -> None:
        current = tuple(Decimal("0.95") for _ in range(100))
        reference = tuple(Decimal("0.05") for _ in range(1000))
        metric = feature_health(
            feature_key="momentum_12_1", feature_version="v1",
            definition_hash="a" * 64, cohort_size=120,
            current=current, reference=reference,
        )
        self.assertEqual(metric.available_count, 100)
        self.assertEqual(metric.unavailable_count, 20)
        self.assertEqual(metric.status, "critical")
        self.assertGreater(metric.population_stability_index, Decimal("0.25"))

    def test_rank_health_tracks_top_twenty_churn_and_normalized_movement(self) -> None:
        current = {str(index): index for index in range(1, 31)}
        previous = {str(index): 31 - index for index in range(1, 31)}
        result = rank_health(current, previous, date(2026, 9, 9))
        self.assertEqual(result.previous_score_date, date(2026, 9, 9))
        self.assertEqual(result.top_20_churn_ratio, Decimal("0.5"))
        self.assertGreater(result.mean_normalized_rank_change, Decimal("0.15"))
        reordered = rank_health(dict(reversed(tuple(current.items()))), dict(reversed(tuple(previous.items()))), date(2026, 9, 9))
        self.assertEqual(result, reordered)

    def test_hash_and_lineage_failures_are_critical_and_never_trigger_actions(self) -> None:
        alerts = build_alerts(
            coverage_ratio=Decimal("0.99"), metrics=(),
            ranks=rank_health({}, {}, None), artifact_hash_matches=False,
            registry_hash_matches=False, explanation_lineage_matches=False,
            readiness_available=True,
        )
        self.assertEqual(len(alerts), 3)
        self.assertTrue(all(item.severity == "critical" for item in alerts))
        self.assertEqual(
            {item.code for item in alerts},
            {"artifact_hash_mismatch", "registry_hash_mismatch", "explanation_lineage_mismatch"},
        )


if __name__ == "__main__":
    unittest.main()
