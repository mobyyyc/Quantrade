from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from quantrade_research.clean_monthly_development_validation import _assert_final_fit_matches
from quantrade_research.clean_monthly_final_training import FAMILY, L1_PENALTY, L2_PENALTY, MODEL_VERSION
from quantrade_research.monthly_model_comparison import Example, fit_linear_model
from quantrade_research.quality import DataQualityError
from quantrade_research.register_clean_monthly_model import validate_registration_inputs


def examples():
    return tuple(
        Example(
            date(2024, 1, index + 1), date(2024, 2, index + 1), f"security-{index}",
            tuple((index + feature) / 10 for feature in range(6)), (), (),
            (index - 2) / 100, (index - 2) / 100, 0.0, 0.25, 0.0, 0.0,
        )
        for index in range(4)
    )


class CleanModelPromotionTests(unittest.TestCase):
    def test_final_artifact_parameters_must_reproduce_exactly(self) -> None:
        fitted = fit_linear_model(
            examples(), lambda item: item.base,
            family=FAMILY, l1=L1_PENALTY, l2=L2_PENALTY,
        )
        model = {
            "feature_means": list(fitted.means), "feature_scales": list(fitted.scales),
            "target_mean": fitted.intercept, "coefficients": list(fitted.coefficients),
        }

        _assert_final_fit_matches(model, examples())
        model["target_mean"] = fitted.intercept + 0.01
        with self.assertRaisesRegex(DataQualityError, "do not reproduce"):
            _assert_final_fit_matches(model, examples())

    def test_registration_requires_matching_dataset_validation_and_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary) / "dataset.csv"
            dataset.write_text("clean-data\n", encoding="utf-8")
            dataset_hash = sha256(dataset.read_bytes()).hexdigest()
            manifest = {
                "dataset_key": "tier_b_clean_monthly_model_development",
                "dataset_version": "v1", "content_sha256": dataset_hash,
            }
            manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
            artifact = {
                "model_version": MODEL_VERSION, "status": "development_frozen",
                "development_only": True, "holdout_used": False,
                "source_dataset": {
                    "content_sha256": dataset_hash,
                    "manifest_sha256": sha256(manifest_bytes).hexdigest(),
                },
            }
            artifact_bytes = json.dumps(artifact, sort_keys=True).encode()
            validation = {
                "experiment_key": "tier_b_clean_monthly_fixed_model_validation",
                "experiment_version": "v1", "model_version": MODEL_VERSION,
                "development_only": True, "holdout_used": False,
                "source_model_artifact_sha256": sha256(artifact_bytes).hexdigest(),
                "source_dataset_sha256": dataset_hash,
            }
            validation_bytes = json.dumps(validation, sort_keys=True).encode()

            loaded, _ = validate_registration_inputs(
                artifact_bytes=artifact_bytes, validation_bytes=validation_bytes,
                dataset=dataset, manifest_bytes=manifest_bytes,
            )
            self.assertEqual(loaded["model_version"], MODEL_VERSION)

            validation["source_model_artifact_sha256"] = "0" * 64
            with self.assertRaisesRegex(DataQualityError, "does not match"):
                validate_registration_inputs(
                    artifact_bytes=artifact_bytes,
                    validation_bytes=json.dumps(validation).encode(),
                    dataset=dataset, manifest_bytes=manifest_bytes,
                )


if __name__ == "__main__":
    unittest.main()
