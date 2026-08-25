"""Read-only, provenance-rich inspection exports for eventual ML experiments."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
import json
import os
from pathlib import Path
from typing import Iterable

from .config import Settings
from .quality import DataQualityError
from .score_run import _dotenv_values


@dataclass(frozen=True, slots=True)
class TrainingDatasetRow:
    """One dated score feature paired with one already-completed future label."""

    score_snapshot_id: str
    security_id: str
    ticker: str
    issuer_name: str
    score_date: date
    decision_at: datetime
    score_data_cutoff_at: datetime
    model_version: str
    feature_registry_hash: str
    protocol_version: str
    sector_code: str
    baseline_score: Decimal
    baseline_rank: int
    feature_key: str
    feature_version: str
    definition_hash: str
    percentile: Decimal
    feature_weight: Decimal
    contribution: Decimal
    horizon_sessions: int
    execution_date: date
    outcome_date: date
    security_return: Decimal
    benchmark_return: Decimal
    benchmark_relative_return: Decimal
    outcome_data_cutoff_at: datetime

    def csv_record(self) -> dict[str, str]:
        record = asdict(self)
        return {
            key: value.isoformat() if isinstance(value, (date, datetime)) else str(value)
            for key, value in record.items()
        }


@dataclass(frozen=True, slots=True)
class TrainingDatasetInspection:
    horizon_sessions: int
    training_example_count: int
    feature_row_count: int
    score_date_count: int
    feature_identities: tuple[str, ...]
    first_score_date: date | None
    latest_score_date: date | None

    def to_dict(self) -> dict[str, object]:
        return {
            "horizon_sessions": self.horizon_sessions,
            "training_example_count": self.training_example_count,
            "feature_row_count": self.feature_row_count,
            "score_date_count": self.score_date_count,
            "feature_identities": list(self.feature_identities),
            "first_score_date": self.first_score_date.isoformat() if self.first_score_date else None,
            "latest_score_date": self.latest_score_date.isoformat() if self.latest_score_date else None,
            "label_definition": "split-adjusted future price return relative to SPY; completed labels only",
        }


def inspect_training_dataset(
    rows: Iterable[TrainingDatasetRow], *, expected_horizon_sessions: int | None = None,
) -> TrainingDatasetInspection:
    """Verify long-format examples are coherent before they are exported or modeled."""
    source = tuple(rows)
    if not source:
        return TrainingDatasetInspection(expected_horizon_sessions or 0, 0, 0, 0, (), None, None)
    horizons = {row.horizon_sessions for row in source}
    if len(horizons) != 1:
        raise DataQualityError("training dataset inspection requires exactly one horizon")
    if expected_horizon_sessions is not None and next(iter(horizons)) != expected_horizon_sessions:
        raise DataQualityError("training dataset does not match its requested horizon")
    feature_sets: dict[str, set[str]] = {}
    score_dates: set[date] = set()
    seen: set[tuple[str, str, str]] = set()
    for row in source:
        identity = (row.score_snapshot_id, row.feature_key, row.feature_version)
        if identity in seen:
            raise DataQualityError("duplicate score feature in the training dataset")
        seen.add(identity)
        feature = f"{row.feature_key}@{row.feature_version}"
        feature_sets.setdefault(row.score_snapshot_id, set()).add(feature)
        score_dates.add(row.score_date)
        if not Decimal("0") <= row.percentile <= Decimal("1"):
            raise DataQualityError("feature percentile must be between zero and one")
        if row.feature_weight <= 0 or row.contribution < 0:
            raise DataQualityError("training feature weight and contribution must be non-negative")
    expected = next(iter(feature_sets.values()))
    if any(features != expected for features in feature_sets.values()):
        raise DataQualityError("training examples do not share one complete feature schema")
    return TrainingDatasetInspection(
        next(iter(horizons)), len(feature_sets), len(source), len(score_dates),
        tuple(sorted(expected)), min(score_dates), max(score_dates),
    )


def load_completed_training_dataset(
    *, settings: Settings, horizon_sessions: int
) -> tuple[TrainingDatasetRow, ...]:
    """Load only valid, completed labels and the exact feature ranks used at scoring."""
    if horizon_sessions not in (5, 20, 60):
        raise DataQualityError("training dataset horizon must be one of 5, 20, or 60 sessions")
    settings.require_runtime_storage()
    assert settings.database_url is not None
    import psycopg

    with psycopg.connect(settings.database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT ss.score_snapshot_id::text, ss.security_id::text,
                      COALESCE(listing.ticker, 'Unavailable'), security.issuer_name,
                      ss.score_date, ss.decision_at, ss.data_cutoff_at, ss.model_version,
                      ss.feature_version, ss.protocol_version, explanation.sector_code,
                      ss.score, ss.rank, explanation.feature_key, explanation.feature_version,
                      explanation.definition_hash, explanation.percentile, explanation.feature_weight,
                      explanation.contribution, outcome.horizon_sessions, outcome.execution_date,
                      outcome.outcome_date, outcome.security_return, outcome.benchmark_return,
                      outcome.benchmark_relative_return, outcome.data_cutoff_at
               FROM quantrade.forward_score_outcomes outcome
               JOIN quantrade.score_snapshots ss ON ss.score_snapshot_id = outcome.score_snapshot_id
               JOIN quantrade.securities security ON security.security_id = ss.security_id
               JOIN quantrade.score_explanations explanation ON explanation.score_snapshot_id = ss.score_snapshot_id
               LEFT JOIN LATERAL (
                   SELECT ticker FROM quantrade.listings
                   WHERE security_id = ss.security_id
                     AND valid_from <= ss.score_date
                     AND (valid_to IS NULL OR valid_to > ss.score_date)
                   ORDER BY valid_from DESC
                   LIMIT 1
               ) listing ON TRUE
               WHERE outcome.horizon_sessions = %s
                 AND outcome.status = 'completed'
                 AND ss.eligible
                 AND explanation.percentile IS NOT NULL
                 AND explanation.contribution IS NOT NULL
               ORDER BY ss.score_date ASC, ss.security_id ASC, explanation.feature_key ASC""",
            (horizon_sessions,),
        )
        return tuple(TrainingDatasetRow(*row) for row in cursor.fetchall())


def write_training_dataset_export(
    *, rows: Iterable[TrainingDatasetRow], destination: Path, horizon_sessions: int | None = None,
) -> TrainingDatasetInspection:
    """Write a stable long-form CSV and adjacent inspection metadata, with no mutation of research data."""
    source = tuple(rows)
    inspection = inspect_training_dataset(source, expected_horizon_sessions=horizon_sessions)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(TrainingDatasetRow.__dataclass_fields__)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(row.csv_record() for row in source)
    metadata_path = destination.with_suffix(".json")
    metadata_path.write_text(json.dumps(inspection.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return inspection


def _settings(env_file: Path) -> Settings:
    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export completed forward score labels with their exact score features")
    parser.add_argument("--horizon-sessions", type=int, choices=(5, 20, 60), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    rows = load_completed_training_dataset(
        settings=_settings(arguments.env_file), horizon_sessions=arguments.horizon_sessions,
    )
    inspection = write_training_dataset_export(
        rows=rows, destination=arguments.output, horizon_sessions=arguments.horizon_sessions,
    )
    print(
        f"training_examples={inspection.training_example_count}; feature_rows={inspection.feature_row_count}; "
        f"score_dates={inspection.score_date_count}; horizon_sessions={arguments.horizon_sessions}"
    )


if __name__ == "__main__":
    main()
