"""Validate the frozen SEC-clean model on purged development folds only."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path

from .clean_monthly_final_training import FAMILY, L1_PENALTY, L2_PENALTY, MODEL_VERSION
from .clean_monthly_model_dataset import load_clean_examples
from .monthly_model_comparison import OUTER_BLOCKS, Prediction, fit_linear_model, metrics
from .quality import DataQualityError


EXPERIMENT_KEY = "tier_b_clean_monthly_fixed_model_validation"
EXPERIMENT_VERSION = "v1"


def _assert_final_fit_matches(model: dict[str, object], examples) -> None:
    fitted = fit_linear_model(
        examples, lambda item: item.base, family=FAMILY, l1=L1_PENALTY, l2=L2_PENALTY,
    )
    try:
        expected = (
            tuple(float(value) for value in model["feature_means"]),
            tuple(float(value) for value in model["feature_scales"]),
            float(model["target_mean"]),
            tuple(float(value) for value in model["coefficients"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise DataQualityError("clean model has an invalid fitted parameter schema") from error
    actual = (fitted.means, fitted.scales, fitted.intercept, fitted.coefficients)
    if any(
        len(left) != len(right) or any(not math.isclose(a, b, rel_tol=0, abs_tol=1e-15) for a, b in zip(left, right))
        for left, right in ((actual[0], expected[0]), (actual[1], expected[1]), (actual[3], expected[3]))
    ) or not math.isclose(actual[2], expected[2], rel_tol=0, abs_tol=1e-15):
        raise DataQualityError("clean model parameters do not reproduce from the development dataset")


def validate_frozen_clean_model(
    *, dataset: Path, manifest: Path, model_artifact: Path, output: Path,
) -> dict[str, object]:
    if output.exists():
        raise DataQualityError("refusing to overwrite immutable clean development validation")
    examples, metadata = load_clean_examples(dataset, manifest)
    model_bytes = model_artifact.read_bytes()
    try:
        model = json.loads(model_bytes)
    except (OSError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid clean model artifact") from error
    if model.get("model_version") != MODEL_VERSION:
        raise DataQualityError("unexpected clean model version")
    if (model.get("family"), model.get("l1_penalty"), model.get("l2_penalty")) != (
        FAMILY, L1_PENALTY, L2_PENALTY,
    ):
        raise DataQualityError("clean model does not use the frozen specification")
    if model.get("holdout_used") is not False or model.get("holdout_evaluated") is not False:
        raise DataQualityError("clean model artifact is not holdout-naive")
    if model.get("source_dataset", {}).get("content_sha256") != metadata["content_sha256"]:
        raise DataQualityError("clean model and development dataset do not match")
    _assert_final_fit_matches(model, examples)

    predictions: list[Prediction] = []
    folds: list[dict[str, object]] = []
    for fold, (start, end) in enumerate(OUTER_BLOCKS, start=1):
        validation = tuple(item for item in examples if start <= item.formation_date <= end)
        if not validation:
            raise DataQualityError(f"clean development fold {fold} has no validation examples")
        validation_start = min(item.formation_date for item in validation)
        training = tuple(item for item in examples if item.outcome_date < validation_start)
        if not training:
            raise DataQualityError(f"clean development fold {fold} has no purged training examples")
        fitted = fit_linear_model(
            training, lambda item: item.base, family=FAMILY, l1=L1_PENALTY, l2=L2_PENALTY,
        )
        fold_predictions = tuple(
            Prediction(
                "frozen_elastic_net", "base", fold, item.formation_date, item.security_id,
                fitted.predict(item.base), item.target, item.security_return,
                item.benchmark_return, "development_only",
            )
            for item in validation
        )
        predictions.extend(fold_predictions)
        fold_metrics = metrics(fold_predictions)
        folds.append({
            "fold": fold,
            "training_end": max(item.formation_date for item in training).isoformat(),
            "validation_start": validation_start.isoformat(),
            "validation_end": max(item.formation_date for item in validation).isoformat(),
            "training_rows": len(training), "validation_rows": len(validation),
            "validation_formations": len({item.formation_date for item in validation}),
            "mean_monthly_rank_ic": fold_metrics["mean_monthly_rank_ic"],
            "top20_relative_return_after_25bps": fold_metrics["top20_relative_return_after_cost"]["25"],
        })
    result: dict[str, object] = {
        "experiment_key": EXPERIMENT_KEY, "experiment_version": EXPERIMENT_VERSION,
        "status": "development_validation_complete", "model_version": MODEL_VERSION,
        "development_only": True, "holdout_used": False, "holdout_evaluated": False,
        "post_holdout_governance_only": True,
        "source_dataset_sha256": metadata["content_sha256"],
        "source_dataset_manifest_sha256": sha256(manifest.read_bytes()).hexdigest(),
        "source_model_artifact_sha256": sha256(model_bytes).hexdigest(),
        "frozen_specification": {"family": FAMILY, "l1": L1_PENALTY, "l2": L2_PENALTY},
        "label_overlap_purge": True, "folds": folds,
        "aggregate_metrics": metrics(tuple(predictions)),
        "limitations": [
            *metadata["limitations"],
            "This validation was generated after the historical holdout had already been consumed and did not tune or alter the frozen model.",
        ],
    }
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"))
    result["result_sha256"] = sha256(canonical.encode()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the frozen clean model on development folds only")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = validate_frozen_clean_model(
        dataset=arguments.input, manifest=arguments.manifest,
        model_artifact=arguments.model_artifact, output=arguments.output,
    )
    print(
        f"development_folds={len(result['folds'])}; model={result['model_version']}; "
        f"holdout_used=false; model_unchanged=true"
    )


if __name__ == "__main__":
    main()
