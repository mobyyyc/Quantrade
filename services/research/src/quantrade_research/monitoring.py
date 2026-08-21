"""Operational checks for freshness, failed runs, and score-run anomalies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from typing import Iterable, Literal


Severity = Literal["warning", "critical"]


@dataclass(frozen=True, slots=True)
class MonitoringAlert:
    code: str
    severity: Severity
    detail: str


@dataclass(frozen=True, slots=True)
class ScoreRunSummary:
    score_date: date
    eligible_count: int
    mean_score: Decimal | None


@dataclass(frozen=True, slots=True)
class MonitoringPolicy:
    minimum_eligible_count: int = 1
    maximum_eligible_count_drop: Decimal = Decimal("0.30")
    maximum_mean_score_shift: Decimal = Decimal("20")


def failed_manifest_ids(manifest_directory: Path) -> tuple[str, ...]:
    """Return failed run IDs from canonical manifests without treating unreadable files as success."""
    failed: list[str] = []
    if not manifest_directory.exists():
        return ()
    for path in sorted(manifest_directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            failed.append(f"unreadable:{path.name}")
            continue
        if payload.get("status") == "failed":
            failed.append(str(payload.get("run_id") or f"unnamed:{path.name}"))
    return tuple(failed)


def evaluate_monitoring(
    *,
    expected_price_date: date,
    expected_score_date: date,
    latest_price_date: date | None,
    latest_score: ScoreRunSummary | None,
    previous_score: ScoreRunSummary | None = None,
    failed_runs: Iterable[str] = (),
    policy: MonitoringPolicy = MonitoringPolicy(),
) -> tuple[MonitoringAlert, ...]:
    alerts: list[MonitoringAlert] = []
    if latest_price_date is None or latest_price_date < expected_price_date:
        alerts.append(MonitoringAlert("stale_market_data", "critical", f"latest price date is {latest_price_date}; expected {expected_price_date}"))
    if latest_score is None or latest_score.score_date < expected_score_date:
        alerts.append(MonitoringAlert("stale_scores", "critical", f"latest score date is {latest_score.score_date if latest_score else None}; expected {expected_score_date}"))
    for run_id in failed_runs:
        alerts.append(MonitoringAlert("failed_run", "critical", f"run manifest reports failure: {run_id}"))
    if latest_score is None:
        return tuple(alerts)
    if latest_score.eligible_count < policy.minimum_eligible_count:
        alerts.append(MonitoringAlert("insufficient_eligible_scores", "critical", f"eligible count is {latest_score.eligible_count}; minimum is {policy.minimum_eligible_count}"))
    if previous_score and previous_score.eligible_count:
        drop = Decimal(previous_score.eligible_count - latest_score.eligible_count) / Decimal(previous_score.eligible_count)
        if drop > policy.maximum_eligible_count_drop:
            alerts.append(MonitoringAlert("eligible_count_drop", "warning", f"eligible count fell {drop:.1%} from {previous_score.eligible_count} to {latest_score.eligible_count}"))
    if previous_score and latest_score.mean_score is not None and previous_score.mean_score is not None:
        shift = abs(latest_score.mean_score - previous_score.mean_score)
        if shift > policy.maximum_mean_score_shift:
            alerts.append(MonitoringAlert("mean_score_shift", "warning", f"mean score shifted {shift} points from the prior published run"))
    return tuple(alerts)


class PostgresOperationalMonitor:
    """Read-only monitor backed by normalized research outputs."""

    def __init__(self, database_url: str) -> None:
        import psycopg
        self._connection = psycopg.connect(database_url)

    def close(self) -> None:
        self._connection.close()

    def latest_price_date(self) -> date | None:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT MAX(session_date) FROM quantrade.daily_price_bars WHERE session = 'regular'")
            return cursor.fetchone()[0]

    def score_runs(self) -> tuple[ScoreRunSummary | None, ScoreRunSummary | None]:
        with self._connection.cursor() as cursor:
            cursor.execute("""WITH dates AS (SELECT DISTINCT score_date FROM quantrade.score_snapshots ORDER BY score_date DESC LIMIT 2)
                SELECT d.score_date, COUNT(s.score_snapshot_id) FILTER (WHERE s.eligible), AVG(s.score) FILTER (WHERE s.eligible)
                FROM dates d LEFT JOIN quantrade.score_snapshots s ON s.score_date = d.score_date GROUP BY d.score_date ORDER BY d.score_date DESC""")
            rows = [ScoreRunSummary(row[0], int(row[1]), row[2]) for row in cursor.fetchall()]
        return (rows[0] if rows else None, rows[1] if len(rows) > 1 else None)
