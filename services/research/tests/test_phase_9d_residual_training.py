from datetime import date
import math
import unittest

from quantrade_research.phase_9d_residual_dataset import ResidualExample
from quantrade_research.phase_9d_residual_training import (
    _select_penalty,
    candidate_prediction,
    fit_residual_ridge,
)
from quantrade_research.quality import DataQualityError


def _row(month: str, security: str, features: tuple[float, float], target: float) -> ResidualExample:
    return ResidualExample(
        date.fromisoformat(month + "-01"), month, security, None,
        0.1, target + 0.1, target, features, 1.0, 0.0,
        date.fromisoformat(month + "-20"), security,
    )


class Phase9DResidualTrainingTests(unittest.TestCase):
    def test_ridge_has_no_intercept_and_finite_parameters(self) -> None:
        rows = (
            _row("2023-01", "a", (-1.0, -1.0), -0.2),
            _row("2023-01", "b", (1.0, -1.0), 0.1),
            _row("2023-02", "c", (-1.0, 1.0), -0.1),
            _row("2023-02", "d", (1.0, 1.0), 0.2),
        )
        fit = fit_residual_ridge(rows, penalty=1.0)
        self.assertTrue(all(math.isfinite(value) for value in (*fit.means, *fit.scales, *fit.coefficients)))
        self.assertEqual(fit.predict(fit.means), 0.0)

    def test_candidate_adds_residual_to_anchor(self) -> None:
        rows = (
            _row("2023-01", "a", (-1.0, -1.0), -0.2),
            _row("2023-01", "b", (1.0, -1.0), 0.1),
            _row("2023-02", "c", (-1.0, 1.0), -0.1),
            _row("2023-02", "d", (1.0, 1.0), 0.2),
        )
        fit = fit_residual_ridge(rows, penalty=10.0)
        residual, candidate = candidate_prediction(rows[0], fit)
        self.assertEqual(candidate, rows[0].anchor_centered_rank + residual)

    def test_tie_break_selects_stronger_registered_penalty(self) -> None:
        selected = _select_penalty([
            {"penalty": 1, "mean_monthly_rank_ic": 0.0200},
            {"penalty": 10, "mean_monthly_rank_ic": 0.0190},
            {"penalty": 100, "mean_monthly_rank_ic": 0.0181},
        ])
        self.assertEqual(selected, 100.0)

    def test_unregistered_penalty_is_rejected(self) -> None:
        with self.assertRaisesRegex(DataQualityError, "unregistered"):
            fit_residual_ridge((_row("2023-01", "a", (1.0, 1.0), 0.1),), penalty=0.1)


if __name__ == "__main__":
    unittest.main()
