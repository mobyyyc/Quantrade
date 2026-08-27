"""Materialize one small, immutable forward-label readiness read model per day."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .config import Settings
from .quality import DataQualityError


HORIZONS = (5, 20, 60)


@dataclass(frozen=True, slots=True)
class ForwardReadinessMetric:
    horizon_sessions: int
    completed_labels: int
    withheld_labels: int
    pending_labels: int
    completed_score_dates: int
    latest_outcome_date: date | None

    def __post_init__(self) -> None:
        if self.horizon_sessions not in HORIZONS:
            raise DataQualityError("unsupported forward-readiness horizon")
        if min(self.completed_labels, self.withheld_labels, self.pending_labels, self.completed_score_dates) < 0:
            raise DataQualityError("forward-readiness metrics cannot be negative")


def current_forward_readiness(connection) -> tuple[ForwardReadinessMetric, ...]:
    """Aggregate once, avoiding the page-time three-horizon score-row expansion."""
    with connection.cursor() as cursor:
        cursor.execute(
            """WITH eligible_snapshots AS MATERIALIZED (
                     SELECT snapshot.score_snapshot_id, snapshot.score_date
                     FROM quantrade.daily_research_runs AS run
                     JOIN quantrade.score_snapshots AS snapshot
                       ON snapshot.score_date = run.score_date
                      AND snapshot.decision_at = run.decision_at
                     WHERE run.status = 'completed' AND snapshot.eligible
                 ), eligible_total AS (
                     SELECT COUNT(*)::integer AS total FROM eligible_snapshots
                 ), outcome_summary AS (
                     SELECT outcome.horizon_sessions,
                            COUNT(*) FILTER (WHERE outcome.status = 'completed')::integer AS completed_labels,
                            COUNT(*) FILTER (WHERE outcome.status = 'withheld')::integer AS withheld_labels,
                            COUNT(DISTINCT snapshot.score_date) FILTER (WHERE outcome.status = 'completed')::integer AS completed_score_dates,
                            MAX(outcome.outcome_date) AS latest_outcome_date
                     FROM eligible_snapshots AS snapshot
                     JOIN quantrade.forward_score_outcomes AS outcome
                       ON outcome.score_snapshot_id = snapshot.score_snapshot_id
                     GROUP BY outcome.horizon_sessions
                 )
                 SELECT horizons.horizon_sessions,
                        COALESCE(summary.completed_labels, 0),
                        COALESCE(summary.withheld_labels, 0),
                        total.total - COALESCE(summary.completed_labels, 0) - COALESCE(summary.withheld_labels, 0),
                        COALESCE(summary.completed_score_dates, 0),
                        summary.latest_outcome_date
                 FROM unnest(ARRAY[5, 20, 60]::smallint[]) AS horizons(horizon_sessions)
                 CROSS JOIN eligible_total AS total
                 LEFT JOIN outcome_summary AS summary ON summary.horizon_sessions = horizons.horizon_sessions
                 ORDER BY horizons.horizon_sessions"""
        )
        rows = cursor.fetchall()
    metrics = tuple(ForwardReadinessMetric(*row) for row in rows)
    if tuple(metric.horizon_sessions for metric in metrics) != HORIZONS:
        raise DataQualityError("forward-readiness summary did not return every supported horizon")
    return metrics


def materialize_forward_readiness_snapshot(*, settings: Settings, as_of_date: date) -> bool:
    """Append the daily snapshot once. A rerun leaves immutable evidence unchanged."""
    settings.require_runtime_storage()
    assert settings.database_url is not None
    import psycopg

    with psycopg.connect(settings.database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM quantrade.forward_outcome_readiness_snapshots WHERE as_of_date = %s",
            (as_of_date,),
        )
        if cursor.fetchone() is not None:
            return False
        metrics = current_forward_readiness(connection)
        cursor.execute(
            """INSERT INTO quantrade.forward_outcome_readiness_snapshots (as_of_date)
               VALUES (%s) RETURNING forward_outcome_readiness_snapshot_id""",
            (as_of_date,),
        )
        snapshot_id = cursor.fetchone()[0]
        cursor.executemany(
            """INSERT INTO quantrade.forward_outcome_readiness_metrics
                   (forward_outcome_readiness_snapshot_id, horizon_sessions, completed_labels,
                    withheld_labels, pending_labels, completed_score_dates, latest_outcome_date)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            [
                (snapshot_id, metric.horizon_sessions, metric.completed_labels, metric.withheld_labels,
                 metric.pending_labels, metric.completed_score_dates, metric.latest_outcome_date)
                for metric in metrics
            ],
        )
        connection.commit()
    return True
