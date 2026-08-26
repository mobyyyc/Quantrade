"""Immutable approval-integrity audit for a completed locked-holdout report."""

from __future__ import annotations

import argparse
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path

from .holdout_evaluation import require_locked_holdout_confirmation
from .quality import DataQualityError
from .score_run import _dotenv_values


def evaluate_holdout_integrity(*, evaluation_document: dict[str, object], corporate_action_count: int) -> dict[str, object]:
    """Reject approval whenever raw-price position accounting lacks action coverage."""
    if evaluation_document.get("status") != "execution_cost_evaluation_complete":
        raise DataQualityError("holdout evaluation document is incomplete")
    if evaluation_document.get("holdout_performance_evaluated") is not True:
        raise DataQualityError("holdout evaluation document does not represent a completed evaluation")
    failures: list[dict[str, str]] = []
    if corporate_action_count <= 0:
        failures.append({
            "gate": "corporate_action_coverage",
            "reason": "No corporate-action records cover the raw-price holdout execution window; split/dividend position accounting cannot be verified.",
        })
    return {
        "status": "holdout_integrity_audit_complete",
        "approval_eligible": not failures,
        "approval_status": "blocked_integrity" if failures else "eligible_for_policy_review",
        "corporate_action_record_count": corporate_action_count,
        "failures": failures,
        "interpretation": (
            "The saved performance report is a diagnostic only and must not support model approval or a performance claim."
            if failures else "Integrity prerequisites passed; apply the remaining approval-policy gates separately."
        ),
    }


def _settings(env_file: Path):
    from .config import Settings

    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def _corporate_action_count(database_url: str, start_date: date, end_date: date) -> int:
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT COUNT(*) FROM quantrade.corporate_actions
               WHERE COALESCE(effective_date, process_date) >= %s
                 AND COALESCE(effective_date, process_date) <= %s""",
            (start_date, end_date),
        )
        return int(cursor.fetchone()[0])


def main() -> None:
    parser = argparse.ArgumentParser(description="Record an immutable integrity audit for a completed locked-holdout report")
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--confirm-locked-holdout", action="store_true")
    arguments = parser.parse_args()
    require_locked_holdout_confirmation(arguments.confirm_locked_holdout)
    if arguments.output.exists():
        raise DataQualityError(f"refusing to overwrite immutable holdout integrity audit: {arguments.output}")
    try:
        document = json.loads(arguments.evaluation.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid holdout evaluation document") from error
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    audit = evaluate_holdout_integrity(
        evaluation_document=document,
        corporate_action_count=_corporate_action_count(settings.database_url, date(2025, 7, 1), date(2026, 6, 30)),
    )
    audit["evaluation_sha256"] = sha256(arguments.evaluation.read_bytes()).hexdigest()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"approval_status={audit['approval_status']}; corporate_action_records={audit['corporate_action_record_count']}")


if __name__ == "__main__":
    main()
