from datetime import date
import unittest

from quantrade_research.active_model import ActiveModelArtifact
from quantrade_research.phase_9c_model_comparison import LinearFit
from quantrade_research.phase_9d_residual_dataset import (
    _aggregate_tuning_records,
    _centered_ranks,
    _fit_as_artifact,
    _predict_full_universe,
    _select_from_records,
)
from quantrade_research.phase_9c_model_comparison import Example


class Phase9DResidualDatasetTests(unittest.TestCase):
    def test_fold_local_fit_ignores_only_its_exact_zero_inputs(self) -> None:
        formation = date(2024, 1, 5)
        fit = LinearFit(
            (0.5,) * 6, (1.0,) * 6, 0.0,
            (1.0, 0.0, -0.5, -0.0, 0.0, 0.25),
        )
        values = {
            "momentum_12_1_percentile": 0.8,
            "relative_strength_6m_percentile": None,
            "trailing_volatility_60d_percentile": 0.2,
            "median_dollar_volume_20d_percentile": None,
            "earnings_yield_ttm_percentile": None,
            "return_on_assets_ttm_percentile": 0.6,
        }
        predictions = _predict_full_universe(
            fit=fit, formations=(formation,), by_formation={formation: ("a",)},
            ranked_inputs={(formation, "a"): values},
        )
        self.assertIn((formation, "a"), predictions)

        nonzero = LinearFit(fit.means, fit.scales, fit.target_mean, (1.0, 1e-300, -0.5, 0, 0, 0.25))
        self.assertEqual(
            _predict_full_universe(
                fit=nonzero, formations=(formation,), by_formation={formation: ("a",)},
                ranked_inputs={(formation, "a"): values},
            ),
            {},
        )

    def test_anchor_rank_is_tie_aware_and_centered(self) -> None:
        formation = date(2024, 1, 5)
        result = _centered_ranks({
            (formation, "a"): 1.0,
            (formation, "b"): 2.0,
            (formation, "c"): 2.0,
        })
        self.assertEqual(result[formation, "a"], -1.0)
        self.assertEqual(result[formation, "b"], 0.5)
        self.assertEqual(result[formation, "c"], 0.5)

    def test_configuration_selection_uses_registered_stronger_tie_break(self) -> None:
        selected = _select_from_records([
            {"configuration": (0.0001, 0.001), "mean_monthly_rank_ic": 0.02},
            {"configuration": (0.001, 0.1), "mean_monthly_rank_ic": 0.019},
        ])
        self.assertEqual(selected, (0.001, 0.1))

    def test_fit_adapter_preserves_serialized_coefficients(self) -> None:
        fit = LinearFit((0.0,) * 6, (1.0,) * 6, 0.1, (1.0, -0.0, 0, 0, 0, 0))
        artifact: ActiveModelArtifact = _fit_as_artifact(fit)
        self.assertEqual(artifact.coefficients, fit.coefficients)
        self.assertEqual(artifact.target_mean, fit.target_mean)

    def test_anchor_tuning_excludes_outcomes_not_completed_before_prediction(self) -> None:
        early = Example(date(2022, 10, 7), "2022-10", "a", 0.1, 0.01, 1.0, (0.0,), "a")
        early_peer = Example(date(2022, 10, 7), "2022-10", "b", 0.2, 0.02, 1.0, (0.0,), "b")
        late = Example(date(2022, 12, 30), "2022-12", "c", 0.3, 0.03, 1.0, (0.0,), "c")
        configurations = ((0.0001, 0.001), (0.001, 0.1))
        predictions = {
            configuration: {
                (early.formation_date, early.security_id): 0.1,
                (early_peer.formation_date, early_peer.security_id): 0.2,
                (late.formation_date, late.security_id): 0.3,
            }
            for configuration in configurations
        }
        from quantrade_research import phase_9d_residual_dataset as module
        original = module.ELASTIC_GRID
        module.ELASTIC_GRID = configurations
        try:
            records = _aggregate_tuning_records(
                ((predictions, (early, early_peer, late)),),
                outcome_dates={
                    (early.formation_date, early.security_id): date(2022, 11, 7),
                    (early_peer.formation_date, early_peer.security_id): date(2022, 11, 7),
                    (late.formation_date, late.security_id): date(2023, 1, 31),
                },
                available_before=date(2023, 1, 6),
            )
        finally:
            module.ELASTIC_GRID = original
        self.assertEqual({record["paired_row_count"] for record in records}, {2})
        self.assertEqual({record["latest_outcome_used"] for record in records}, {"2022-11-07"})


if __name__ == "__main__":
    unittest.main()
