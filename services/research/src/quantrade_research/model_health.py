"""Deterministic, immutable health monitoring for deployed score publications."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from math import log
from pathlib import Path
import re

from .active_model import _path_from_file_uri
from .features import baseline_feature_registry
from .quality import DataQualityError
from .score_run import _dotenv_values


COVERAGE_WARNING = Decimal("0.98")
COVERAGE_CRITICAL = Decimal("0.90")
MISSINGNESS_WARNING = Decimal("0.02")
MISSINGNESS_CRITICAL = Decimal("0.10")
PSI_WARNING = Decimal("0.10")
PSI_CRITICAL = Decimal("0.25")
TOP_20_CHURN_WARNING = Decimal("0.50")
NORMALIZED_RANK_CHANGE_WARNING = Decimal("0.15")
REFERENCE_DATES = 20
MINIMUM_REFERENCE_OBSERVATIONS = 100


@dataclass(frozen=True, slots=True)
class HealthAlert:
    code: str
    severity: str
    metric_key: str
    observed_value: str
    threshold_value: str
    detail: str


@dataclass(frozen=True, slots=True)
class FeatureHealth:
    feature_key: str
    feature_version: str
    definition_hash: str
    available_count: int
    unavailable_count: int
    missing_ratio: Decimal
    mean_percentile: Decimal | None
    reference_mean_percentile: Decimal | None
    population_stability_index: Decimal | None
    reference_observation_count: int
    status: str


@dataclass(frozen=True, slots=True)
class RankHealth:
    previous_score_date: date | None
    top_20_churn_ratio: Decimal | None
    mean_normalized_rank_change: Decimal | None


def _decimal(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.0000000001")), "f")


def population_stability_index(
    current: tuple[Decimal, ...], reference: tuple[Decimal, ...], bins: int = 10,
) -> Decimal | None:
    """Compare bounded percentile distributions with fixed bins and smoothing."""
    if len(current) < MINIMUM_REFERENCE_OBSERVATIONS or len(reference) < MINIMUM_REFERENCE_OBSERVATIONS:
        return None
    current_counts = [0] * bins
    reference_counts = [0] * bins
    for value in current:
        current_counts[min(bins - 1, max(0, int(value * bins)))] += 1
    for value in reference:
        reference_counts[min(bins - 1, max(0, int(value * bins)))] += 1
    epsilon = 1e-6
    value = 0.0
    for current_count, reference_count in zip(current_counts, reference_counts, strict=True):
        current_share = max(epsilon, current_count / len(current))
        reference_share = max(epsilon, reference_count / len(reference))
        value += (current_share - reference_share) * log(current_share / reference_share)
    return Decimal(str(value)).quantize(Decimal("0.0000000000000001"))


def feature_health(
    *, feature_key: str, feature_version: str, definition_hash: str,
    cohort_size: int, current: tuple[Decimal, ...], reference: tuple[Decimal, ...],
) -> FeatureHealth:
    if cohort_size <= 0 or len(current) > cohort_size:
        raise DataQualityError("invalid feature-health cohort counts")
    unavailable = cohort_size - len(current)
    missing = (Decimal(unavailable) / Decimal(cohort_size)).quantize(Decimal("0.0000000001"))
    psi = population_stability_index(current, reference)
    status = "insufficient_reference" if psi is None else "healthy"
    if missing > MISSINGNESS_CRITICAL or (psi is not None and psi > PSI_CRITICAL):
        status = "critical"
    elif missing > MISSINGNESS_WARNING or (psi is not None and psi > PSI_WARNING):
        status = "warning"
    return FeatureHealth(
        feature_key, feature_version, definition_hash, len(current), unavailable,
        missing,
        (sum(current, Decimal(0)) / Decimal(len(current))).quantize(Decimal("0.0000000000000001")) if current else None,
        (sum(reference, Decimal(0)) / Decimal(len(reference))).quantize(Decimal("0.0000000000000001")) if reference else None,
        psi, len(reference), status,
    )


def rank_health(
    current: dict[str, int], previous: dict[str, int], previous_score_date: date | None,
) -> RankHealth:
    if not current or not previous or previous_score_date is None:
        return RankHealth(previous_score_date, None, None)
    basket_size = min(20, len(current), len(previous))
    current_top = {key for key, _ in sorted(current.items(), key=lambda item: item[1])[:basket_size]}
    previous_top = {key for key, _ in sorted(previous.items(), key=lambda item: item[1])[:basket_size]}
    churn = (Decimal(basket_size - len(current_top & previous_top)) / Decimal(basket_size)).quantize(Decimal("0.0000000001"))
    common = current.keys() & previous.keys()
    normalized_change = (
        sum(
            (abs(Decimal(current[key]) / Decimal(len(current)) - Decimal(previous[key]) / Decimal(len(previous))) for key in common),
            Decimal(0),
        ) / Decimal(len(common))
        if common else None
    )
    if normalized_change is not None:
        normalized_change = normalized_change.quantize(Decimal("0.0000000001"))
    return RankHealth(previous_score_date, churn, normalized_change)


def _exclusion_code(reason: str | None) -> str:
    if not reason:
        return "unspecified_exclusion"
    lower = reason.lower()
    if "required_feature_rank_unavailable" in lower:
        return "required_active_input_unavailable"
    if "price" in lower or "session" in lower or "split-adjusted" in lower:
        return "price_history_unavailable"
    if "sector" in lower:
        return "sector_unavailable"
    if "filing" in lower or "asset" in lower or "income" in lower or "shares" in lower:
        return "fundamental_input_unavailable"
    return re.sub(r"[^a-z0-9]+", "_", lower).strip("_")[:80] or "other_exclusion"


def _feature_alerts(metrics: tuple[FeatureHealth, ...]) -> list[HealthAlert]:
    alerts: list[HealthAlert] = []
    for metric in metrics:
        key = f"{metric.feature_key}@{metric.feature_version}"
        if metric.missing_ratio > MISSINGNESS_CRITICAL:
            alerts.append(HealthAlert("feature_missingness", "critical", key, _decimal(metric.missing_ratio), _decimal(MISSINGNESS_CRITICAL), f"{key} missingness exceeds the critical threshold."))
        elif metric.missing_ratio > MISSINGNESS_WARNING:
            alerts.append(HealthAlert("feature_missingness", "warning", key, _decimal(metric.missing_ratio), _decimal(MISSINGNESS_WARNING), f"{key} missingness exceeds the warning threshold."))
        if metric.population_stability_index is None:
            continue
        if metric.population_stability_index > PSI_CRITICAL:
            alerts.append(HealthAlert("feature_drift", "critical", key, _decimal(metric.population_stability_index), _decimal(PSI_CRITICAL), f"{key} population drift exceeds the critical threshold."))
        elif metric.population_stability_index > PSI_WARNING:
            alerts.append(HealthAlert("feature_drift", "warning", key, _decimal(metric.population_stability_index), _decimal(PSI_WARNING), f"{key} population drift exceeds the warning threshold."))
    return alerts


def build_alerts(
    *, coverage_ratio: Decimal, metrics: tuple[FeatureHealth, ...], ranks: RankHealth,
    artifact_hash_matches: bool, registry_hash_matches: bool,
    explanation_lineage_matches: bool, readiness_available: bool,
) -> tuple[HealthAlert, ...]:
    alerts = _feature_alerts(metrics)
    if coverage_ratio < COVERAGE_CRITICAL:
        alerts.append(HealthAlert("coverage", "critical", "eligible_coverage", _decimal(coverage_ratio), _decimal(COVERAGE_CRITICAL), "Eligible score coverage is below the critical threshold."))
    elif coverage_ratio < COVERAGE_WARNING:
        alerts.append(HealthAlert("coverage", "warning", "eligible_coverage", _decimal(coverage_ratio), _decimal(COVERAGE_WARNING), "Eligible score coverage is below the warning threshold."))
    if ranks.top_20_churn_ratio is not None and ranks.top_20_churn_ratio > TOP_20_CHURN_WARNING:
        alerts.append(HealthAlert("rank_churn", "warning", "top_20_churn_ratio", _decimal(ranks.top_20_churn_ratio), _decimal(TOP_20_CHURN_WARNING), "More than half of the top 20 changed since the prior publication."))
    if ranks.mean_normalized_rank_change is not None and ranks.mean_normalized_rank_change > NORMALIZED_RANK_CHANGE_WARNING:
        alerts.append(HealthAlert("rank_churn", "warning", "mean_normalized_rank_change", _decimal(ranks.mean_normalized_rank_change), _decimal(NORMALIZED_RANK_CHANGE_WARNING), "Average normalized rank movement is above the warning threshold."))
    for matches, code, key, detail in (
        (artifact_hash_matches, "artifact_hash_mismatch", "artifact_sha256", "The deployed artifact bytes do not match the immutable registry hash."),
        (registry_hash_matches, "registry_hash_mismatch", "feature_registry_sha256", "The model, card, and active feature registry hashes do not agree."),
        (explanation_lineage_matches, "explanation_lineage_mismatch", "score_explanations", "Published explanation rows do not exactly match the active input contract."),
    ):
        if not matches:
            alerts.append(HealthAlert(code, "critical", key, "false", "true", detail))
    if not readiness_available:
        alerts.append(HealthAlert("forward_readiness_missing", "warning", "forward_outcome_readiness", "missing", "available", "No forward-outcome readiness snapshot was recorded for this publication."))
    return tuple(sorted(alerts, key=lambda item: (item.severity, item.code, item.metric_key)))


def _logical_hash(payload: dict[str, object]) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def materialize_model_health_snapshot(*, database_url: str, score_date: date) -> bool:
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT run.decision_at, run.score_snapshot_count, run.eligible_count,
                      snapshot.model_version, snapshot.protocol_version,
                      artifact.artifact_uri, artifact.artifact_sha256,
                      card.feature_registry_hash
               FROM quantrade.daily_research_runs run
               JOIN LATERAL (
                 SELECT model_version, protocol_version FROM quantrade.score_snapshots
                 WHERE score_date=run.score_date AND decision_at=run.decision_at
                 ORDER BY score_snapshot_id LIMIT 1
               ) snapshot ON TRUE
               JOIN quantrade.model_artifacts artifact USING(model_version)
               JOIN quantrade.model_cards card USING(model_version)
               WHERE run.score_date=%s AND run.status='completed'""",
            (score_date,),
        )
        run = cursor.fetchone()
        if run is None:
            raise DataQualityError(f"no completed score publication exists for {score_date}")
        decision_at, cohort_size, eligible_count, model_version, protocol_version, artifact_uri, expected_artifact_hash, card_registry_hash = run
        cohort_size, eligible_count = int(cohort_size), int(eligible_count)
        try:
            artifact_bytes = _path_from_file_uri(str(artifact_uri)).read_bytes()
            artifact_document = json.loads(artifact_bytes)
            artifact_hash_matches = sha256(artifact_bytes).hexdigest() == str(expected_artifact_hash)
            artifact_registry_hash = str(artifact_document.get("feature_registry_hash", ""))
        except (OSError, ValueError, json.JSONDecodeError, DataQualityError):
            artifact_hash_matches = False
            artifact_registry_hash = ""
        registry_hash_matches = (
            artifact_registry_hash == str(card_registry_hash) == baseline_feature_registry().registry_hash
        )

        cursor.execute(
            """SELECT input_ordinal, feature_key, feature_version, definition_hash
               FROM quantrade.model_input_contracts
               WHERE model_version=%s AND is_active ORDER BY input_ordinal""",
            (model_version,),
        )
        active_inputs = tuple((int(row[0]), str(row[1]), str(row[2]), str(row[3])) for row in cursor.fetchall())
        if not active_inputs:
            raise DataQualityError("deployed model has no active input contract")

        cursor.execute(
            """SELECT COUNT(*), COUNT(*) FILTER (WHERE contract.model_version IS NULL)
               FROM quantrade.score_explanations explanation
               JOIN quantrade.score_snapshots snapshot USING(score_snapshot_id)
               LEFT JOIN quantrade.model_input_contracts contract
                 ON contract.model_version=snapshot.model_version
                AND contract.feature_key=regexp_replace(explanation.feature_key, '_percentile$', '')
                AND contract.feature_version=explanation.feature_version
                AND contract.definition_hash=explanation.definition_hash
                AND contract.is_active
               WHERE snapshot.score_date=%s AND snapshot.decision_at=%s
                 AND snapshot.model_version=%s""",
            (score_date, decision_at, model_version),
        )
        explanation_count, orphan_count = (int(value) for value in cursor.fetchone())
        explanation_lineage_matches = explanation_count == cohort_size * len(active_inputs) and orphan_count == 0

        cursor.execute(
            """SELECT score_date FROM quantrade.daily_research_runs
               WHERE status='completed' AND score_date < %s
                 AND EXISTS (SELECT 1 FROM quantrade.score_snapshots s
                             WHERE s.score_date=daily_research_runs.score_date AND s.model_version=%s)
               ORDER BY score_date DESC LIMIT 1""",
            (score_date, model_version),
        )
        previous_row = cursor.fetchone()
        previous_date = previous_row[0] if previous_row else None

        def ranks_for(target: date | None) -> dict[str, int]:
            if target is None:
                return {}
            cursor.execute(
                """SELECT snapshot.security_id::text, snapshot.rank
                   FROM quantrade.score_snapshots snapshot
                   JOIN quantrade.daily_research_runs run
                     ON run.score_date=snapshot.score_date
                    AND run.decision_at=snapshot.decision_at
                    AND run.status='completed'
                   WHERE snapshot.score_date=%s AND snapshot.model_version=%s
                     AND snapshot.eligible AND snapshot.rank IS NOT NULL""",
                (target, model_version),
            )
            return {str(row[0]): int(row[1]) for row in cursor.fetchall()}

        ranks = rank_health(ranks_for(score_date), ranks_for(previous_date), previous_date)

        cursor.execute(
            """WITH reference_dates AS (
                 SELECT run.score_date FROM quantrade.daily_research_runs run
                 WHERE run.status='completed' AND run.score_date < %s
                   AND EXISTS (SELECT 1 FROM quantrade.score_snapshots snapshot
                               WHERE snapshot.score_date=run.score_date
                                 AND snapshot.decision_at=run.decision_at
                                 AND snapshot.model_version=%s)
                 ORDER BY run.score_date DESC LIMIT %s
               )
               SELECT regexp_replace(explanation.feature_key, '_percentile$', '') AS feature_key,
                      explanation.feature_version, explanation.definition_hash,
                      snapshot.score_date=%s AS is_current, explanation.percentile
               FROM quantrade.score_explanations explanation
               JOIN quantrade.score_snapshots snapshot USING(score_snapshot_id)
               JOIN quantrade.daily_research_runs run
                 ON run.score_date=snapshot.score_date
                AND run.decision_at=snapshot.decision_at
                AND run.status='completed'
               WHERE snapshot.model_version=%s
                 AND (snapshot.score_date=%s OR snapshot.score_date IN (SELECT score_date FROM reference_dates))""",
            (score_date, model_version, REFERENCE_DATES, score_date, model_version, score_date),
        )
        current_values: dict[tuple[str, str, str], list[Decimal]] = defaultdict(list)
        reference_values: dict[tuple[str, str, str], list[Decimal]] = defaultdict(list)
        for feature_key, version, definition_hash, is_current, percentile in cursor.fetchall():
            if percentile is not None:
                target = current_values if is_current else reference_values
                target[(str(feature_key), str(version), str(definition_hash))].append(Decimal(percentile))
        metrics = tuple(
            feature_health(
                feature_key=key, feature_version=version, definition_hash=definition_hash,
                cohort_size=cohort_size, current=tuple(current_values[(key, version, definition_hash)]),
                reference=tuple(reference_values[(key, version, definition_hash)]),
            )
            for _, key, version, definition_hash in active_inputs
        )

        cursor.execute(
            """SELECT unavailable_reason FROM quantrade.score_snapshots
               WHERE score_date=%s AND decision_at=%s AND model_version=%s AND NOT eligible""",
            (score_date, decision_at, model_version),
        )
        exclusions = Counter(_exclusion_code(row[0]) for row in cursor.fetchall())
        cursor.execute(
            """SELECT forward_outcome_readiness_snapshot_id
               FROM quantrade.forward_outcome_readiness_snapshots
               WHERE as_of_date = %s""",
            (score_date,),
        )
        readiness_row = cursor.fetchone()
        readiness_id = readiness_row[0] if readiness_row else None
        coverage = Decimal(eligible_count) / Decimal(cohort_size)
        alerts = build_alerts(
            coverage_ratio=coverage, metrics=metrics, ranks=ranks,
            artifact_hash_matches=artifact_hash_matches,
            registry_hash_matches=registry_hash_matches,
            explanation_lineage_matches=explanation_lineage_matches,
            readiness_available=readiness_id is not None,
        )
        status = "critical" if any(alert.severity == "critical" for alert in alerts) else "warning" if alerts else "healthy"
        payload = {
            "score_date": score_date.isoformat(), "decision_at": decision_at.isoformat(),
            "model_version": str(model_version), "protocol_version": str(protocol_version),
            "cohort_size": cohort_size, "eligible_count": eligible_count,
            "coverage_ratio": _decimal(coverage), "rank_health": asdict(ranks),
            "artifact_hash_matches": artifact_hash_matches,
            "registry_hash_matches": registry_hash_matches,
            "explanation_lineage_matches": explanation_lineage_matches,
            "forward_readiness_snapshot_id": str(readiness_id) if readiness_id else None,
            "features": [asdict(metric) for metric in metrics],
            "exclusions": dict(sorted(exclusions.items())),
            "alerts": [asdict(alert) for alert in alerts], "health_status": status,
        }
        logical_hash = _logical_hash(payload)
        cursor.execute(
            "SELECT logical_sha256 FROM quantrade.model_health_snapshots WHERE score_date=%s",
            (score_date,),
        )
        existing = cursor.fetchone()
        if existing:
            if str(existing[0]) != logical_hash:
                raise DataQualityError(
                    "stored model-health snapshot conflicts with current immutable evidence: "
                    f"stored={existing[0]}; recomputed={logical_hash}"
                )
            return False
        cursor.execute(
            """INSERT INTO quantrade.model_health_snapshots
                   (score_date, decision_at, model_version, protocol_version, cohort_size,
                    eligible_count, excluded_count, coverage_ratio, previous_score_date,
                    top_20_churn_ratio, mean_normalized_rank_change,
                    forward_outcome_readiness_snapshot_id, artifact_hash_matches,
                    registry_hash_matches, explanation_lineage_matches, health_status, logical_sha256)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING model_health_snapshot_id""",
            (
                score_date, decision_at, model_version, protocol_version, cohort_size,
                eligible_count, cohort_size - eligible_count, coverage, ranks.previous_score_date,
                ranks.top_20_churn_ratio, ranks.mean_normalized_rank_change, readiness_id,
                artifact_hash_matches, registry_hash_matches, explanation_lineage_matches,
                status, logical_hash,
            ),
        )
        snapshot_id = cursor.fetchone()[0]
        cursor.executemany(
            """INSERT INTO quantrade.model_health_feature_metrics
                   (model_health_snapshot_id, feature_key, feature_version, definition_hash,
                    available_count, unavailable_count, missing_ratio, mean_percentile,
                    reference_mean_percentile, population_stability_index,
                    reference_observation_count, status)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [
                (snapshot_id, item.feature_key, item.feature_version, item.definition_hash,
                 item.available_count, item.unavailable_count, item.missing_ratio,
                 item.mean_percentile, item.reference_mean_percentile,
                 item.population_stability_index, item.reference_observation_count, item.status)
                for item in metrics
            ],
        )
        cursor.executemany(
            "INSERT INTO quantrade.model_health_exclusion_metrics (model_health_snapshot_id, reason_code, excluded_count) VALUES (%s,%s,%s)",
            [(snapshot_id, code, count) for code, count in sorted(exclusions.items())],
        )
        cursor.executemany(
            """INSERT INTO quantrade.model_health_alerts
                   (model_health_snapshot_id, alert_code, severity, metric_key,
                    observed_value, threshold_value, detail)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            [(snapshot_id, item.code, item.severity, item.metric_key, item.observed_value, item.threshold_value, item.detail) for item in alerts],
        )
        connection.commit()
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize an immutable deployed-model health snapshot")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--score-date", type=date.fromisoformat)
    arguments = parser.parse_args()
    database_url = _dotenv_values(arguments.env_file).get("DATABASE_URL")
    if not database_url:
        raise DataQualityError("DATABASE_URL is required")
    target = arguments.score_date
    if target is None:
        import psycopg
        with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT MAX(score_date) FROM quantrade.daily_research_runs WHERE status='completed'")
            target = cursor.fetchone()[0]
    if target is None:
        raise DataQualityError("no completed score publication exists")
    created = materialize_model_health_snapshot(database_url=database_url, score_date=target)
    print(f"score_date={target}; model_health_snapshot={'created' if created else 'already_verified'}")


if __name__ == "__main__":
    main()
