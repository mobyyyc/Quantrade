"""Refit the frozen elastic-net design on the clean monthly development dataset."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path

from .clean_monthly_baseline_panel import FEATURES
from .clean_monthly_model_dataset import load_clean_examples
from .features import baseline_feature_registry
from .monthly_model_comparison import fit_linear_model
from .quality import DataQualityError


MODEL_VERSION = "tier_b_monthly_elastic_net_sec_clean_v3"
FAMILY = "elastic_net"
L1_PENALTY = 0.001
L2_PENALTY = 0.001


def train_clean_final_model(
    *, dataset: Path, manifest: Path, design_artifact: Path, output: Path,
) -> dict[str, object]:
    if output.exists():
        raise DataQualityError("refusing to overwrite immutable clean final model")
    examples, metadata = load_clean_examples(dataset, manifest)
    try:
        design = json.loads(design_artifact.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid frozen design artifact") from error
    if (design.get("family"), design.get("l1_penalty"), design.get("l2_penalty")) != (
        FAMILY, L1_PENALTY, L2_PENALTY,
    ):
        raise DataQualityError("frozen design artifact does not match the approved elastic-net specification")
    if design.get("holdout_used") is not False or design.get("holdout_evaluated") is not False:
        raise DataQualityError("frozen design artifact has exposed holdout evidence")
    model = fit_linear_model(examples, lambda item: item.base, family=FAMILY, l1=L1_PENALTY, l2=L2_PENALTY)
    if not all(math.isfinite(value) for value in (*model.means, *model.scales, *model.coefficients, model.intercept)):
        raise DataQualityError("clean final model contains non-finite parameters")
    registry = baseline_feature_registry()
    artifact = {
        "artifact_schema_version": "research_inference_v3", "model_version": MODEL_VERSION,
        "status": "development_frozen", "protocol_version": "tier_b_monthly_20d_sec_clean_v3",
        "data_capability_tier": "B", "development_only": True,
        "holdout_used": False, "holdout_evaluated": False,
        "family": FAMILY, "l1_penalty": L1_PENALTY, "l2_penalty": L2_PENALTY,
        "feature_registry_hash": registry.registry_hash,
        "feature_columns": [f"{feature}_percentile" for feature in FEATURES],
        "feature_means": list(model.means), "feature_scales": list(model.scales),
        "target_mean": model.intercept, "coefficients": list(model.coefficients),
        "target_column": "benchmark_relative_return",
        "prediction_target": "20-session split-adjusted return relative to SPY",
        "training_example_count": len(examples),
        "training_formation_count": len({item.formation_date for item in examples}),
        "training_start_date": min(item.formation_date for item in examples).isoformat(),
        "training_end_date": max(item.formation_date for item in examples).isoformat(),
        "source_dataset": {
            "key": metadata["dataset_key"], "version": metadata["dataset_version"],
            "content_sha256": metadata["content_sha256"],
            "manifest_sha256": sha256(manifest.read_bytes()).hexdigest(),
            "source_panel_sha256": metadata["source_panel_sha256"],
            "sec_form_scope": metadata["sec_form_scope"],
        },
        "source_design_artifact_sha256": sha256(design_artifact.read_bytes()).hexdigest(),
        "limitations": metadata["limitations"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit the SEC-clean monthly elastic-net model")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--design-artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    artifact = train_clean_final_model(
        dataset=arguments.input, manifest=arguments.manifest,
        design_artifact=arguments.design_artifact, output=arguments.output,
    )
    print(
        f"trained_model={artifact['model_version']}; examples={artifact['training_example_count']}; "
        f"artifact_sha256={sha256(arguments.output.read_bytes()).hexdigest()}; holdout_used=false; deployed=false"
    )


if __name__ == "__main__":
    main()
