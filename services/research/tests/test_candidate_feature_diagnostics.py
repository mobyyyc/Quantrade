from collections import Counter
from datetime import date
from decimal import Decimal
import unittest

from quantrade_research.candidate_feature_diagnostics import evaluate_candidate_diagnostics
from quantrade_research.features import FeatureRegistry, NEXT_GENERATION_CANDIDATE_DEFINITIONS


DATES = (date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 31))
SECURITIES = tuple(f"security-{index:02d}" for index in range(20))
REGISTRY = FeatureRegistry((NEXT_GENERATION_CANDIDATE_DEFINITIONS[0],))
KEY = NEXT_GENERATION_CANDIDATE_DEFINITIONS[0].key


def ordered(reverse: bool = False) -> dict[str, Decimal]:
    values = list(enumerate(SECURITIES))
    if reverse:
        values.reverse()
    return {security: Decimal(index) / Decimal("19") for index, security in values}


class CandidateFeatureDiagnosticTests(unittest.TestCase):
    def test_accepts_complete_distinct_stable_feature(self) -> None:
        candidates = {day: {KEY: ordered()} for day in DATES}
        baseline = {
            day: {"active": {security: Decimal((index * 7) % 20) / Decimal("19") for index, security in enumerate(SECURITIES)}}
            for day in DATES
        }
        report = evaluate_candidate_diagnostics(
            formation_dates=DATES,
            universe_security_ids=SECURITIES,
            candidate_ranks=candidates,
            baseline_ranks=baseline,
            missingness={KEY: Counter()},
            point_in_time_violations={KEY: 0},
            registry=REGISTRY,
        )[0]
        self.assertTrue(report.accepted)
        self.assertEqual(report.aggregate_coverage, Decimal("1"))
        self.assertEqual(report.median_consecutive_rank_correlation, Decimal("1"))

    def test_rejects_low_coverage_redundancy_instability_and_time_violation(self) -> None:
        partial = dict(list(ordered().items())[:10])
        candidates = {
            DATES[0]: {KEY: partial},
            DATES[1]: {KEY: {security: Decimal("1") - value for security, value in partial.items()}},
            DATES[2]: {KEY: partial},
        }
        baseline = {day: {"active": dict(values[KEY])} for day, values in candidates.items()}
        report = evaluate_candidate_diagnostics(
            formation_dates=DATES,
            universe_security_ids=SECURITIES,
            candidate_ranks=candidates,
            baseline_ranks=baseline,
            missingness={KEY: Counter({"insufficient_history": 30})},
            point_in_time_violations={KEY: 1},
            registry=REGISTRY,
        )[0]
        self.assertFalse(report.accepted)
        self.assertIn("aggregate_coverage_below_90_percent", report.rejection_reasons)
        self.assertIn("monthly_coverage_below_80_percent", report.rejection_reasons)
        self.assertIn("redundant_with_active_feature", report.rejection_reasons)
        self.assertIn("rank_stability_below_0_10", report.rejection_reasons)
        self.assertIn("point_in_time_violation", report.rejection_reasons)


if __name__ == "__main__":
    unittest.main()
