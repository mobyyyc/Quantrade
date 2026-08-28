"""Resumable legacy snapshot into immutable, buffered SEC fact observations."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from .score_run import _settings


RUN_KEY = "legacy_sec_fact_snapshot_v1"
RULE_KEY = "sec_filing_acceptance_buffered"
RULE_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class SnapshotProgress:
    source_rows: int
    processed_rows: int
    persisted_rows: int
    duplicate_rows: int
    last_filing_fact_id: str | None
    completed: bool

    @property
    def percent(self) -> float:
        return 100.0 if self.source_rows == 0 else self.processed_rows * 100.0 / self.source_rows


class SecFactSnapshotRepository:
    def __init__(self, database_url: str) -> None:
        import psycopg

        self._connection = psycopg.connect(database_url)

    def close(self) -> None:
        self._connection.close()

    def start_or_resume(self) -> SnapshotProgress:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT availability_rule_id FROM quantrade.availability_rules
                   WHERE rule_key = %s AND rule_version = %s AND provider = 'sec_edgar'
                     AND data_domain = 'filing_fact'""",
                (RULE_KEY, RULE_VERSION),
            )
            rule = cursor.fetchone()
            if rule is None:
                raise ValueError("run migration 0028 before the SEC fact snapshot")
            cursor.execute("SELECT COUNT(*) FROM quantrade.filing_facts")
            source_rows = int(cursor.fetchone()[0])
            cursor.execute(
                """INSERT INTO quantrade.sec_fact_snapshot_runs
                       (run_key, availability_rule_id, status, source_row_count)
                   VALUES (%s, %s, 'running', %s)
                   ON CONFLICT (run_key) DO NOTHING""",
                (RUN_KEY, rule[0], source_rows),
            )
            cursor.execute(
                """SELECT source_row_count, processed_row_count, persisted_observation_count,
                          duplicate_observation_count, last_filing_fact_id::text, status = 'completed'
                   FROM quantrade.sec_fact_snapshot_runs WHERE run_key = %s""",
                (RUN_KEY,),
            )
            row = cursor.fetchone()
        self._connection.commit()
        if row is None:  # pragma: no cover - table constraints guarantee the row
            raise RuntimeError("could not initialize legacy SEC fact snapshot")
        return SnapshotProgress(int(row[0]), int(row[1]), int(row[2]), int(row[3]), row[4], bool(row[5]))

    def process_batch(self, batch_size: int) -> SnapshotProgress:
        if batch_size < 1:
            raise ValueError("batch size must be positive")
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT status, last_filing_fact_id::text FROM quantrade.sec_fact_snapshot_runs
                   WHERE run_key = %s FOR UPDATE""",
                (RUN_KEY,),
            )
            run = cursor.fetchone()
            if run is None:
                raise ValueError("start the legacy SEC fact snapshot before processing batches")
            if run[0] == "completed":
                self._connection.rollback()
                return self.start_or_resume()
            cursor.execute(
                """WITH source_rows AS MATERIALIZED (
                       SELECT fact.filing_fact_id, fact.filing_id, fact.security_id, fact.taxonomy, fact.concept,
                              fact.unit, fact.fact_value, fact.period_start, fact.period_end, fact.fiscal_year,
                              fact.fiscal_period, fact.raw_artifact_id, fact.source_reference,
                              fact.source_receipt_id, fact.ingested_at, filing.accepted_at
                       FROM quantrade.filing_facts AS fact
                       JOIN quantrade.filings AS filing ON filing.filing_id = fact.filing_id
                       WHERE (%s::uuid IS NULL OR fact.filing_fact_id > %s::uuid)
                       ORDER BY fact.filing_fact_id
                       LIMIT %s
                   ), inserted AS (
                       INSERT INTO quantrade.filing_fact_observations
                           (filing_id, security_id, taxonomy, concept, unit, fact_value, period_start, period_end,
                            fiscal_year, fiscal_period, available_at, availability_rule_id, raw_artifact_id,
                            source_reference, source_receipt_id, observed_at, observation_kind, observation_hash)
                       SELECT fact.filing_id, fact.security_id, fact.taxonomy, fact.concept, fact.unit, fact.fact_value,
                              fact.period_start, fact.period_end, fact.fiscal_year, fact.fiscal_period,
                              fact.accepted_at + INTERVAL '5 minutes', run.availability_rule_id,
                              fact.raw_artifact_id, fact.source_reference, fact.source_receipt_id, fact.ingested_at,
                              'legacy_snapshot',
                              encode(digest(concat_ws('|', fact.filing_id::text, fact.taxonomy, fact.concept,
                                  fact.unit, coalesce(fact.period_start::text, ''), fact.period_end::text,
                                  fact.fact_value::text, coalesce(fact.fiscal_year::text, ''),
                                  coalesce(fact.fiscal_period, ''), coalesce(fact.source_receipt_id::text, ''),
                                  fact.raw_artifact_id::text, 'legacy_snapshot'), 'sha256'), 'hex')
                       FROM source_rows AS fact
                       CROSS JOIN quantrade.sec_fact_snapshot_runs AS run
                       WHERE run.run_key = %s
                       ON CONFLICT (observation_hash) DO NOTHING
                       RETURNING filing_fact_observation_id
                   ), totals AS (
                       SELECT COUNT(*)::bigint AS processed,
                              COALESCE((SELECT filing_fact_id::text FROM source_rows
                                        ORDER BY filing_fact_id DESC LIMIT 1), '') AS last_id
                       FROM source_rows
                   ), updated AS (
                       UPDATE quantrade.sec_fact_snapshot_runs AS run
                       SET last_filing_fact_id = NULLIF(totals.last_id, '')::uuid,
                           processed_row_count = run.processed_row_count + totals.processed,
                           persisted_observation_count = run.persisted_observation_count + (SELECT COUNT(*) FROM inserted),
                           duplicate_observation_count = run.duplicate_observation_count
                               + totals.processed - (SELECT COUNT(*) FROM inserted)
                       FROM totals
                       WHERE run.run_key = %s AND totals.processed > 0
                       RETURNING run.source_row_count, run.processed_row_count, run.persisted_observation_count,
                                 run.duplicate_observation_count, run.last_filing_fact_id::text
                   )
                   SELECT * FROM updated""",
                (run[1], run[1], batch_size, RUN_KEY, RUN_KEY),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    """UPDATE quantrade.sec_fact_snapshot_runs
                       SET status = 'completed', completed_at = now()
                       WHERE run_key = %s AND status = 'running'
                       RETURNING source_row_count, processed_row_count, persisted_observation_count,
                                 duplicate_observation_count, last_filing_fact_id::text""",
                    (RUN_KEY,),
                )
                row = cursor.fetchone()
                completed = True
            else:
                completed = False
        self._connection.commit()
        if row is None:  # pragma: no cover - guarded by start_or_resume
            raise RuntimeError("could not update legacy SEC fact snapshot progress")
        return SnapshotProgress(int(row[0]), int(row[1]), int(row[2]), int(row[3]), row[4], completed)


def progress_line(progress: SnapshotProgress, *, batch: int) -> str:
    return (
        f"progress batch={batch}; processed={progress.processed_rows}/{progress.source_rows} "
        f"({progress.percent:.1f}%); persisted={progress.persisted_rows}; duplicates={progress.duplicate_rows}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Resume the immutable Tier-B legacy SEC fact snapshot")
    parser.add_argument("--batch-size", type=int, default=5_000)
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument("--max-batches", type=int, help="Stop after N safe committed batches")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    if arguments.batch_size < 1 or arguments.progress_every < 1:
        parser.error("batch-size and progress-every must be positive")
    if arguments.max_batches is not None and arguments.max_batches < 1:
        parser.error("max-batches must be positive")
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    repository = SecFactSnapshotRepository(settings.database_url)
    try:
        progress = repository.start_or_resume()
        if arguments.dry_run:
            print(progress_line(progress, batch=0))
            return
        batch = 0
        while not progress.completed:
            if arguments.max_batches is not None and batch >= arguments.max_batches:
                break
            batch += 1
            progress = repository.process_batch(arguments.batch_size)
            if batch % arguments.progress_every == 0 or progress.completed:
                print(progress_line(progress, batch=batch), flush=True)
        print(f"status={'completed' if progress.completed else 'paused'}; {progress_line(progress, batch=batch)}")
    finally:
        repository.close()


if __name__ == "__main__":
    main()
