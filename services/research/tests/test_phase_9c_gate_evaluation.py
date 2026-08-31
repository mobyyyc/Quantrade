from datetime import date
import unittest

from quantrade_research.phase_9c_gate_evaluation import (
    PredictionRow,
    coefficient_sign_stability,
    consecutive_rank_stability,
    moving_block_bootstrap,
)


class Phase9CGateEvaluationTests(unittest.TestCase):
    def test_moving_block_bootstrap_is_deterministic_and_paired(self) -> None:
        values = (-0.02, 0.01, 0.03, 0.04, -0.01, 0.02)
        first = moving_block_bootstrap(values, seed=41, resamples=200, block_length=3)
        second = moving_block_bootstrap(values, seed=41, resamples=200, block_length=3)
        self.assertEqual(first, second)
        self.assertAlmostEqual(first["observed_effect"], sum(values) / len(values))
        self.assertEqual(first["resamples"], 200)

    def test_consecutive_rank_stability_uses_shared_security_ids(self) -> None:
        rows = []
        for formation, reverse in ((date(2024, 1, 5), False), (date(2024, 1, 12), False)):
            for index in range(20):
                value = float(19 - index if reverse else index)
                rows.append(PredictionRow(
                    "candidate", 1, formation, "2024-01", f"s{index:02d}", value,
                    value, value / 100, f"hash-{index}",
                ))
        result = consecutive_rank_stability(rows)
        self.assertEqual(result["comparison_count"], 1)
        self.assertAlmostEqual(result["mean_spearman"], 1.0)

    def test_coefficient_sign_gate_requires_three_of_four_fits_for_every_family(self) -> None:
        fits = {
            "fits": [
                {"candidate": {"coefficients": [1, 1, 1, 1, 1, 1]}},
                {"candidate": {"coefficients": [1, 1, 1, 1, 1, -1]}},
                {"candidate": {"coefficients": [1, 1, 1, 1, -1, 1]}},
                {"candidate": {"coefficients": [1, 1, 1, 1, -1, -1]}},
            ]
        }
        result = coefficient_sign_stability(fits, "candidate")
        self.assertFalse(result["passed"])
        self.assertTrue(result["families"]["momentum_trend"]["passed"])
        self.assertFalse(result["families"]["investment_issuance"]["passed"])


if __name__ == "__main__":
    unittest.main()
