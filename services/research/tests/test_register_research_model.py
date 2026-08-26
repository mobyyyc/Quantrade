import json
import unittest

from quantrade_research.quality import DataQualityError
from quantrade_research.register_research_model import (
    build_research_inference_artifact,
    serialize_research_inference_artifact,
)


def experiment() -> bytes:
    return json.dumps({
        "holdout_used": False,
        "holdout_excluded_from_input": True,
        "feature_columns": [
            "earnings_yield_ttm_percentile", "median_dollar_volume_20d_percentile",
            "momentum_12_1_percentile", "relative_strength_6m_percentile",
            "return_on_assets_ttm_percentile", "trailing_volatility_60d_percentile",
        ],
        "target_column": "benchmark_relative_return",
        "selected_candidate": {"family": "elastic_net", "l1_penalty": 0.001, "l2_penalty": 0.01},
        "final_development_model": {
            "family": "elastic_net", "l1_penalty": 0.001, "l2_penalty": 0.01,
            "feature_means": [0] * 6, "feature_scales": [1] * 6,
            "target_mean": 0, "coefficients": [0] * 6,
        },
    }, sort_keys=True).encode("utf-8")


class RegisterResearchModelTests(unittest.TestCase):
    def test_builds_research_only_artifact_from_frozen_development_result(self) -> None:
        artifact = build_research_inference_artifact(experiment_bytes=experiment(), feature_registry_hash="a" * 64)
        self.assertEqual(artifact["status"], "research_only")
        self.assertEqual(artifact["model_version"], "tier_b_regularized_linear_development_v1")
        self.assertEqual(len(artifact["coefficients"]), 6)
        self.assertTrue(serialize_research_inference_artifact(artifact).endswith(b"\n"))
        self.assertNotIn(b"\r\n", serialize_research_inference_artifact(artifact))

    def test_rejects_holdout_contaminated_source(self) -> None:
        contaminated = json.loads(experiment())
        contaminated["holdout_used"] = True
        with self.assertRaisesRegex(DataQualityError, "development-only"):
            build_research_inference_artifact(experiment_bytes=json.dumps(contaminated).encode("utf-8"), feature_registry_hash="a" * 64)


if __name__ == "__main__":
    unittest.main()
