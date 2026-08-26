"""Read-only coverage evidence for Tier-B historical corporate actions."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path

from .historical_cohorts import CURRENT_SURVIVORS_COHORT
from .quality import DataQualityError
from .score_run import _dotenv_values


@dataclass(frozen=True)
class CorporateActionCoverageEvidence:
    start_date: date
    end_date: date
    action_count: int
    completed_run_count: int
    requested_chunks: int
    completed_chunks: int
    chunks_without_raw_document: int


def evaluate_corporate_action_coverage(evidence: CorporateActionCoverageEvidence) -> dict[str, object]:
    """Make the Tier-B action-coverage assertion explicit and fail closed."""
    failures: list[str] = []
    if evidence.completed_run_count != 1:
        failures.append("no completed cohort corporate-action backfill covers the requested period")
    if evidence.requested_chunks <= 0 or evidence.completed_chunks != evidence.requested_chunks:
        failures.append("the covering corporate-action backfill has incomplete chunks")
    if evidence.chunks_without_raw_document:
        failures.append("one or more completed corporate-action chunks lack a raw provider response")
    if evidence.action_count <= 0:
        failures.append("no corporate-action records fall in the requested period")
    return {
        "status": "corporate_action_coverage_checked",
        "coverage_ready": not failures,
        "cohort_code": CURRENT_SURVIVORS_COHORT,
        "data_capability_tier": "B",
        "start_date": evidence.start_date.isoformat(),
        "end_date": evidence.end_date.isoformat(),
        "corporate_action_record_count": evidence.action_count,
        "completed_run_count": evidence.completed_run_count,
        "requested_chunks": evidence.requested_chunks,
        "completed_chunks": evidence.completed_chunks,
        "chunks_without_raw_document": evidence.chunks_without_raw_document,
        "failures": failures,
        "limitations": [
            "This verifies ingestion completeness for the fixed current-survivors Tier-B cohort, not licensed point-in-time index membership or provider completeness.",
            "Corporate-action-adjusted position accounting remains a separate requirement for any raw-price performance claim.",
        ],
    }


def load_corporate_action_coverage(database_url: str, *, start_date: date, end_date: date) -> dict[str, object]:
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT COUNT(*) FROM quantrade.corporate_actions
               WHERE COALESCE(effective_date, process_date) >= %s
                 AND COALESCE(effective_date, process_date) <= %s""",
            (start_date, end_date),
        )
        action_count = int(cursor.fetchone()[0])
        cursor.execute(
            """SELECT run.requested_count,
                      COUNT(chunk.historical_backfill_chunk_id) FILTER (WHERE chunk.status = 'completed'),
                      COUNT(chunk.historical_backfill_chunk_id) FILTER (
                          WHERE chunk.status = 'completed' AND chunk.raw_document_count < 1
                      )
                 FROM quantrade.historical_backfill_runs AS run
                 JOIN quantrade.research_cohorts AS cohort
                   ON cohort.research_cohort_id = run.research_cohort_id
                 JOIN quantrade.availability_rules AS rule
                   ON rule.availability_rule_id = run.availability_rule_id
                 LEFT JOIN quantrade.historical_backfill_chunks AS chunk
                   ON chunk.historical_backfill_run_id = run.historical_backfill_run_id
                WHERE cohort.cohort_code = %s
                  AND rule.data_domain = 'corporate_action'
                  AND run.data_domain = 'corporate_action'
                  AND run.status = 'completed'
                  AND run.start_date <= %s
                  AND run.end_date >= %s
                GROUP BY run.historical_backfill_run_id, run.requested_count, run.completed_at
                ORDER BY run.completed_at DESC
                LIMIT 1""",
            (CURRENT_SURVIVORS_COHORT, start_date, end_date),
        )
        run = cursor.fetchone()
    evidence = CorporateActionCoverageEvidence(
        start_date=start_date,
        end_date=end_date,
        action_count=action_count,
        completed_run_count=1 if run else 0,
        requested_chunks=int(run[0]) if run else 0,
        completed_chunks=int(run[1]) if run else 0,
        chunks_without_raw_document=int(run[2]) if run else 0,
    )
    return evaluate_corporate_action_coverage(evidence)


def require_corporate_action_coverage(database_url: str, *, start_date: date, end_date: date) -> dict[str, object]:
    report = load_corporate_action_coverage(database_url, start_date=start_date, end_date=end_date)
    if not report["coverage_ready"]:
        reasons = "; ".join(str(value) for value in report["failures"])
        raise DataQualityError(f"corporate-action coverage is incomplete: {reasons}")
    return report


def _settings(env_file: Path):
    from .config import Settings

    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a read-only Tier-B corporate-action coverage report")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    if arguments.start > arguments.end:
        parser.error("--start must not be after --end")
    if arguments.output.exists():
        raise DataQualityError(f"refusing to overwrite immutable coverage report: {arguments.output}")
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    report = load_corporate_action_coverage(settings.database_url, start_date=arguments.start, end_date=arguments.end)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"coverage_ready={report['coverage_ready']}; corporate_action_records={report['corporate_action_record_count']}")


if __name__ == "__main__":
    main()
