"""Freeze a development-only model into a local research inference artifact."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path

from .quality import DataQualityError
from .regularized_training import FEATURE_COLUMNS, TARGET_COLUMN
from .score_run import _dotenv_values


MODEL_VERSION = "tier_b_regularized_linear_development_v1"
PROTOCOL_VERSION = "tier_b_20d_v1"


def serialize_research_inference_artifact(artifact: dict[str, object]) -> bytes:
    """Use canonical UTF-8/LF bytes so the registered digest matches the file."""
    return (json.dumps(artifact, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _feature_registry_hash(dataset: Path) -> str:
    with dataset.open("r", encoding="utf-8", newline="") as handle:
        hashes = {
            row["feature_registry_hash"]
            for row in csv.DictReader(handle)
            if row.get("partition") == "development" and row.get("feature_registry_hash")
        }
    if len(hashes) != 1:
        raise DataQualityError("development dataset must contain exactly one feature registry hash")
    return hashes.pop()


def build_research_inference_artifact(*, experiment_bytes: bytes, feature_registry_hash: str) -> dict[str, object]:
    """Validate the frozen selection artifact and expose only inference essentials."""
    try:
        experiment = json.loads(experiment_bytes)
        model = experiment["final_development_model"]
        selected = experiment["selected_candidate"]
        features = tuple(experiment["feature_columns"])
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid development experiment artifact") from error
    if experiment.get("holdout_used") is not False or experiment.get("holdout_excluded_from_input") is not True:
        raise DataQualityError("research model source must be development-only")
    if experiment.get("target_column") != TARGET_COLUMN or features != FEATURE_COLUMNS:
        raise DataQualityError("research model source feature schema does not match the registered baseline schema")
    expected = ("elastic_net", 0.001, 0.01)
    actual = (model.get("family"), model.get("l1_penalty"), model.get("l2_penalty"))
    selected_actual = (selected.get("family"), selected.get("l1_penalty"), selected.get("l2_penalty"))
    if actual != expected or selected_actual != expected:
        raise DataQualityError("development selection is not the pre-registered elastic-net candidate")
    coefficients = model.get("coefficients")
    means = model.get("feature_means")
    scales = model.get("feature_scales")
    if not all(isinstance(values, list) and len(values) == len(FEATURE_COLUMNS) for values in (coefficients, means, scales)):
        raise DataQualityError("development model has an invalid feature vector shape")
    return {
        "artifact_schema_version": "research_inference_v1",
        "model_version": MODEL_VERSION,
        "status": "research_only",
        "protocol_version": PROTOCOL_VERSION,
        "data_capability_tier": "B",
        "feature_registry_hash": feature_registry_hash,
        "feature_columns": list(FEATURE_COLUMNS),
        "target_column": TARGET_COLUMN,
        "prediction_target": "20-session split-adjusted return relative to SPY",
        "family": model["family"],
        "l1_penalty": model["l1_penalty"],
        "l2_penalty": model["l2_penalty"],
        "feature_means": means,
        "feature_scales": scales,
        "target_mean": model["target_mean"],
        "coefficients": coefficients,
        "source_experiment_sha256": sha256(experiment_bytes).hexdigest(),
        "limitations": [
            "Research-only: this artifact must not alter daily baseline scores, rankings, or public performance claims.",
            "Tier B current-survivors cohort has survivorship bias and static current-sector classifications.",
            "Use only with point-in-time features produced after the model is frozen; forward paper tracking is required for genuine out-of-sample evidence.",
        ],
    }


def record_research_model(*, database_url: str, artifact: dict[str, object], artifact_uri: str, source_experiment_uri: str) -> None:
    """Append immutable model-card and artifact rows; reject any duplicate registration."""
    import psycopg

    created_at = datetime.now(timezone.utc)
    artifact_bytes = serialize_research_inference_artifact(artifact)
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM quantrade.model_cards WHERE model_version = %s", (MODEL_VERSION,))
        if cursor.fetchone() is not None:
            raise DataQualityError(f"research model is already registered: {MODEL_VERSION}")
        cursor.execute(
            """INSERT INTO quantrade.model_cards
                   (model_version, status, protocol_version, feature_registry_hash, data_capability_tier,
                    created_at, purpose, methodology, limitations, evaluation_uri)
               VALUES (%s, 'research_only', %s, %s, 'B', %s, %s, %s, %s::jsonb, %s)
               RETURNING model_card_id""",
            (
                MODEL_VERSION, PROTOCOL_VERSION, artifact["feature_registry_hash"], created_at,
                "Preserve the frozen development-only elastic-net candidate for private quantitative research.",
                "Six point-in-time percentile features with elastic-net regularization selected through three purged chronological development folds.",
                json.dumps(artifact["limitations"]), source_experiment_uri,
            ),
        )
        card_id = cursor.fetchone()[0]
        cursor.execute(
            """INSERT INTO quantrade.model_artifacts
                   (model_card_id, model_version, artifact_uri, artifact_sha256,
                    source_experiment_uri, source_experiment_sha256, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                card_id, MODEL_VERSION, artifact_uri, sha256(artifact_bytes).hexdigest(),
                source_experiment_uri, artifact["source_experiment_sha256"], created_at,
            ),
        )
        connection.commit()


def _settings(env_file: Path):
    from .config import Settings

    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Register the frozen Tier-B research model and write an immutable inference artifact")
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--training-dataset", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    if arguments.artifact.exists():
        raise DataQualityError(f"refusing to overwrite immutable model artifact: {arguments.artifact}")
    experiment_bytes = arguments.experiment.read_bytes()
    artifact = build_research_inference_artifact(
        experiment_bytes=experiment_bytes,
        feature_registry_hash=_feature_registry_hash(arguments.training_dataset),
    )
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    arguments.artifact.parent.mkdir(parents=True, exist_ok=True)
    arguments.artifact.write_bytes(serialize_research_inference_artifact(artifact))
    try:
        record_research_model(
            database_url=settings.database_url,
            artifact=artifact,
            artifact_uri=arguments.artifact.resolve().as_uri(),
            source_experiment_uri=arguments.experiment.resolve().as_uri(),
        )
    except Exception:
        arguments.artifact.unlink(missing_ok=True)
        raise
    print(f"registered_model={MODEL_VERSION}; status=research_only; artifact_sha256={sha256(arguments.artifact.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
