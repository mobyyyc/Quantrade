"""Immutable raw model predictions attached to published score snapshots."""

from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal
import os
from pathlib import Path
from typing import Iterable

from .active_model import load_active_model
from .config import Settings
from .ml_scoring import ModelScore
from .quality import DataQualityError


PREDICTION_HORIZON_SESSIONS = 20
PREDICTION_BENCHMARK = "SPY"


def persist_score_predictions(*, database_url: str, snapshots: Iterable[object],
                              scores: Iterable[ModelScore]) -> int:
    snapshot_by_security = {str(snapshot.security_id): snapshot for snapshot in snapshots}  # type: ignore[attr-defined]
    eligible_scores = [score for score in scores if score.eligible]
    if any(score.predicted_relative_return is None for score in eligible_scores):
        raise DataQualityError("eligible model scores require a raw relative-return prediction")
    if set(snapshot_by_security) != {score.security_id for score in scores}:
        raise DataQualityError("prediction persistence requires the complete score snapshot set")

    import psycopg
    inserted = 0
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        for score in eligible_scores:
            snapshot = snapshot_by_security[score.security_id]
            cursor.execute(
                """SELECT score_snapshot_id
                   FROM quantrade.score_snapshots
                   WHERE security_id = %s AND decision_at = %s AND model_version = %s
                     AND feature_version = %s AND protocol_version = %s""",
                snapshot.identity(),  # type: ignore[attr-defined]
            )
            row = cursor.fetchone()
            if row is None:
                raise DataQualityError(f"score snapshot is missing for prediction: {score.security_id}")
            score_snapshot_id = row[0]
            cursor.execute(
                """INSERT INTO quantrade.score_predictions
                       (score_snapshot_id, benchmark_ticker, horizon_sessions,
                        predicted_benchmark_relative_return)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (score_snapshot_id) DO NOTHING""",
                (score_snapshot_id, PREDICTION_BENCHMARK, PREDICTION_HORIZON_SESSIONS,
                 score.predicted_relative_return),
            )
            inserted += cursor.rowcount
            if cursor.rowcount == 0:
                cursor.execute(
                    """SELECT benchmark_ticker, horizon_sessions, predicted_benchmark_relative_return
                       FROM quantrade.score_predictions WHERE score_snapshot_id = %s""",
                    (score_snapshot_id,),
                )
                existing = cursor.fetchone()
                expected = (PREDICTION_BENCHMARK, PREDICTION_HORIZON_SESSIONS,
                            score.predicted_relative_return)
                if existing != expected:
                    raise DataQualityError(f"conflicting immutable prediction for {score.security_id}")
        connection.commit()
    return inserted


def backfill_active_model_predictions(*, database_url: str, through_date: date | None = None) -> int:
    """Reconstruct raw predictions from immutable contribution rows for existing snapshots."""
    model = load_active_model(database_url)
    active_feature_count = sum(coefficient != 0 for coefficient in model.coefficients)
    if active_feature_count < 1:
        raise DataQualityError("active model has no non-zero coefficients")
    target_mean = Decimal(str(model.target_mean))

    import psycopg
    inserted = 0
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT snapshot.score_snapshot_id, snapshot.score_date,
                      COUNT(explanation.contribution), SUM(explanation.contribution)
               FROM quantrade.score_snapshots snapshot
               JOIN quantrade.score_explanations explanation
                 ON explanation.score_snapshot_id = snapshot.score_snapshot_id
               LEFT JOIN quantrade.score_predictions prediction
                 ON prediction.score_snapshot_id = snapshot.score_snapshot_id
               WHERE snapshot.model_version = %s AND snapshot.eligible
                 AND prediction.score_snapshot_id IS NULL
                 AND (%s::date IS NULL OR snapshot.score_date <= %s::date)
               GROUP BY snapshot.score_snapshot_id, snapshot.score_date
               ORDER BY snapshot.score_date, snapshot.score_snapshot_id""",
            (model.model_version, through_date, through_date),
        )
        rows = cursor.fetchall()
        for score_snapshot_id, score_date, contribution_count, contribution_sum in rows:
            if contribution_count != active_feature_count or contribution_sum is None:
                raise DataQualityError(
                    f"incomplete model contributions for prediction backfill: {score_snapshot_id}@{score_date}"
                )
            prediction = (target_mean + Decimal(contribution_sum)).quantize(Decimal("0.000000000001"))
            cursor.execute(
                """INSERT INTO quantrade.score_predictions
                       (score_snapshot_id, benchmark_ticker, horizon_sessions,
                        predicted_benchmark_relative_return)
                   VALUES (%s, %s, %s, %s)""",
                (score_snapshot_id, PREDICTION_BENCHMARK, PREDICTION_HORIZON_SESSIONS, prediction),
            )
            inserted += 1
        connection.commit()
    return inserted


def _dotenv_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill immutable raw predictions for active-model scores")
    parser.add_argument("--through-date", type=date.fromisoformat)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    values = dict(os.environ)
    values.update(_dotenv_values(arguments.env_file))
    settings = Settings.from_environment(values)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    inserted = backfill_active_model_predictions(
        database_url=settings.database_url, through_date=arguments.through_date,
    )
    print(f"score_predictions_inserted={inserted}")


if __name__ == "__main__":
    main()
