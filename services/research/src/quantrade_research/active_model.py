"""Immutable private-beta model deployment and artifact loading."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import unquote, urlparse

from .quality import DataQualityError


def _dotenv_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True, slots=True)
class ActiveModelArtifact:
    model_version: str
    protocol_version: str
    feature_registry_hash: str
    feature_columns: tuple[str, ...]
    feature_means: tuple[float, ...]
    feature_scales: tuple[float, ...]
    target_mean: float
    coefficients: tuple[float, ...]


def _path_from_file_uri(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise DataQualityError("active model artifact must use a local file URI")
    return Path(unquote(parsed.path).lstrip("/"))


def load_active_model(database_url: str) -> ActiveModelArtifact:
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT deployment.model_version, artifact.artifact_uri, artifact.artifact_sha256
               FROM quantrade.model_deployments deployment
               JOIN quantrade.model_artifacts artifact ON artifact.model_version = deployment.model_version
               ORDER BY deployment.deployed_at DESC LIMIT 1"""
        )
        row = cursor.fetchone()
    if row is None:
        raise DataQualityError("no private-beta model deployment is active")
    model_version, artifact_uri, expected_hash = (str(value) for value in row)
    path = _path_from_file_uri(artifact_uri)
    try:
        payload = path.read_bytes()
        document = json.loads(payload)
    except (OSError, json.JSONDecodeError) as error:
        raise DataQualityError("active model artifact is unreadable") from error
    if sha256(payload).hexdigest() != expected_hash or document.get("model_version") != model_version:
        raise DataQualityError("active model artifact does not match its immutable registry record")
    try:
        columns = tuple(str(value) for value in document["feature_columns"])
        means = tuple(float(value) for value in document["feature_means"])
        scales = tuple(float(value) for value in document["feature_scales"])
        coefficients = tuple(float(value) for value in document["coefficients"])
        target_mean = float(document["target_mean"])
        registry_hash = str(document["feature_registry_hash"])
        protocol = str(document["protocol_version"])
    except (KeyError, TypeError, ValueError) as error:
        raise DataQualityError("active model artifact has an invalid inference schema") from error
    if not columns or not (len(columns) == len(means) == len(scales) == len(coefficients)) or any(scale <= 0 for scale in scales):
        raise DataQualityError("active model artifact has invalid feature vectors")
    return ActiveModelArtifact(model_version, protocol, registry_hash, columns, means, scales, target_mean, coefficients)


def deploy_model(*, database_url: str, model_version: str, approval_evidence_uri: str) -> None:
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM quantrade.model_artifacts WHERE model_version = %s", (model_version,))
        if cursor.fetchone() is None:
            raise DataQualityError(f"model artifact is not registered: {model_version}")
        cursor.execute(
            """INSERT INTO quantrade.model_deployments
                   (model_version, approval_scope, approval_evidence_uri, deployed_by)
               VALUES (%s, 'private_beta', %s, 'local_owner')""",
            (model_version, approval_evidence_uri),
        )
        connection.commit()


def main() -> None:
    from .config import Settings

    parser = argparse.ArgumentParser(description="Deploy one approved private-beta research model")
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--approval-evidence", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    if not arguments.approval_evidence.exists():
        raise DataQualityError("approval evidence file is required")
    values = dict(__import__("os").environ)
    values.update(_dotenv_values(arguments.env_file))
    settings = Settings.from_environment(values)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    deploy_model(database_url=settings.database_url, model_version=arguments.model_version,
                 approval_evidence_uri=arguments.approval_evidence.resolve().as_uri())
    print(f"active_model={arguments.model_version}; scope=private_beta")


if __name__ == "__main__":
    main()
