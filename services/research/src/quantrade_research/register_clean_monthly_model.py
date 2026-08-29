"""Register an existing frozen SEC-clean model without rewriting its artifact."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path

from .clean_monthly_development_validation import EXPERIMENT_KEY, EXPERIMENT_VERSION
from .clean_monthly_final_training import MODEL_VERSION
from .clean_monthly_model_dataset import DATASET_KEY, DATASET_VERSION
from .quality import DataQualityError
from .score_run import _dotenv_values


def validate_registration_inputs(
    *, artifact_bytes: bytes, validation_bytes: bytes, dataset: Path, manifest_bytes: bytes,
) -> tuple[dict[str, object], dict[str, object]]:
    try:
        artifact = json.loads(artifact_bytes)
        validation = json.loads(validation_bytes)
        manifest = json.loads(manifest_bytes)
    except json.JSONDecodeError as error:
        raise DataQualityError("clean model registration input is not valid JSON") from error
    if artifact.get("model_version") != MODEL_VERSION or artifact.get("status") != "development_frozen":
        raise DataQualityError("registration requires the frozen SEC-clean model")
    if artifact.get("development_only") is not True or artifact.get("holdout_used") is not False:
        raise DataQualityError("registration model is not development-only")
    if (manifest.get("dataset_key"), manifest.get("dataset_version")) != (DATASET_KEY, DATASET_VERSION):
        raise DataQualityError("registration requires the clean development dataset manifest")
    dataset_hash = sha256(dataset.read_bytes()).hexdigest()
    if dataset_hash != manifest.get("content_sha256") or artifact.get("source_dataset", {}).get("content_sha256") != dataset_hash:
        raise DataQualityError("registration dataset lineage does not match the model")
    if artifact.get("source_dataset", {}).get("manifest_sha256") != sha256(manifest_bytes).hexdigest():
        raise DataQualityError("registration manifest lineage does not match the model")
    if (validation.get("experiment_key"), validation.get("experiment_version")) != (EXPERIMENT_KEY, EXPERIMENT_VERSION):
        raise DataQualityError("registration requires the clean development validation")
    if validation.get("model_version") != MODEL_VERSION or validation.get("source_model_artifact_sha256") != sha256(artifact_bytes).hexdigest():
        raise DataQualityError("registration validation does not match the model artifact")
    if validation.get("source_dataset_sha256") != dataset_hash:
        raise DataQualityError("registration validation does not match the clean dataset")
    if validation.get("development_only") is not True or validation.get("holdout_used") is not False:
        raise DataQualityError("registration validation is not development-only")
    return artifact, validation


def record_clean_model(
    *, database_url: str, artifact: dict[str, object], artifact_bytes: bytes,
    artifact_uri: str, validation_uri: str, validation_bytes: bytes,
) -> None:
    import psycopg

    created_at = datetime.now(timezone.utc)
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM quantrade.model_cards WHERE model_version = %s", (MODEL_VERSION,))
        if cursor.fetchone() is not None:
            raise DataQualityError(f"clean research model is already registered: {MODEL_VERSION}")
        cursor.execute(
            """INSERT INTO quantrade.model_cards
                   (model_version, status, protocol_version, feature_registry_hash, data_capability_tier,
                    created_at, purpose, methodology, limitations, evaluation_uri)
               VALUES (%s, 'research_only', %s, %s, 'B', %s, %s, %s, %s::jsonb, %s)
               RETURNING model_card_id""",
            (
                MODEL_VERSION, artifact["protocol_version"], artifact["feature_registry_hash"], created_at,
                "Private-beta ranking with the frozen SEC-clean monthly elastic-net model.",
                "Six point-in-time percentile features; fixed elastic-net specification validated on four purged chronological development folds.",
                json.dumps(artifact["limitations"]), validation_uri,
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
                validation_uri, sha256(validation_bytes).hexdigest(), created_at,
            ),
        )
        connection.commit()


def _settings(env_file: Path):
    from .config import Settings

    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Register the frozen SEC-clean monthly model")
    parser.add_argument("--model-artifact", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--training-dataset", type=Path, required=True)
    parser.add_argument("--training-manifest", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    artifact_bytes = arguments.model_artifact.read_bytes()
    validation_bytes = arguments.validation.read_bytes()
    artifact, _ = validate_registration_inputs(
        artifact_bytes=artifact_bytes, validation_bytes=validation_bytes,
        dataset=arguments.training_dataset, manifest_bytes=arguments.training_manifest.read_bytes(),
    )
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    record_clean_model(
        database_url=settings.database_url, artifact=artifact, artifact_bytes=artifact_bytes,
        artifact_uri=arguments.model_artifact.resolve().as_uri(),
        validation_uri=arguments.validation.resolve().as_uri(), validation_bytes=validation_bytes,
    )
    print(f"registered_model={MODEL_VERSION}; status=research_only; artifact_unchanged=true")


if __name__ == "__main__":
    main()
