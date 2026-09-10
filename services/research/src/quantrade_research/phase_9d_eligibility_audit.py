"""Audit exact-zero active-model eligibility without changing live scoring."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import date
import gzip
from hashlib import sha256
import json
from pathlib import Path
import struct
from typing import Mapping, Sequence

from .active_model import ActiveModelArtifact, _path_from_file_uri, load_active_model
from .model_eligibility import evaluate_model_inputs, required_model_columns
from .phase_9c_model_comparison import (
    ACTIVE_DIRECTIONS,
    ACTIVE_MODEL_COLUMNS,
    _canonical_hash,
    _load_active_raw_panel,
    _load_static_sectors_and_liquidity,
    _sha256_file,
    _tie_percentiles,
)
from .quality import DataQualityError
from .score_run import _dotenv_values


AUDIT_KEY = "phase_9d_exact_zero_eligibility_audit"
AUDIT_VERSION = "v1"
HISTORICAL_DECISION_CONTRACT = "historical_replay_2000_toronto_v1"
LIVE_DECISION_CONTRACT = "live_after_validation_v1"


def _load_registration(path: Path) -> dict[str, object]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid Phase 9D registration") from error
    payload = dict(document)
    recorded = payload.pop("registration_sha256", None)
    if _canonical_hash(payload) != recorded:
        raise DataQualityError("Phase 9D registration hash is invalid")
    return document


def _validate_anchor(
    model: ActiveModelArtifact, registration: Mapping[str, object], *, artifact_sha256: str,
) -> None:
    anchor = registration.get("anchor")
    if not isinstance(anchor, dict):
        raise DataQualityError("Phase 9D registration has no anchor")
    expected = {
        "active_model_version": model.model_version,
        "active_feature_registry_sha256": model.feature_registry_hash,
        "feature_columns": list(model.feature_columns),
        "serialized_coefficients": list(model.coefficients),
        "active_artifact_sha256": artifact_sha256,
    }
    mismatches = [key for key, value in expected.items() if anchor.get(key) != value]
    if mismatches:
        raise DataQualityError("active model differs from the frozen Phase 9D anchor: " + ",".join(mismatches))
    if tuple(model.feature_columns) != ACTIVE_MODEL_COLUMNS:
        raise DataQualityError("active model input order differs from the audited replay")


def _panel_index(panel: Path) -> tuple[set[tuple[date, str]], dict[date, tuple[str, ...]]]:
    keys: set[tuple[date, str]] = set()
    by_formation: dict[date, list[str]] = defaultdict(list)
    with gzip.open(panel, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"formation_date", "security_id"} <= set(reader.fieldnames):
            raise DataQualityError("Phase 9C feature panel has an unexpected schema")
        for row in reader:
            formation = date.fromisoformat(row["formation_date"])
            key = formation, row["security_id"]
            if key in keys:
                raise DataQualityError("Phase 9C feature panel contains duplicate rows")
            keys.add(key)
            by_formation[formation].append(row["security_id"])
    return keys, {key: tuple(sorted(values)) for key, values in by_formation.items()}


def _validate_panel(panel: Path) -> dict[str, object]:
    manifest_path = panel.with_suffix("").with_suffix(".json")
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid Phase 9C feature-panel manifest") from error
    if document.get("panel_key") != "phase_9c_weekly_feature_panel" or document.get("panel_version") != "v1":
        raise DataQualityError("unexpected Phase 9C feature panel")
    if document.get("passed") is not True or document.get("holdout_used") is not False:
        raise DataQualityError("Phase 9C feature panel is not approved development data")
    if _sha256_file(panel) != document.get("panel_file_sha256"):
        raise DataQualityError("Phase 9C feature panel does not match its manifest")
    payload = dict(document)
    recorded = payload.pop("report_hash", None)
    if _canonical_hash(payload) != recorded:
        raise DataQualityError("Phase 9C feature-panel report hash is invalid")
    return document


def _rank_active_inputs(
    *,
    raw: Mapping[tuple[date, str], list[float | None]],
    by_formation: Mapping[date, Sequence[str]],
    sectors: Mapping[str, str],
    active_values: Mapping[tuple[date, str], tuple[float | None, float | None, float | None]],
) -> dict[tuple[date, str], dict[str, float | None]]:
    result: dict[tuple[date, str], dict[str, float | None]] = {}
    for formation, security_ids in sorted(by_formation.items()):
        for security_id in security_ids:
            liquidity, earnings_yield, return_on_assets = active_values[
                formation, security_id
            ]
            raw[formation, security_id][3] = liquidity
            raw[formation, security_id][4] = earnings_yield
            raw[formation, security_id][5] = return_on_assets
        ranks: list[dict[str, float]] = []
        for column_index, direction in enumerate(ACTIVE_DIRECTIONS):
            sector_values: dict[str, list[tuple[str, float]]] = defaultdict(list)
            for security_id in security_ids:
                value = raw[formation, security_id][column_index]
                if value is not None:
                    sector_values[sectors[security_id]].append((security_id, value))
            ranked: dict[str, float] = {}
            for values in sector_values.values():
                ranked.update(_tie_percentiles(values, direction))
            ranks.append(ranked)
        for security_id in security_ids:
            result[formation, security_id] = {
                column: ranks[index].get(security_id)
                for index, column in enumerate(ACTIVE_MODEL_COLUMNS)
            }
    return result


def _display_positions(predictions: Mapping[str, float]) -> tuple[dict[str, float], dict[str, int]]:
    ordered = sorted(predictions, key=lambda security_id: (predictions[security_id], security_id))
    denominator = max(1, len(ordered) - 1)
    scores = {security_id: index / denominator * 100.0 for index, security_id in enumerate(ordered)}
    ranks = {
        security_id: index
        for index, security_id in enumerate(
            sorted(predictions, key=lambda security_id: (-predictions[security_id], security_id)), start=1,
        )
    }
    return scores, ranks


def audit_rank_rows(
    *, model: ActiveModelArtifact,
    ranked_inputs: Mapping[tuple[date, str], Mapping[str, float | None]],
    by_formation: Mapping[date, Sequence[str]],
) -> dict[str, object]:
    per_formation: list[dict[str, object]] = []
    identical = 0
    prior_total = 0
    corrected_total = 0
    expanded_total = 0
    score_changes: list[float] = []
    rank_changes: list[int] = []
    exact_zero_only_violations = 0
    for formation, security_ids in sorted(by_formation.items()):
        legacy: dict[str, float] = {}
        corrected: dict[str, float] = {}
        for security_id in security_ids:
            values = ranked_inputs[formation, security_id]
            old = evaluate_model_inputs(model, values, ignore_exact_zero_coefficients=False)
            new = evaluate_model_inputs(model, values, ignore_exact_zero_coefficients=True)
            if old.eligible:
                assert old.prediction is not None and new.prediction is not None
                legacy[security_id] = old.prediction
                corrected[security_id] = new.prediction
                prior_total += 1
                if struct.pack(">d", old.prediction) == struct.pack(">d", new.prediction):
                    identical += 1
            elif new.eligible:
                assert new.prediction is not None
                corrected[security_id] = new.prediction
                expanded_total += 1
                if any(model.coefficients[model.feature_columns.index(column)] != 0.0 for column in old.missing_required_columns):
                    exact_zero_only_violations += 1
        old_scores, old_ranks = _display_positions(legacy)
        new_scores, new_ranks = _display_positions(corrected)
        for security_id in legacy:
            score_changes.append(abs(new_scores[security_id] - old_scores[security_id]))
            rank_changes.append(abs(new_ranks[security_id] - old_ranks[security_id]))
        corrected_total += len(corrected)
        per_formation.append({
            "formation_date": formation.isoformat(),
            "universe_count": len(security_ids),
            "previously_eligible_count": len(legacy),
            "corrected_eligible_count": len(corrected),
            "newly_eligible_count": len(corrected) - len(legacy),
            "previous_coverage": len(legacy) / len(security_ids),
            "corrected_coverage": len(corrected) / len(security_ids),
        })
    row_count = sum(len(rows) for rows in by_formation.values())
    minimum_coverage = min(float(row["corrected_coverage"]) for row in per_formation)
    return {
        "row_count": row_count,
        "formation_count": len(by_formation),
        "previously_eligible_rows": prior_total,
        "corrected_eligible_rows": corrected_total,
        "newly_eligible_rows": expanded_total,
        "previous_coverage": prior_total / row_count,
        "corrected_coverage": corrected_total / row_count,
        "minimum_corrected_formation_coverage": minimum_coverage,
        "previous_raw_prediction_byte_identical_count": identical,
        "previous_raw_prediction_byte_mismatch_count": prior_total - identical,
        "new_eligibility_nonzero_missing_violations": exact_zero_only_violations,
        "previous_row_display_score_changes": {
            "changed_count": sum(value != 0 for value in score_changes),
            "mean_absolute_points": sum(score_changes) / len(score_changes),
            "maximum_absolute_points": max(score_changes, default=0.0),
        },
        "previous_row_rank_changes": {
            "changed_count": sum(value != 0 for value in rank_changes),
            "mean_absolute_positions": sum(rank_changes) / len(rank_changes),
            "maximum_absolute_positions": max(rank_changes, default=0),
        },
        "explanations": {
            "active_input_count": len(required_model_columns(model, ignore_exact_zero_coefficients=True)),
            "previous_explanation_rows": prior_total * len(required_model_columns(model, ignore_exact_zero_coefficients=True)),
            "corrected_explanation_rows": corrected_total * len(required_model_columns(model, ignore_exact_zero_coefficients=True)),
            "previous_explanations_numerically_changed": 0,
        },
        "per_formation": per_formation,
    }


def run_audit(
    *, database_url: str, panel: Path, registration_path: Path, destination: Path,
) -> dict[str, object]:
    registration = _load_registration(registration_path)
    panel_manifest = _validate_panel(panel)
    model = load_active_model(database_url)
    # Resolve the authenticated active artifact from its immutable DB deployment.
    import psycopg
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT artifact.artifact_uri,artifact.artifact_sha256
                 FROM quantrade.model_deployments deployment
                 JOIN quantrade.model_artifacts artifact USING(model_version)
                ORDER BY deployment.deployed_at DESC LIMIT 1"""
        )
        artifact_row = cursor.fetchone()
    if artifact_row is None:
        raise DataQualityError("no active model artifact is registered")
    artifact_path = _path_from_file_uri(str(artifact_row[0]))
    artifact_sha256 = _sha256_file(artifact_path)
    if artifact_sha256 != str(artifact_row[1]):
        raise DataQualityError("active model artifact hash differs from its database record")
    _validate_anchor(model, registration, artifact_sha256=artifact_sha256)

    keys, by_formation = _panel_index(panel)
    security_ids = sorted({security_id for _, security_id in keys})
    formations = sorted(by_formation)
    raw = _load_active_raw_panel(panel, keys)
    sectors, active_values, active_source_hash = _load_static_sectors_and_liquidity(
        database_url, security_ids=security_ids, formations=formations,
        conservative_asof=True,
    )
    ranked = _rank_active_inputs(
        raw=raw, by_formation=by_formation, sectors=sectors, active_values=active_values,
    )
    metrics = audit_rank_rows(model=model, ranked_inputs=ranked, by_formation=by_formation)
    gates = {
        "raw_predictions_byte_identical": metrics["previous_raw_prediction_byte_mismatch_count"] == 0,
        "new_rows_ignore_only_exact_zero_inputs": metrics["new_eligibility_nonzero_missing_violations"] == 0,
        "aggregate_coverage_at_least_95_percent": metrics["corrected_coverage"] >= 0.95,
        "minimum_formation_coverage_at_least_90_percent": metrics["minimum_corrected_formation_coverage"] >= 0.90,
    }
    document: dict[str, object] = {
        "audit_key": AUDIT_KEY,
        "audit_version": AUDIT_VERSION,
        "model_version": model.model_version,
        "active_artifact_sha256": artifact_sha256,
        "feature_registry_sha256": model.feature_registry_hash,
        "source_panel_sha256": panel_manifest["panel_file_sha256"],
        "source_panel_report_sha256": panel_manifest["report_hash"],
        "active_input_source_sha256": active_source_hash,
        "mathematically_nonzero_inputs": list(required_model_columns(model, ignore_exact_zero_coefficients=True)),
        "mathematically_zero_inputs": [
            column for column, coefficient in zip(model.feature_columns, model.coefficients, strict=True)
            if coefficient == 0.0
        ],
        "eligibility_semantics": "serialized coefficient != 0.0; no tolerance or approximate-zero rule",
        "decision_time_consistency": {
            "historical_contract": HISTORICAL_DECISION_CONTRACT,
            "historical_cutoff": "20:00 America/Toronto with SEC acceptance-plus-five-minute eligibility",
            "live_contract": LIVE_DECISION_CONTRACT,
            "live_cutoff": "actual post-ingestion and post-validation timestamp",
            "shared_eligibility_implementation": "quantrade_research.model_eligibility.evaluate_model_inputs",
            "live_rollout_performed": False,
        },
        "metrics": metrics,
        "gates": gates,
        "passed": all(gates.values()),
        "limitations": [
            "Tier B current-survivors cohort is survivorship biased",
            "current sectors are static groupings, not historical point-in-time classifications",
            "this audit does not authorize or perform a live eligibility expansion",
        ],
    }
    document["audit_sha256"] = _canonical_hash(document)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not document["passed"]:
        raise DataQualityError("Phase 9D exact-zero eligibility audit failed")
    return document


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Phase 9D exact-zero input eligibility")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--panel", type=Path, default=Path("data/derived/phase_9c_weekly_feature_panel_v1.csv.gz"))
    parser.add_argument("--registration", type=Path, default=Path("research/registrations/phase_9d_anchored_stability_v1.json"))
    parser.add_argument("--destination", type=Path, default=Path("data/derived/phase_9d_exact_zero_eligibility_audit_v1.json"))
    arguments = parser.parse_args()
    values = dict(__import__("os").environ)
    values.update(_dotenv_values(arguments.env_file))
    database_url = values.get("DATABASE_URL")
    if not database_url:
        raise DataQualityError("DATABASE_URL is required")
    result = run_audit(
        database_url=database_url, panel=arguments.panel,
        registration_path=arguments.registration, destination=arguments.destination,
    )
    metrics = result["metrics"]
    print(
        f"audit={result['audit_sha256']}; corrected_coverage={metrics['corrected_coverage']:.6f}; "
        f"minimum_formation_coverage={metrics['minimum_corrected_formation_coverage']:.6f}; "
        f"newly_eligible={metrics['newly_eligible_rows']}; live_rollout=false"
    )


if __name__ == "__main__":
    main()
