"""Freeze the winning monthly model design on the cleaned development dataset."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Sequence

from .features import baseline_feature_registry
from .monthly_model_comparison import Example, fit_linear_model, load_examples
from .monthly_model_dataset import BASE_FEATURES
from .quality import DataQualityError


MODEL_VERSION = "tier_b_monthly_elastic_net_clean_v2"
PROTOCOL_VERSION = "tier_b_monthly_20d_sec_scope_v2"
MODEL_KEY = "active_elastic_net"
TRANSFORM = "market"
FAMILY = "elastic_net"
L1_PENALTY = 0.001
L2_PENALTY = 0.001


def _canonical_hash(document: dict[str, object], hash_key: str) -> str:
    payload = dict(document)
    expected = str(payload.pop(hash_key, ""))
    actual = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if expected != actual:
        raise DataQualityError(f"comparison {hash_key} does not match its canonical payload")
    return expected


def validate_winning_specification(
    comparison: dict[str, object], *, dataset_sha256: str,
) -> tuple[str, float, float]:
    """Require the selected design to be the unique modal nested-fold specification."""
    if comparison.get("development_only") is not True or comparison.get("holdout_used") is not False:
        raise DataQualityError("final training requires a development-only comparison")
    if comparison.get("source_dataset_sha256") != dataset_sha256:
        raise DataQualityError("comparison does not use the requested cleaned dataset")
    _canonical_hash(comparison, "result_sha256")
    try:
        fits = [
            item for item in comparison["fits"]
            if item["model_key"] == MODEL_KEY and item["transform"] == TRANSFORM
        ]
    except (KeyError, TypeError) as error:
        raise DataQualityError("comparison lacks winning-model fit records") from error
    if not fits:
        raise DataQualityError("comparison has no winning-model fit records")
    specifications: Counter[tuple[str, float, float]] = Counter()
    for item in fits:
        try:
            tuning = item["tuning"]
            specification = str(tuning["family"]), float(tuning["l1"]), float(tuning["l2"])
        except (KeyError, TypeError, ValueError) as error:
            raise DataQualityError("comparison has an invalid tuning record") from error
        specifications[specification] += 1
    highest = max(specifications.values())
    modal = [item for item, count in specifications.items() if count == highest]
    frozen = FAMILY, L1_PENALTY, L2_PENALTY
    if modal != [frozen]:
        raise DataQualityError("frozen elastic-net specification is not the unique nested-fold mode")
    return frozen


def build_final_artifact(
    *, examples: Sequence[Example], dataset_metadata: dict[str, object],
    dataset_manifest_sha256: str, comparison: dict[str, object], comparison_sha256: str,
) -> dict[str, object]:
    if not examples:
        raise DataQualityError("final training requires development examples")
    if dataset_metadata.get("development_only") is not True or dataset_metadata.get("holdout_used") is not False:
        raise DataQualityError("final training dataset must exclude the holdout")
    dataset_sha256 = str(dataset_metadata.get("content_sha256", ""))
    family, l1, l2 = validate_winning_specification(comparison, dataset_sha256=dataset_sha256)
    model = fit_linear_model(examples, lambda item: item.base, family=family, l1=l1, l2=l2)
    registry = baseline_feature_registry()
    feature_columns = tuple(f"{feature}_percentile" for feature in BASE_FEATURES)
    registered_columns = {f"{definition.key}_percentile" for definition in registry.definitions()}
    if set(feature_columns) != registered_columns:
        raise DataQualityError("winning model features do not match the production feature registry")
    if not all(math.isfinite(value) for value in (*model.means, *model.scales, *model.coefficients, model.intercept)):
        raise DataQualityError("final model contains a non-finite parameter")
    if any(scale <= 0 for scale in model.scales):
        raise DataQualityError("final model contains a nonpositive feature scale")
    dates = sorted({item.formation_date for item in examples})
    return {
        "artifact_schema_version": "research_inference_v2",
        "model_version": MODEL_VERSION,
        "status": "development_frozen",
        "protocol_version": PROTOCOL_VERSION,
        "data_capability_tier": "B",
        "development_only": True,
        "holdout_used": False,
        "holdout_evaluated": False,
        "family": family,
        "l1_penalty": l1,
        "l2_penalty": l2,
        "feature_registry_hash": registry.registry_hash,
        "feature_columns": list(feature_columns),
        "feature_means": [value + 0.5 for value in model.means],
        "feature_scales": list(model.scales),
        "target_mean": model.intercept,
        "coefficients": list(model.coefficients),
        "target_column": "benchmark_relative_return",
        "prediction_target": "20-session split-adjusted return relative to SPY",
        "training_example_count": len(examples),
        "training_formation_count": len(dates),
        "training_start_date": min(dates).isoformat(),
        "training_end_date": max(dates).isoformat(),
        "source_dataset": {
            "key": dataset_metadata["dataset_key"],
            "version": dataset_metadata["dataset_version"],
            "content_sha256": dataset_sha256,
            "manifest_sha256": dataset_manifest_sha256,
            "source_panel_sha256": dataset_metadata["source_panel_sha256"],
            "sec_form_scope": dataset_metadata["sec_form_scope"],
        },
        "source_comparison": {
            "experiment_key": comparison["experiment_key"],
            "experiment_version": comparison["experiment_version"],
            "file_sha256": comparison_sha256,
            "result_sha256": comparison["result_sha256"],
            "selection_rule": "unique modal nested-fold hyperparameter specification",
        },
        "input_transformation": (
            "Training values are centered percentiles; feature means are translated by +0.5 "
            "so inference consumes the production registry's [0,1] percentiles."
        ),
        "limitations": list(dataset_metadata["limitations"]),
    }


def train_final_model(*, dataset: Path, manifest: Path, comparison_path: Path, output: Path) -> dict[str, object]:
    if output.exists():
        raise DataQualityError(f"refusing to overwrite immutable final model artifact: {output}")
    examples, metadata = load_examples(dataset, manifest)
    manifest_bytes = manifest.read_bytes()
    comparison_bytes = comparison_path.read_bytes()
    try:
        comparison = json.loads(comparison_bytes)
    except json.JSONDecodeError as error:
        raise DataQualityError("invalid monthly comparison artifact") from error
    artifact = build_final_artifact(
        examples=examples, dataset_metadata=metadata,
        dataset_manifest_sha256=sha256(manifest_bytes).hexdigest(),
        comparison=comparison, comparison_sha256=sha256(comparison_bytes).hexdigest(),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit the cleaned v2 monthly elastic-net inference artifact")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    artifact = train_final_model(
        dataset=arguments.input, manifest=arguments.manifest,
        comparison_path=arguments.comparison, output=arguments.output,
    )
    digest = sha256(arguments.output.read_bytes()).hexdigest()
    print(
        f"trained_model={artifact['model_version']}; examples={artifact['training_example_count']}; "
        f"artifact_sha256={digest}; holdout_used=false; deployed=false"
    )


if __name__ == "__main__":
    main()
