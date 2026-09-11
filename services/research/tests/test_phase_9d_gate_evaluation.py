from datetime import date
import unittest

from quantrade_research.phase_9d_gate_evaluation import _fold_blocks, coefficient_stability


class Phase9DGateEvaluationTests(unittest.TestCase):
    def test_calendar_month_end_uses_registered_block_not_last_weekly_formation(self) -> None:
        blocks = _fold_blocks({"outer_folds": [{
            "outer_fold": 1,
            "registered_block": ["2024-07-01", "2024-12-31"],
            "validation_formations": ["2024-07-05", "2024-12-27"],
        }]})
        self.assertEqual(blocks[1], (date(2024, 7, 1), date(2024, 12, 31)))

    def test_coefficient_gate_requires_positive_material_value_in_three_fits(self) -> None:
        fits = {
            "outer_folds": [
                {"fit": {"coefficients": [0.2, 0.3]}},
                {"fit": {"coefficients": [0.1, 0.2]}},
                {"fit": {"coefficients": [-0.1, 0.1]}},
                {"fit": {"coefficients": [0.3, 0.0]}},
            ]
        }
        result = coefficient_stability(fits, {
            "minimum_coefficient_absolute_value": 1e-8,
            "minimum_coefficient_positive_outer_fits": 3,
        })
        self.assertTrue(result["families"]["investment_issuance"]["passed"])
        self.assertTrue(result["families"]["profitability_quality"]["passed"])
        self.assertTrue(result["passed"])

    def test_negative_direction_adjusted_coefficients_fail(self) -> None:
        fits = {
            "outer_folds": [
                {"fit": {"coefficients": [-0.2, 0.3]}},
                {"fit": {"coefficients": [-0.1, 0.2]}},
                {"fit": {"coefficients": [-0.1, 0.1]}},
                {"fit": {"coefficients": [-0.3, 0.2]}},
            ]
        }
        result = coefficient_stability(fits, {
            "minimum_coefficient_absolute_value": 1e-8,
            "minimum_coefficient_positive_outer_fits": 3,
        })
        self.assertFalse(result["families"]["investment_issuance"]["passed"])
        self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
