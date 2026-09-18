"""Publish a read-only report of genuinely forward active-model evidence."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from .quality import DataQualityError
from .score_run import _settings


SCHEMA_VERSION = "quantrade_forward_evidence_report_v1"
HORIZONS = (5, 20, 60)
FORMATION_PROTOCOL = "monthly_last_session_next_open_v1"
TORONTO = ZoneInfo("America/Toronto")


@dataclass(frozen=True, slots=True)
class Deployment:
    model_version: str
    deployed_at: datetime
    approval_scope: str


@dataclass(frozen=True, slots=True)
class HealthObservation:
    score_date: date
    health_status: str
    cohort_size: int
    eligible_count: int
    coverage_ratio: Decimal
    top_20_churn_ratio: Decimal | None
    mean_normalized_rank_change: Decimal | None
    artifact_hash_matches: bool
    registry_hash_matches: bool
    explanation_lineage_matches: bool


@dataclass(frozen=True, slots=True)
class DriftObservation:
    score_date: date
    feature_key: str
    feature_version: str
    population_stability_index: Decimal | None
    status: str


@dataclass(frozen=True, slots=True)
class ForwardLabelEvidence:
    horizon_sessions: int
    eligible_labels: int
    completed_labels: int
    withheld_labels: int
    pending_labels: int
    completed_score_dates: int
    latest_outcome_date: date | None


@dataclass(frozen=True, slots=True)
class OfficialFormation:
    score_date: date
    execution_date: date


@dataclass(frozen=True, slots=True)
class PortfolioOutcome:
    score_date: date
    horizon_sessions: int
    status: str
    outcome_date: date
    portfolio_return: Decimal | None
    benchmark_return: Decimal | None
    benchmark_relative_return: Decimal | None
    unavailable_reason: str | None


@dataclass(frozen=True, slots=True)
class MissedFormation:
    formation_date: date
    expected_execution_date: date
    reason_code: str


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _decimal_mean(values: list[Decimal]) -> str | None:
    return _decimal(sum(values, Decimal(0)) / Decimal(len(values))) if values else None


def _validate_period(deployment: Deployment, period_start: date, period_end: date) -> None:
    if deployment.deployed_at.tzinfo is None or deployment.deployed_at.utcoffset() is None:
        raise DataQualityError("deployment time requires a UTC offset")
    if period_start > period_end:
        raise DataQualityError("forward-evidence period start must not follow its end")
    if period_start < deployment.deployed_at.astimezone(TORONTO).date():
        raise DataQualityError("forward evidence cannot begin before the active model deployment date")


def build_report(
    *, deployment: Deployment, period_start: date, period_end: date,
    health: tuple[HealthObservation, ...], drift: tuple[DriftObservation, ...],
    forward_labels: tuple[ForwardLabelEvidence, ...],
    formations: tuple[OfficialFormation, ...], outcomes: tuple[PortfolioOutcome, ...],
    missed_formations: tuple[MissedFormation, ...], code_revision: str,
) -> dict[str, object]:
    """Build a deterministic report without training, selecting, or promoting a model."""
    _validate_period(deployment, period_start, period_end)
    if tuple(item.horizon_sessions for item in forward_labels) != HORIZONS:
        raise DataQualityError("forward evidence must include the 5, 20, and 60 session horizons")
    if any(
        min(
            item.eligible_labels, item.completed_labels, item.withheld_labels,
            item.pending_labels, item.completed_score_dates,
        ) < 0
        for item in forward_labels
    ):
        raise DataQualityError("forward-label counts cannot be negative")
    if any(item.pending_labels != item.eligible_labels - item.completed_labels - item.withheld_labels
           for item in forward_labels):
        raise DataQualityError("forward-label counts do not reconcile")
    for item in health:
        if not period_start <= item.score_date <= period_end:
            raise DataQualityError("health observation falls outside the reporting period")
        if item.health_status not in {"healthy", "warning", "critical"}:
            raise DataQualityError("health observation has an invalid status")
        if item.cohort_size <= 0 or not 0 <= item.eligible_count <= item.cohort_size:
            raise DataQualityError("health observation has invalid coverage counts")
    if any(item.score_date < period_start or item.score_date > period_end for item in formations):
        raise DataQualityError("official formation falls outside the reporting period")

    health_rows = sorted(health, key=lambda item: item.score_date)
    coverage_values = [item.coverage_ratio for item in health_rows]
    churn_values = [item.top_20_churn_ratio for item in health_rows if item.top_20_churn_ratio is not None]
    rank_values = [item.mean_normalized_rank_change for item in health_rows if item.mean_normalized_rank_change is not None]
    health_statuses = Counter(item.health_status for item in health_rows)
    drift_by_feature: dict[tuple[str, str], list[DriftObservation]] = defaultdict(list)
    for item in drift:
        if not period_start <= item.score_date <= period_end:
            raise DataQualityError("drift observation falls outside the reporting period")
        drift_by_feature[(item.feature_key, item.feature_version)].append(item)
    drift_summary = []
    for (feature_key, version), observations in sorted(drift_by_feature.items()):
        ordered = sorted(observations, key=lambda item: item.score_date)
        measured = [item.population_stability_index for item in ordered if item.population_stability_index is not None]
        statuses = Counter(item.status for item in ordered)
        drift_summary.append({
            "feature_key": feature_key,
            "feature_version": version,
            "observation_count": len(ordered),
            "measured_psi_count": len(measured),
            "latest_psi": _decimal(ordered[-1].population_stability_index),
            "maximum_psi": _decimal(max(measured)) if measured else None,
            "warning_count": statuses["warning"],
            "critical_count": statuses["critical"],
            "latest_status": ordered[-1].status,
        })

    formation_dates = {item.score_date for item in formations}
    if len(formation_dates) != len(formations):
        raise DataQualityError("official formations contain duplicate score dates")
    outcome_by_horizon: dict[int, list[PortfolioOutcome]] = defaultdict(list)
    for item in outcomes:
        if item.horizon_sessions not in HORIZONS or item.score_date not in formation_dates:
            raise DataQualityError("portfolio outcome does not match an in-period official formation")
        if item.status == "completed":
            if None in (item.portfolio_return, item.benchmark_return, item.benchmark_relative_return):
                raise DataQualityError("completed portfolio outcome is missing returns")
            if item.benchmark_relative_return != item.portfolio_return - item.benchmark_return:
                raise DataQualityError("portfolio outcome does not reconcile to SPY")
        elif item.status == "withheld":
            if item.unavailable_reason is None:
                raise DataQualityError("withheld portfolio outcome is missing its reason")
        else:
            raise DataQualityError("portfolio outcome has an invalid status")
        outcome_by_horizon[item.horizon_sessions].append(item)
    basket_horizons = []
    for horizon in HORIZONS:
        observations = sorted(outcome_by_horizon[horizon], key=lambda item: (item.score_date, item.outcome_date))
        completed = [item for item in observations if item.status == "completed"]
        withheld = [item for item in observations if item.status == "withheld"]
        pending = len(formations) - len(completed) - len(withheld)
        if pending < 0:
            raise DataQualityError("portfolio outcomes exceed official formations")
        basket_horizons.append({
            "horizon_sessions": horizon,
            "formation_count": len(formations),
            "completed_outcomes": len(completed),
            "withheld_outcomes": len(withheld),
            "pending_outcomes": pending,
            "outperformed_spy_count": sum(item.benchmark_relative_return > 0 for item in completed),
            "average_basket_return": _decimal_mean([item.portfolio_return for item in completed]),
            "average_spy_return": _decimal_mean([item.benchmark_return for item in completed]),
            "average_benchmark_relative_return": _decimal_mean(
                [item.benchmark_relative_return for item in completed]
            ),
        })

    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "code_revision": code_revision,
        "read_only": True,
        "model": {
            "model_version": deployment.model_version,
            "deployed_at": deployment.deployed_at.astimezone(timezone.utc).isoformat(),
            "approval_scope": deployment.approval_scope,
        },
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "health": {
            "snapshot_count": len(health_rows),
            "first_score_date": health_rows[0].score_date.isoformat() if health_rows else None,
            "latest_score_date": health_rows[-1].score_date.isoformat() if health_rows else None,
            "status_counts": dict(sorted(health_statuses.items())),
            "minimum_coverage_ratio": _decimal(min(coverage_values)) if coverage_values else None,
            "mean_coverage_ratio": _decimal_mean(coverage_values),
            "latest_coverage_ratio": _decimal(coverage_values[-1]) if coverage_values else None,
            "integrity_verified_for_every_snapshot": bool(health_rows) and all(
                item.artifact_hash_matches and item.registry_hash_matches
                and item.explanation_lineage_matches for item in health_rows
            ),
            "rank_stability": {
                "comparison_count": len(churn_values),
                "mean_top_20_churn_ratio": _decimal_mean(churn_values),
                "maximum_top_20_churn_ratio": _decimal(max(churn_values)) if churn_values else None,
                "mean_normalized_rank_change": _decimal_mean(rank_values),
                "maximum_normalized_rank_change": _decimal(max(rank_values)) if rank_values else None,
            },
            "feature_drift": drift_summary,
        },
        "forward_labels": [
            {**asdict(item), "latest_outcome_date": item.latest_outcome_date.isoformat()
             if item.latest_outcome_date else None}
            for item in forward_labels
        ],
        "official_basket_vs_spy": {
            "formation_protocol": FORMATION_PROTOCOL,
            "formation_count": len(formations),
            "missed_formation_count": len(missed_formations),
            "status": (
                "awaiting_official_formation" if not formations
                else "awaiting_completed_outcome" if not any(item.status == "completed" for item in outcomes)
                else "observed"
            ),
            "horizons": basket_horizons,
            "formations": [
                {"score_date": item.score_date.isoformat(), "execution_date": item.execution_date.isoformat()}
                for item in sorted(formations, key=lambda item: item.score_date)
            ],
            "outcomes": [
                {
                    **asdict(item),
                    "score_date": item.score_date.isoformat(),
                    "outcome_date": item.outcome_date.isoformat(),
                    "portfolio_return": _decimal(item.portfolio_return),
                    "benchmark_return": _decimal(item.benchmark_return),
                    "benchmark_relative_return": _decimal(item.benchmark_relative_return),
                }
                for item in sorted(outcomes, key=lambda item: (item.score_date, item.horizon_sessions))
            ],
            "missed_formations": [
                {
                    "formation_date": item.formation_date.isoformat(),
                    "expected_execution_date": item.expected_execution_date.isoformat(),
                    "reason_code": item.reason_code,
                }
                for item in sorted(missed_formations, key=lambda item: item.formation_date)
            ],
        },
        "limitations": [
            "This is monitoring evidence, not a model-selection, retraining, or promotion input.",
            "Only canonical completed live publications on or after the active deployment are included.",
            "Historical replay and the consumed holdout are excluded from forward evidence.",
            "Basket-versus-SPY evidence uses only official pre-existing monthly formations; no retrospective basket is constructed.",
            "Pending horizons are not treated as zero return, and withheld outcomes are not imputed.",
            "The Tier-B current-survivor cohort and static sectors remain survivorship-biased research inputs.",
        ],
    }
    logical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    payload["logical_sha256"] = sha256(logical_payload).hexdigest()
    return payload


class PostgresForwardEvidenceRepository:
    def __init__(self, database_url: str) -> None:
        import psycopg
        from psycopg import IsolationLevel

        self._connection = psycopg.connect(database_url)
        self._connection.read_only = True
        self._connection.isolation_level = IsolationLevel.REPEATABLE_READ

    def close(self) -> None:
        self._connection.close()

    def active_deployment(self) -> Deployment:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT model_version, deployed_at, approval_scope
                   FROM quantrade.model_deployments
                   ORDER BY deployed_at DESC, created_at DESC LIMIT 1"""
            )
            row = cursor.fetchone()
        if row is None:
            raise DataQualityError("no active model deployment exists")
        return Deployment(str(row[0]), row[1], str(row[2]))

    def latest_completed_score_date(self, model_version: str) -> date:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT MAX(run.score_date)
                   FROM quantrade.daily_research_runs run
                   WHERE run.status='completed'
                     AND EXISTS (
                       SELECT 1 FROM quantrade.score_snapshots snapshot
                       WHERE snapshot.score_date=run.score_date
                         AND snapshot.decision_at=run.decision_at
                         AND snapshot.model_version=%s
                     )""",
                (model_version,),
            )
            value = cursor.fetchone()[0]
        if value is None:
            raise DataQualityError("the active model has no completed live publication")
        return value

    def health(self, model_version: str, start: date, end: date) -> tuple[HealthObservation, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT score_date, health_status, cohort_size, eligible_count, coverage_ratio,
                          top_20_churn_ratio, mean_normalized_rank_change,
                          artifact_hash_matches, registry_hash_matches, explanation_lineage_matches
                   FROM quantrade.model_health_snapshots
                   WHERE model_version=%s AND score_date BETWEEN %s AND %s
                   ORDER BY score_date""",
                (model_version, start, end),
            )
            return tuple(HealthObservation(*row) for row in cursor.fetchall())

    def drift(self, model_version: str, start: date, end: date) -> tuple[DriftObservation, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT snapshot.score_date, metric.feature_key, metric.feature_version,
                          metric.population_stability_index, metric.status
                   FROM quantrade.model_health_snapshots snapshot
                   JOIN quantrade.model_health_feature_metrics metric USING(model_health_snapshot_id)
                   WHERE snapshot.model_version=%s AND snapshot.score_date BETWEEN %s AND %s
                   ORDER BY metric.feature_key, metric.feature_version, snapshot.score_date""",
                (model_version, start, end),
            )
            return tuple(DriftObservation(*row) for row in cursor.fetchall())

    def forward_labels(self, model_version: str, start: date, end: date) -> tuple[ForwardLabelEvidence, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """WITH eligible AS MATERIALIZED (
                     SELECT snapshot.score_snapshot_id, snapshot.score_date
                     FROM quantrade.daily_research_runs run
                     JOIN quantrade.score_snapshots snapshot
                       ON snapshot.score_date=run.score_date
                      AND snapshot.decision_at=run.decision_at
                     WHERE run.status='completed' AND snapshot.eligible
                       AND snapshot.model_version=%s
                       AND snapshot.score_date BETWEEN %s AND %s
                   ), totals AS (
                     SELECT COUNT(*)::integer AS labels FROM eligible
                   ), outcomes AS (
                     SELECT outcome.horizon_sessions,
                            COUNT(*) FILTER (WHERE outcome.status='completed')::integer AS completed,
                            COUNT(*) FILTER (WHERE outcome.status='withheld')::integer AS withheld,
                            COUNT(DISTINCT eligible.score_date)
                              FILTER (WHERE outcome.status='completed')::integer AS completed_dates,
                            MAX(outcome.outcome_date)
                              FILTER (WHERE outcome.status='completed') AS latest_outcome
                     FROM eligible
                     JOIN quantrade.forward_score_outcomes outcome USING(score_snapshot_id)
                     WHERE outcome.outcome_date <= %s
                     GROUP BY outcome.horizon_sessions
                   )
                   SELECT horizon.horizon_sessions, totals.labels,
                          COALESCE(outcomes.completed,0), COALESCE(outcomes.withheld,0),
                          totals.labels-COALESCE(outcomes.completed,0)-COALESCE(outcomes.withheld,0),
                          COALESCE(outcomes.completed_dates,0), outcomes.latest_outcome
                   FROM unnest(ARRAY[5,20,60]::smallint[]) horizon(horizon_sessions)
                   CROSS JOIN totals
                   LEFT JOIN outcomes USING(horizon_sessions)
                   ORDER BY horizon.horizon_sessions""",
                (model_version, start, end, end),
            )
            return tuple(ForwardLabelEvidence(*row) for row in cursor.fetchall())

    def formations(self, model_version: str, start: date, end: date) -> tuple[OfficialFormation, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT score_date, execution_date FROM quantrade.paper_portfolio_runs
                   WHERE model_version=%s AND formation_protocol=%s
                     AND score_date BETWEEN %s AND %s ORDER BY score_date""",
                (model_version, FORMATION_PROTOCOL, start, end),
            )
            return tuple(OfficialFormation(*row) for row in cursor.fetchall())

    def portfolio_outcomes(self, model_version: str, start: date, end: date) -> tuple[PortfolioOutcome, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT run.score_date, outcome.horizon_sessions, outcome.status,
                          outcome.outcome_date, outcome.portfolio_return,
                          outcome.benchmark_return, outcome.benchmark_relative_return,
                          outcome.unavailable_reason
                   FROM quantrade.paper_portfolio_runs run
                   JOIN quantrade.paper_portfolio_outcomes outcome USING(paper_portfolio_run_id)
                   WHERE run.model_version=%s AND run.formation_protocol=%s
                     AND run.score_date BETWEEN %s AND %s AND outcome.outcome_date <= %s
                   ORDER BY run.score_date, outcome.horizon_sessions""",
                (model_version, FORMATION_PROTOCOL, start, end, end),
            )
            return tuple(PortfolioOutcome(*row) for row in cursor.fetchall())

    def missed_formations(self, start: date, end: date) -> tuple[MissedFormation, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT formation_date, expected_execution_date, reason_code
                   FROM quantrade.missed_paper_portfolio_formations
                   WHERE formation_date BETWEEN %s AND %s ORDER BY formation_date""",
                (start, end),
            )
            return tuple(MissedFormation(*row) for row in cursor.fetchall())


def _percent(value: str | None) -> str:
    return "unavailable" if value is None else f"{Decimal(value) * 100:.2f}%"


def render_summary(report: dict[str, object]) -> str:
    model = report["model"]
    period = report["period"]
    health = report["health"]
    rank = health["rank_stability"]
    basket = report["official_basket_vs_spy"]
    lines = [
        "# Forward model evidence",
        "",
        f"Model: `{model['model_version']}`",
        "",
        f"Period: {period['start']} through {period['end']}",
        "",
        "This report is monitoring-only. It does not train, select, or promote a model.",
        "",
        "## Coverage and stability",
        "",
        f"- Health snapshots: {health['snapshot_count']}.",
        f"- Latest eligible coverage: {_percent(health['latest_coverage_ratio'])}.",
        f"- Minimum eligible coverage: {_percent(health['minimum_coverage_ratio'])}.",
        f"- Mean top-20 churn: {_percent(rank['mean_top_20_churn_ratio'])}.",
        f"- Mean normalized rank change: {_percent(rank['mean_normalized_rank_change'])}.",
        f"- Every recorded artifact/registry/explanation integrity check passed: "
        f"{'yes' if health['integrity_verified_for_every_snapshot'] else 'not yet established'}.",
        "",
        "## Active-feature drift",
        "",
        "| Feature | Latest PSI | Maximum PSI | Latest status | Warnings | Critical |",
        "| --- | ---: | ---: | --- | ---: | ---: |",
    ]
    for row in health["feature_drift"]:
        lines.append(
            f"| {row['feature_key']}@{row['feature_version']} | "
            f"{row['latest_psi'] or 'forming'} | {row['maximum_psi'] or 'forming'} | "
            f"{row['latest_status']} | {row['warning_count']} | {row['critical_count']} |"
        )
    lines.extend([
        "",
        "## Forward label accumulation",
        "",
        "| Horizon | Eligible | Completed | Withheld | Pending | Completed score dates | Latest outcome |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ])
    for row in report["forward_labels"]:
        lines.append(
            f"| {row['horizon_sessions']} sessions | {row['eligible_labels']:,} | "
            f"{row['completed_labels']:,} | {row['withheld_labels']:,} | {row['pending_labels']:,} | "
            f"{row['completed_score_dates']:,} | {row['latest_outcome_date'] or 'unavailable'} |"
        )
    lines.extend([
        "",
        "## Official basket versus SPY",
        "",
        f"Status: `{basket['status']}`. Official formations: {basket['formation_count']}; "
        f"recorded missed formations: {basket['missed_formation_count']}.",
        "",
        "| Horizon | Completed | Withheld | Pending | Avg basket | Avg SPY | Avg difference | Outperformed |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in basket["horizons"]:
        lines.append(
            f"| {row['horizon_sessions']} sessions | {row['completed_outcomes']} | "
            f"{row['withheld_outcomes']} | {row['pending_outcomes']} | "
            f"{_percent(row['average_basket_return'])} | {_percent(row['average_spy_return'])} | "
            f"{_percent(row['average_benchmark_relative_return'])} | {row['outperformed_spy_count']} |"
        )
    lines.extend(["", "## Limits", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.extend(["", f"Logical evidence hash: `{report['logical_sha256']}`"])
    return "\n".join(lines) + "\n"


def publish_report(report: dict[str, object], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    files = {
        "evidence.json": json.dumps(report, sort_keys=True, indent=2) + "\n",
        "summary.md": render_summary(report),
    }
    hashes: dict[str, str] = {}
    for name, content in files.items():
        data = content.encode("utf-8")
        with (output / name).open("xb") as handle:
            handle.write(data)
        hashes[name] = sha256(data).hexdigest()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "completed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "logical_sha256": report["logical_sha256"],
        "sha256": hashes,
    }
    with (output / "manifest.json").open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, sort_keys=True, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--period-start", type=date.fromisoformat)
    parser.add_argument("--as-of-date", type=date.fromisoformat)
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.output.exists():
        parser.error("output already exists; evidence reports must not be overwritten")
    settings = _settings(arguments.env_file)
    if not settings.database_url:
        parser.error("DATABASE_URL is required")
    repository = PostgresForwardEvidenceRepository(settings.database_url)
    try:
        deployment = repository.active_deployment()
        period_start = arguments.period_start or deployment.deployed_at.astimezone(TORONTO).date()
        period_end = arguments.as_of_date or repository.latest_completed_score_date(deployment.model_version)
        report = build_report(
            deployment=deployment, period_start=period_start, period_end=period_end,
            health=repository.health(deployment.model_version, period_start, period_end),
            drift=repository.drift(deployment.model_version, period_start, period_end),
            forward_labels=repository.forward_labels(deployment.model_version, period_start, period_end),
            formations=repository.formations(deployment.model_version, period_start, period_end),
            outcomes=repository.portfolio_outcomes(deployment.model_version, period_start, period_end),
            missed_formations=repository.missed_formations(period_start, period_end),
            code_revision=arguments.code_revision,
        )
    finally:
        repository.close()
    publish_report(report, arguments.output)
    print(json.dumps({
        "output": str(arguments.output),
        "model_version": report["model"]["model_version"],
        "period": report["period"],
        "health_snapshots": report["health"]["snapshot_count"],
        "basket_status": report["official_basket_vs_spy"]["status"],
        "logical_sha256": report["logical_sha256"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
