from datetime import date
from hashlib import sha256
import json
import unittest

from quantrade_research.monthly_final_training import (
    MODEL_VERSION, build_final_artifact, validate_winning_specification,
)
from quantrade_research.monthly_model_comparison import Example
from quantrade_research.quality import DataQualityError


def comparison(dataset_hash: str) -> dict[str, object]:
    document: dict[str, object] = {
        "experiment_key": "comparison", "experiment_version": "v1",
        "source_dataset_sha256": dataset_hash, "development_only": True, "holdout_used": False,
        "fits": [
            {"model_key": "active_elastic_net", "transform": "market", "tuning": spec}
            for spec in (
                {"family": "elastic_net", "l1": 0.001, "l2": 0.001},
                {"family": "elastic_net", "l1": 0.0001, "l2": 0.001},
                {"family": "elastic_net", "l1": 0.001, "l2": 0.01},
                {"family": "elastic_net", "l1": 0.001, "l2": 0.001},
            )
        ],
    }
    document["result_sha256"] = sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return document


def example(day: int, offset: float) -> Example:
    values = tuple(offset + index / 100 for index in range(6))
    return Example(
        date(2024, 1, day), date(2024, 2, day), f"security-{day}", values, (), (),
        offset / 10, offset / 10, 0.0, 0.5, 0.1, 0.02,
    )


class MonthlyFinalTrainingTests(unittest.TestCase):
    def test_builds_production_compatible_development_artifact(self) -> None:
        dataset_hash = "a" * 64
        metadata = {
            "dataset_key": "tier_b_monthly_model_development", "dataset_version": "v2",
            "content_sha256": dataset_hash, "source_panel_sha256": "b" * 64,
            "development_only": True, "holdout_used": False,
            "sec_form_scope": ["10-K", "10-Q", "20-F", "40-F", "8-K"],
            "limitations": ["Tier B"],
        }
        artifact = build_final_artifact(
            examples=(example(1, -0.2), example(2, 0.2)), dataset_metadata=metadata,
            dataset_manifest_sha256="c" * 64, comparison=comparison(dataset_hash),
            comparison_sha256="d" * 64,
        )
        self.assertEqual(artifact["model_version"], MODEL_VERSION)
        self.assertEqual(artifact["status"], "development_frozen")
        self.assertFalse(artifact["holdout_used"])
        self.assertEqual(len(artifact["feature_columns"]), 6)
        self.assertTrue(all(item.endswith("_percentile") for item in artifact["feature_columns"]))
        self.assertEqual(artifact["training_example_count"], 2)

    def test_rejects_a_comparison_from_another_dataset(self) -> None:
        with self.assertRaisesRegex(DataQualityError, "requested cleaned dataset"):
            validate_winning_specification(comparison("a" * 64), dataset_sha256="b" * 64)

    def test_rejects_a_nonunique_modal_specification(self) -> None:
        document = comparison("a" * 64)
        document["fits"] = document["fits"][:2]
        payload = dict(document)
        payload.pop("result_sha256")
        document["result_sha256"] = sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with self.assertRaisesRegex(DataQualityError, "unique nested-fold mode"):
            validate_winning_specification(document, dataset_sha256="a" * 64)


if __name__ == "__main__":
    unittest.main()
