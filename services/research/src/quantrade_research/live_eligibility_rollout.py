"""Read-only dry run for the live exact-zero eligibility rollout."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable

from .active_model import load_active_model
from .model_eligibility import (
    EXACT_ZERO_COEFFICIENTS_V1,
    required_model_columns,
)
from .quality import DataQualityError
from .score_run import SCORE_PROTOCOL_BY_ELIGIBILITY_CONTRACT, _dotenv_values


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def audit_rows(
    rows: Iterable[tuple[str, str, bool, str | None, object | None, str | None]],
    *,
    required_feature_keys: tuple[str, ...],
) -> dict[str, object]:
    """Classify existing published rows using only non-zero-input evidence."""
    snapshots: dict[str, tuple[str, bool]] = {}
    evidence: dict[str, dict[str, tuple[object | None, str | None]]] = defaultdict(dict)
    for security_id, label, was_eligible, feature_key, percentile, reason in rows:
        prior = snapshots.setdefault(security_id, (label, was_eligible))
        if prior != (label, was_eligible):
            raise DataQualityError(f"inconsistent published snapshot evidence: {security_id}")
        if feature_key is None:
            continue
        if feature_key in evidence[security_id]:
            raise DataQualityError(f"duplicate score explanation: {security_id}:{feature_key}")
        evidence[security_id][feature_key] = (percentile, reason)
    if not snapshots:
        raise DataQualityError("no published scores are available for the rollout dry run")

    newly_eligible: list[str] = []
    still_excluded: dict[str, list[str]] = {}
    corrected_eligible = 0
    old_eligible = 0
    exclusions: Counter[str] = Counter()
    for security_id, (label, was_eligible) in sorted(snapshots.items(), key=lambda item: item[1][0]):
        old_eligible += int(was_eligible)
        missing: list[str] = []
        for feature_key in required_feature_keys:
            feature = evidence[security_id].get(feature_key)
            if feature is None:
                missing.append(f"{feature_key}:missing_explanation")
            elif feature[0] is None:
                missing.append(f"{feature_key}:{feature[1] or 'percentile_unavailable'}")
        if missing:
            still_excluded[f"{label} [{security_id}]"] = missing
            for reason in missing:
                exclusions[reason] += 1
            if was_eligible:
                raise DataQualityError(
                    f"previously eligible row lacks a required non-zero input: {label}"
                )
            continue
        corrected_eligible += 1
        if not was_eligible:
            newly_eligible.append(f"{label} [{security_id}]")

    return {
        "snapshot_count": len(snapshots),
        "previously_eligible_count": old_eligible,
        "corrected_eligible_count": corrected_eligible,
        "newly_eligible_count": len(newly_eligible),
        "newly_eligible_securities": newly_eligible,
        "still_excluded_count": len(snapshots) - corrected_eligible,
        "still_excluded": still_excluded,
        "still_excluded_reasons": dict(sorted(exclusions.items())),
    }


def _published_rows(database_url: str, model_version: str) -> tuple[date, list[tuple]]:
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT MAX(score_date)
               FROM quantrade.score_snapshots
               WHERE model_version = %s""",
            (model_version,),
        )
        latest = cursor.fetchone()[0]
        if latest is None:
            raise DataQualityError("the active model has no published score snapshots")
        cursor.execute(
            """SELECT snapshot.security_id::text,
                      security.issuer_name,
                      snapshot.eligible,
                      explanation.feature_key,
                      explanation.percentile,
                      explanation.unavailable_reason
               FROM quantrade.score_snapshots snapshot
               JOIN quantrade.securities security
                 ON security.security_id = snapshot.security_id
               LEFT JOIN quantrade.score_explanations explanation
                 ON explanation.score_snapshot_id = snapshot.score_snapshot_id
               WHERE snapshot.model_version = %s AND snapshot.score_date = %s
               ORDER BY snapshot.security_id, explanation.feature_key""",
            (model_version, latest),
        )
        return latest, list(cursor.fetchall())


def run(database_url: str) -> dict[str, object]:
    model = load_active_model(database_url)
    required_columns = required_model_columns(
        model, ignore_exact_zero_coefficients=True,
    )
    score_date, rows = _published_rows(database_url, model.model_version)
    metrics = audit_rows(rows, required_feature_keys=required_columns)
    report: dict[str, object] = {
        "audit": "live_exact_zero_eligibility_rollout",
        "version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_score_date": score_date.isoformat(),
        "active_model_version": model.model_version,
        "eligibility_contract": EXACT_ZERO_COEFFICIENTS_V1,
        "future_score_protocol": SCORE_PROTOCOL_BY_ELIGIBILITY_CONTRACT[
            EXACT_ZERO_COEFFICIENTS_V1
        ],
        "required_nonzero_columns": list(required_columns),
        "historical_scores_mutated": False,
        **metrics,
    }
    authenticated = dict(report)
    authenticated.pop("generated_at")
    report["logical_sha256"] = sha256(_canonical_json(authenticated).encode("utf-8")).hexdigest()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run the live exact-zero eligibility contract")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--destination", type=Path)
    arguments = parser.parse_args()
    database_url = _dotenv_values(arguments.env_file).get("DATABASE_URL")
    if not database_url:
        raise DataQualityError("DATABASE_URL is required")
    report = run(database_url)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.destination:
        arguments.destination.parent.mkdir(parents=True, exist_ok=True)
        arguments.destination.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
