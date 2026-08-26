"""Export the Tier-B historical replay as a versioned, wide ML dataset."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Iterable

from .quality import DataQualityError
from .score_run import _dotenv_values


DATASET_KEY = "sp500_current_survivors_20d"
DATASET_VERSION = "v1"
COHORT_CODE = "sp500_current_survivors_v1"
HORIZON_SESSIONS = 20
HOLDOUT_START = date(2025, 7, 1)
HOLDOUT_END = date(2026, 6, 30)
FEATURE_KEYS = (
    "earnings_yield_ttm",
    "median_dollar_volume_20d",
    "momentum_12_1",
    "relative_strength_6m",
    "return_on_assets_ttm",
    "trailing_volatility_60d",
)
LIMITATIONS = [
    "Tier B research only: fixed current S&P 500 survivors, not historical membership.",
    "Sector grouping is static/current and not point-in-time historical classification.",
    "Historical market-bar availability follows the documented conservative 6 p.m. Toronto rule.",
    "This dataset must not support an unbiased historical-performance or public-performance claim.",
]


def dataset_partition(score_date: date) -> str:
    return "holdout" if HOLDOUT_START <= score_date <= HOLDOUT_END else "development"


def _settings(env_file: Path):
    from .config import Settings

    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def _csv_rows(cursor) -> Iterable[tuple[object, ...]]:
    cursor.execute(
        """SELECT snapshot.score_snapshot_id::text, snapshot.security_id::text,
                  COALESCE(listing.ticker, 'Unavailable'), security.issuer_name,
                  snapshot.score_date, snapshot.decision_at, snapshot.data_cutoff_at,
                  snapshot.model_version, snapshot.feature_version, snapshot.protocol_version,
                  MAX(explanation.sector_code) AS sector_code, snapshot.score AS baseline_score,
                  snapshot.rank AS baseline_rank,
                  MAX(explanation.percentile) FILTER (WHERE explanation.feature_key = 'earnings_yield_ttm') AS earnings_yield_ttm_percentile,
                  MAX(explanation.percentile) FILTER (WHERE explanation.feature_key = 'median_dollar_volume_20d') AS median_dollar_volume_20d_percentile,
                  MAX(explanation.percentile) FILTER (WHERE explanation.feature_key = 'momentum_12_1') AS momentum_12_1_percentile,
                  MAX(explanation.percentile) FILTER (WHERE explanation.feature_key = 'relative_strength_6m') AS relative_strength_6m_percentile,
                  MAX(explanation.percentile) FILTER (WHERE explanation.feature_key = 'return_on_assets_ttm') AS return_on_assets_ttm_percentile,
                  MAX(explanation.percentile) FILTER (WHERE explanation.feature_key = 'trailing_volatility_60d') AS trailing_volatility_60d_percentile,
                  outcome.execution_date, outcome.outcome_date, outcome.security_return,
                  outcome.benchmark_return, outcome.benchmark_relative_return, outcome.data_cutoff_at
           FROM quantrade.forward_score_outcomes outcome
           JOIN quantrade.score_snapshots snapshot ON snapshot.score_snapshot_id = outcome.score_snapshot_id
           JOIN quantrade.daily_research_runs run ON run.score_date = snapshot.score_date
                AND run.decision_at = snapshot.decision_at AND run.status = 'completed'
           JOIN quantrade.securities security ON security.security_id = snapshot.security_id
           JOIN quantrade.score_explanations explanation ON explanation.score_snapshot_id = snapshot.score_snapshot_id
           LEFT JOIN LATERAL (
               SELECT ticker FROM quantrade.listings
               WHERE security_id = snapshot.security_id AND valid_from <= snapshot.score_date
                 AND (valid_to IS NULL OR valid_to > snapshot.score_date)
               ORDER BY valid_from DESC LIMIT 1
           ) listing ON TRUE
           WHERE outcome.horizon_sessions = %s AND outcome.status = 'completed'
             AND snapshot.eligible AND snapshot.score_date BETWEEN %s AND %s
             AND explanation.percentile IS NOT NULL
           GROUP BY snapshot.score_snapshot_id, snapshot.security_id, listing.ticker, security.issuer_name,
                    snapshot.score_date, snapshot.decision_at, snapshot.data_cutoff_at, snapshot.model_version,
                    snapshot.feature_version, snapshot.protocol_version, snapshot.score, snapshot.rank,
                    outcome.execution_date, outcome.outcome_date, outcome.security_return, outcome.benchmark_return,
                    outcome.benchmark_relative_return, outcome.data_cutoff_at
           HAVING COUNT(DISTINCT (explanation.feature_key, explanation.feature_version)) = %s
           ORDER BY snapshot.score_date, snapshot.security_id""",
        (HORIZON_SESSIONS, date(2021, 1, 1), HOLDOUT_END, len(FEATURE_KEYS)),
    )
    yield from cursor


def export_training_dataset(*, database_url: str, destination: Path) -> dict[str, object]:
    """Write one wide row per completed labeled snapshot without mutating research rows."""
    try:
        import psycopg
    except ImportError as error:  # pragma: no cover
        raise RuntimeError("Install quantrade-research dependencies before exporting") from error
    if destination.exists():
        raise DataQualityError(f"refusing to overwrite immutable dataset export: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "score_snapshot_id", "security_id", "ticker", "issuer_name", "score_date", "partition",
        "decision_at", "score_data_cutoff_at", "model_version", "feature_registry_hash", "protocol_version",
        "sector_code", "baseline_score", "baseline_rank",
        *(f"{key}_percentile" for key in FEATURE_KEYS),
        "execution_date", "outcome_date", "security_return", "benchmark_return",
        "benchmark_relative_return", "outcome_data_cutoff_at",
    )
    rows = development = holdout = 0
    with psycopg.connect(database_url) as connection, connection.cursor(name="training_export") as cursor:
        cursor.itersize = 10_000
        with destination.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(fieldnames)
            for source in _csv_rows(cursor):
                record = list(source)
                score_date = record[4]
                partition = dataset_partition(score_date)
                record.insert(5, partition)
                writer.writerow(value.isoformat() if isinstance(value, (date, datetime)) else value for value in record)
                rows += 1
                if partition == "development":
                    development += 1
                else:
                    holdout += 1
    if not rows:
        raise DataQualityError("training export contains no completed examples")
    return {
        "dataset_key": DATASET_KEY,
        "dataset_version": DATASET_VERSION,
        "cohort_code": COHORT_CODE,
        "data_capability_tier": "B",
        "horizon_sessions": HORIZON_SESSIONS,
        "row_count": rows,
        "development_row_count": development,
        "holdout_row_count": holdout,
        "feature_columns": [f"{key}_percentile" for key in FEATURE_KEYS],
        "target_column": "benchmark_relative_return",
        "holdout": {"start_date": HOLDOUT_START.isoformat(), "end_date": HOLDOUT_END.isoformat()},
        "development_validation_rule": "Use dates before 2025-07-01 and apply a 20-session purge before every validation window.",
        "content_sha256": sha256(destination.read_bytes()).hexdigest(),
        "limitations": LIMITATIONS,
    }


def record_provenance(*, database_url: str, metadata: dict[str, object], manifest_uri: str) -> None:
    """Lock the final holdout and dataset provenance before the first model experiment."""
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO quantrade.holdout_periods
               (protocol_version, start_date, end_date, locked_at, rationale)
               VALUES ('tier_b_20d_v1', %s, %s, now(), %s)
               ON CONFLICT (protocol_version) DO NOTHING""",
            (HOLDOUT_START, HOLDOUT_END, "Reserved final Tier-B holdout; never use it for model selection."),
        )
        cursor.execute("SELECT research_cohort_id FROM quantrade.research_cohorts WHERE cohort_code = %s", (COHORT_CODE,))
        cohort = cursor.fetchone()
        if cohort is None:
            raise DataQualityError(f"missing research cohort {COHORT_CODE}")
        cursor.execute(
            """INSERT INTO quantrade.training_dataset_provenance
               (dataset_key, dataset_version, research_cohort_id, primary_label_horizon_sessions,
                data_capability_tier, historical_start_date, historical_end_date, provenance_status,
                limitations, manifest_uri)
               VALUES (%s, %s, %s, %s, 'B', %s, %s, 'ready', %s::jsonb, %s)""",
            (DATASET_KEY, DATASET_VERSION, cohort[0], HORIZON_SESSIONS, date(2022, 1, 3), HOLDOUT_END,
             json.dumps(LIMITATIONS), manifest_uri),
        )
        connection.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the versioned Tier-B 20-session historical training dataset")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    metadata = export_training_dataset(database_url=settings.database_url, destination=arguments.output)
    manifest = arguments.output.with_suffix(".json")
    manifest.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    record_provenance(database_url=settings.database_url, metadata=metadata, manifest_uri=manifest.resolve().as_uri())
    print(f"training_rows={metadata['row_count']}; development_rows={metadata['development_row_count']}; holdout_rows={metadata['holdout_row_count']}; dataset={DATASET_KEY}@{DATASET_VERSION}")


if __name__ == "__main__":
    main()
