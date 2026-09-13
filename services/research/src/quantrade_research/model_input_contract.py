"""Register immutable input metadata from a verified model artifact."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from math import isfinite
from pathlib import Path

from .active_model import ActiveModelArtifact, load_active_model
from .features import FeatureRegistry, baseline_feature_registry
from .quality import DataQualityError
from .score_run import _dotenv_values


@dataclass(frozen=True, slots=True)
class ModelInputContract:
    input_ordinal: int
    model_column: str
    feature_key: str
    feature_version: str
    definition_hash: str
    display_name: str
    coefficient: float
    is_active: bool


def record_feature_definitions(cursor, registry: FeatureRegistry) -> int:
    """Insert missing immutable definitions and reject conflicting catalog rows."""
    inserted = 0
    for definition in registry.definitions():
        cursor.execute(
            """INSERT INTO quantrade.feature_definitions
                   (feature_key, feature_version, family, direction, display_name,
                    description, formula, required_inputs, as_of_rule, definition_hash)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
               ON CONFLICT (feature_key, feature_version) DO NOTHING""",
            (
                definition.key, definition.version, definition.family,
                definition.direction, definition.display_name, definition.description,
                definition.formula, json.dumps(definition.required_inputs),
                definition.as_of_rule, definition.definition_hash,
            ),
        )
        inserted += cursor.rowcount
        cursor.execute(
            """SELECT family, direction, display_name, description, formula,
                      required_inputs, as_of_rule, definition_hash
               FROM quantrade.feature_definitions
               WHERE feature_key = %s AND feature_version = %s""",
            (definition.key, definition.version),
        )
        row = cursor.fetchone()
        expected = (
            definition.family, definition.direction, definition.display_name,
            definition.description, definition.formula, list(definition.required_inputs),
            definition.as_of_rule, definition.definition_hash,
        )
        if row is None or (
            str(row[0]), str(row[1]), str(row[2]), str(row[3]), str(row[4]),
            list(row[5]), str(row[6]), str(row[7]),
        ) != expected:
            raise DataQualityError(
                f"stored feature definition conflicts with registry: "
                f"{definition.key}@{definition.version}"
            )
    return inserted


def build_model_input_contracts(
    model: ActiveModelArtifact, registry: FeatureRegistry,
) -> tuple[ModelInputContract, ...]:
    if model.feature_registry_hash != registry.registry_hash:
        raise DataQualityError("model input contract registry does not match the artifact")
    definitions = {definition.key: definition for definition in registry.definitions()}
    contracts: list[ModelInputContract] = []
    for ordinal, (column, coefficient) in enumerate(
        zip(model.feature_columns, model.coefficients, strict=True), start=1,
    ):
        if not column.endswith("_percentile"):
            raise DataQualityError(f"model input is not a percentile column: {column}")
        if not isfinite(coefficient):
            raise DataQualityError(f"model input coefficient is not finite: {column}")
        feature_key = column.removesuffix("_percentile")
        definition = definitions.get(feature_key)
        if definition is None:
            raise DataQualityError(f"model input has no registered definition: {feature_key}")
        contracts.append(ModelInputContract(
            ordinal,
            column,
            feature_key,
            definition.version,
            definition.definition_hash,
            definition.display_name,
            coefficient,
            coefficient != 0.0,
        ))
    return tuple(contracts)


def record_model_input_contracts(
    cursor, *, model: ActiveModelArtifact, registry: FeatureRegistry,
) -> int:
    expected = build_model_input_contracts(model, registry)
    cursor.execute(
        """SELECT input_ordinal, model_column, feature_key, feature_version,
                  definition_hash, display_name, coefficient, is_active
           FROM quantrade.model_input_contracts
           WHERE model_version = %s
           ORDER BY input_ordinal""",
        (model.model_version,),
    )
    existing = tuple(
        ModelInputContract(
            int(row[0]), str(row[1]), str(row[2]), str(row[3]), str(row[4]),
            str(row[5]), float(row[6]), bool(row[7]),
        )
        for row in cursor.fetchall()
    )
    if existing:
        if existing != expected:
            raise DataQualityError(
                f"stored input contract conflicts with model artifact: {model.model_version}"
            )
        return 0
    cursor.executemany(
        """INSERT INTO quantrade.model_input_contracts
               (model_version, input_ordinal, model_column, feature_key,
                feature_version, definition_hash, display_name, coefficient, is_active)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        [
            (
                model.model_version, contract.input_ordinal, contract.model_column,
                contract.feature_key, contract.feature_version, contract.definition_hash,
                contract.display_name, contract.coefficient, contract.is_active,
            )
            for contract in expected
        ],
    )
    return len(expected)


def main() -> None:
    parser = argparse.ArgumentParser(description="Register the active model's immutable input contract")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    database_url = _dotenv_values(arguments.env_file).get("DATABASE_URL")
    if not database_url:
        raise DataQualityError("DATABASE_URL is required")
    model = load_active_model(database_url)
    registry = baseline_feature_registry()
    import psycopg
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        definitions_inserted = record_feature_definitions(cursor, registry)
        inserted = record_model_input_contracts(cursor, model=model, registry=registry)
        connection.commit()
    print(
        f"model={model.model_version}; registered_inputs={len(model.feature_columns)}; "
        f"active_inputs={sum(value != 0.0 for value in model.coefficients)}; "
        f"definitions_inserted={definitions_inserted}; inputs_inserted={inserted}"
    )


if __name__ == "__main__":
    main()
