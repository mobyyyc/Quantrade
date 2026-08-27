"""Pre-holdout diagnostics for the isolated Phase 9 free-data features."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
from statistics import median
from typing import Iterable

from .candidate_features import (
    calculate_amihud_illiquidity_20d,
    calculate_downside_volatility_60d,
    calculate_return_on_assets_change_yoy,
    calculate_short_term_reversal_20d,
)
from .feature_diagnostics import FeatureOutcome
from .features import (
    NEXT_GENERATION_CANDIDATE_SET_VERSION,
    FeatureRegistry,
    baseline_feature_registry,
    next_generation_candidate_registry,
)
from .fundamentals import FundamentalFactObservation
from .historical_cohorts import CURRENT_SURVIVORS_COHORT
from .historical_replay import historical_decision_at
from .momentum import FeaturePriceObservation
from .quality import DataQualityError
from .ranking import SectorClassification, build_sector_aware_percentile_ranks
from .score_run import _dotenv_values


DIAGNOSTIC_PROTOCOL_VERSION = "next_gen_feature_diagnostics_v1"
DIAGNOSTIC_START = date(2022, 1, 1)
DIAGNOSTIC_END = date(2025, 6, 30)
MINIMUM_AGGREGATE_COVERAGE = Decimal("0.90")
MINIMUM_MONTHLY_COVERAGE = Decimal("0.80")
MAXIMUM_REDUNDANCY_CORRELATION = Decimal("0.90")
MINIMUM_RANK_STABILITY = Decimal("0.10")
MAXIMUM_MEDIAN_TOP_20_TURNOVER = Decimal("0.90")


@dataclass(frozen=True, slots=True)
class CandidateDiagnostic:
    feature_key: str
    feature_version: str
    available_observations: int
    expected_observations: int
    aggregate_coverage: Decimal
    minimum_monthly_coverage: Decimal
    most_correlated_active_feature: str | None
    median_absolute_active_correlation: Decimal | None
    median_consecutive_rank_correlation: Decimal | None
    median_top_20_turnover: Decimal | None
    point_in_time_violations: int
    missingness: tuple[tuple[str, int], ...]
    accepted: bool
    rejection_reasons: tuple[str, ...]


def _correlation(pairs: list[tuple[Decimal, Decimal]]) -> Decimal | None:
    if len(pairs) < 2:
        return None
    left_mean = sum((pair[0] for pair in pairs), Decimal("0")) / Decimal(len(pairs))
    right_mean = sum((pair[1] for pair in pairs), Decimal("0")) / Decimal(len(pairs))
    left = [pair[0] - left_mean for pair in pairs]
    right = [pair[1] - right_mean for pair in pairs]
    left_ss = sum((value * value for value in left), Decimal("0"))
    right_ss = sum((value * value for value in right), Decimal("0"))
    if left_ss == 0 or right_ss == 0:
        return None
    covariance = sum((x * y for x, y in zip(left, right)), Decimal("0"))
    return covariance / (left_ss * right_ss).sqrt()


def _median(values: Iterable[Decimal]) -> Decimal | None:
    materialized = list(values)
    return Decimal(str(median(materialized))) if materialized else None


def _top_ids(values: dict[str, Decimal], count: int = 20) -> set[str]:
    return {
        security_id
        for security_id, _ in sorted(values.items(), key=lambda item: (-item[1], item[0]))[:count]
    }


def evaluate_candidate_diagnostics(
    *,
    formation_dates: tuple[date, ...],
    universe_security_ids: tuple[str, ...],
    candidate_ranks: dict[date, dict[str, dict[str, Decimal]]],
    baseline_ranks: dict[date, dict[str, dict[str, Decimal]]],
    missingness: dict[str, Counter[str]],
    point_in_time_violations: dict[str, int],
    registry: FeatureRegistry | None = None,
) -> tuple[CandidateDiagnostic, ...]:
    """Apply the frozen P9.3 data-quality gates without using target returns."""
    active_registry = registry or next_generation_candidate_registry()
    if len(formation_dates) < 2 or not universe_security_ids:
        raise DataQualityError("candidate diagnostics require at least two dates and a non-empty universe")
    expected = len(formation_dates) * len(universe_security_ids)
    reports: list[CandidateDiagnostic] = []
    for definition in active_registry.definitions():
        monthly = [candidate_ranks.get(day, {}).get(definition.key, {}) for day in formation_dates]
        available = sum(len(values) for values in monthly)
        aggregate_coverage = Decimal(available) / Decimal(expected)
        monthly_coverages = [Decimal(len(values)) / Decimal(len(universe_security_ids)) for values in monthly]

        active_correlations: dict[str, list[Decimal]] = defaultdict(list)
        for day in formation_dates:
            candidate = candidate_ranks.get(day, {}).get(definition.key, {})
            for active_key, active_values in baseline_ranks.get(day, {}).items():
                paired = [
                    (candidate[security], active_values[security])
                    for security in sorted(candidate.keys() & active_values.keys())
                ]
                correlation = _correlation(paired)
                if correlation is not None:
                    active_correlations[active_key].append(abs(correlation))
        correlation_medians = {
            key: value
            for key, correlations in active_correlations.items()
            if (value := _median(correlations)) is not None
        }
        most_correlated = max(correlation_medians, key=correlation_medians.get) if correlation_medians else None
        redundancy = correlation_medians.get(most_correlated) if most_correlated else None

        stability_values: list[Decimal] = []
        turnover_values: list[Decimal] = []
        for prior, current in zip(monthly, monthly[1:]):
            shared = prior.keys() & current.keys()
            correlation = _correlation(
                [(prior[security], current[security]) for security in sorted(shared)]
            )
            if correlation is not None:
                stability_values.append(correlation)
            prior_top, current_top = _top_ids(prior), _top_ids(current)
            selected = max(len(prior_top), len(current_top))
            if selected:
                turnover_values.append(Decimal("1") - Decimal(len(prior_top & current_top)) / Decimal(selected))

        stability = _median(stability_values)
        turnover = _median(turnover_values)
        violations = point_in_time_violations.get(definition.key, 0)
        reasons: list[str] = []
        if aggregate_coverage < MINIMUM_AGGREGATE_COVERAGE:
            reasons.append("aggregate_coverage_below_90_percent")
        if min(monthly_coverages) < MINIMUM_MONTHLY_COVERAGE:
            reasons.append("monthly_coverage_below_80_percent")
        if redundancy is None:
            reasons.append("active_feature_redundancy_unavailable")
        elif redundancy > MAXIMUM_REDUNDANCY_CORRELATION:
            reasons.append("redundant_with_active_feature")
        if stability is None:
            reasons.append("rank_stability_unavailable")
        elif stability < MINIMUM_RANK_STABILITY:
            reasons.append("rank_stability_below_0_10")
        if turnover is None:
            reasons.append("top_20_turnover_unavailable")
        elif turnover > MAXIMUM_MEDIAN_TOP_20_TURNOVER:
            reasons.append("median_top_20_turnover_above_0_90")
        if violations:
            reasons.append("point_in_time_violation")
        reports.append(CandidateDiagnostic(
            definition.key,
            definition.version,
            available,
            expected,
            aggregate_coverage,
            min(monthly_coverages),
            most_correlated,
            redundancy,
            stability,
            turnover,
            violations,
            tuple(sorted(missingness.get(definition.key, Counter()).items())),
            not reasons,
            tuple(reasons),
        ))
    return tuple(reports)


def _reason(error: Exception) -> str:
    message = str(error)
    if "completed split-adjusted sessions" in message or "requires 21 completed" in message:
        return "insufficient_price_history"
    if "has no split-adjusted close for formation date" in message:
        return "missing_split_adjusted_formation_bar"
    if "has no unadjusted close for formation date" in message:
        return "missing_unadjusted_formation_bar"
    if "matching adjusted and unadjusted" in message:
        return "mismatched_price_sessions"
    if "duplicate" in message and "price observation" in message:
        return "duplicate_price_observation"
    if "non-positive split-adjusted close" in message or "negative unadjusted close" in message:
        return "invalid_price"
    if "positive dollar volume" in message:
        return "nonpositive_dollar_volume"
    if "two eligible annual periods" in message:
        return "insufficient_annual_history"
    if "consecutive annual periods" in message:
        return "nonconsecutive_annual_periods"
    if "missing assets" in message:
        return "missing_asset_endpoint"
    if "unavailable" in message or "decision_at" in message:
        return "point_in_time_violation"
    return "other_data_quality"


def _outcome(definition, security_id: str, formation_date: date, calculator) -> FeatureOutcome:
    try:
        calculated = calculator()
    except (DataQualityError, ArithmeticError, ValueError) as error:
        return FeatureOutcome(
            security_id,
            formation_date,
            definition.key,
            definition.version,
            definition.definition_hash,
            None,
            _reason(error),
        )
    return FeatureOutcome(
        security_id,
        formation_date,
        definition.key,
        definition.version,
        definition.definition_hash,
        calculated.value,
    )


def _load_inputs(database_url: str):
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT membership.security_id::text
               FROM quantrade.research_cohort_memberships membership
               JOIN quantrade.research_cohorts cohort USING (research_cohort_id)
               WHERE cohort.cohort_code = %s ORDER BY membership.security_id""",
            (CURRENT_SURVIVORS_COHORT,),
        )
        security_ids = tuple(row[0] for row in cursor.fetchall())
        if len(security_ids) != 500:
            raise DataQualityError(f"{CURRENT_SURVIVORS_COHORT} must contain 500 securities")
        cursor.execute(
            """SELECT MAX(score_date)
               FROM quantrade.daily_research_runs
               WHERE status = 'completed' AND score_date BETWEEN %s AND %s
               GROUP BY date_trunc('month', score_date)
               ORDER BY MAX(score_date)""",
            (DIAGNOSTIC_START, DIAGNOSTIC_END),
        )
        formation_dates = tuple(row[0] for row in cursor.fetchall())
        if len(formation_dates) < 12:
            raise DataQualityError("candidate diagnostics require at least twelve development month-ends")
        cursor.execute(
            """SELECT security_id::text, session_date, close_price, adjustment_basis, available_at, volume
               FROM quantrade.daily_price_bars
               WHERE security_id = ANY(%s::uuid[]) AND session = 'regular'
                 AND session_date <= %s AND adjustment_basis IN ('split_adjusted', 'unadjusted')
               ORDER BY security_id, session_date, adjustment_basis""",
            (list(security_ids), formation_dates[-1]),
        )
        prices: dict[str, list[FeaturePriceObservation]] = defaultdict(list)
        for row in cursor:
            prices[row[0]].append(FeaturePriceObservation(*row))
        cursor.execute(
            """SELECT security_id::text, filing_id::text, taxonomy, concept, unit, fact_value,
                      period_start, period_end, available_at
               FROM quantrade.filing_facts
               WHERE security_id = ANY(%s::uuid[]) AND period_end <= %s
                 AND taxonomy = 'us-gaap' AND unit = 'USD'
                 AND concept IN ('NetIncomeLoss', 'ProfitLoss', 'Assets')
               ORDER BY security_id, period_end, available_at""",
            (list(security_ids), formation_dates[-1]),
        )
        facts: dict[str, list[FundamentalFactObservation]] = defaultdict(list)
        for row in cursor:
            facts[row[0]].append(FundamentalFactObservation(*row))
        cursor.execute(
            """SELECT DISTINCT ON (security_id) security_id::text, sector_code, as_of_date, available_at
               FROM quantrade.sector_classifications
               WHERE security_id = ANY(%s::uuid[])
               ORDER BY security_id, as_of_date DESC, available_at DESC""",
            (list(security_ids),),
        )
        sectors = tuple(SectorClassification(*row) for row in cursor.fetchall())
        cursor.execute(
            """SELECT snapshot.score_date, explanation.feature_key, snapshot.security_id::text,
                      explanation.percentile
               FROM quantrade.score_snapshots snapshot
               JOIN quantrade.daily_research_runs run
                 ON run.score_date = snapshot.score_date AND run.decision_at = snapshot.decision_at
                AND run.status = 'completed'
               JOIN quantrade.score_explanations explanation
                 ON explanation.score_snapshot_id = snapshot.score_snapshot_id
               WHERE snapshot.score_date = ANY(%s::date[]) AND explanation.percentile IS NOT NULL
               ORDER BY snapshot.score_date, explanation.feature_key, snapshot.security_id""",
            (list(formation_dates),),
        )
        baseline: dict[date, dict[str, dict[str, Decimal]]] = defaultdict(lambda: defaultdict(dict))
        for score_date, feature_key, security_id, percentile in cursor:
            baseline[score_date][feature_key][security_id] = Decimal(percentile)
    return security_ids, formation_dates, prices, facts, sectors, baseline


def run_candidate_diagnostics(database_url: str) -> dict[str, object]:
    registry = next_generation_candidate_registry()
    security_ids, formation_dates, prices, facts, sectors, baseline = _load_inputs(database_url)
    candidate_ranks: dict[date, dict[str, dict[str, Decimal]]] = defaultdict(lambda: defaultdict(dict))
    missingness: dict[str, Counter[str]] = defaultdict(Counter)
    violations: dict[str, int] = defaultdict(int)
    definitions = {definition.key: definition for definition in registry.definitions()}
    for index, formation_date in enumerate(formation_dates, start=1):
        decision_at = historical_decision_at(formation_date)
        outcomes: list[FeatureOutcome] = []
        for security_id in security_ids:
            eligible_prices = [item for item in prices[security_id] if item.session_date <= formation_date and item.available_at <= decision_at]
            eligible_facts = [item for item in facts[security_id] if item.period_end <= formation_date and item.available_at <= decision_at]
            calculations = {
                "short_term_reversal_20d": lambda p=eligible_prices, s=security_id: calculate_short_term_reversal_20d(p, security_id=s, formation_date=formation_date, decision_at=decision_at, registry=registry),
                "downside_volatility_60d": lambda p=eligible_prices, s=security_id: calculate_downside_volatility_60d(p, security_id=s, formation_date=formation_date, decision_at=decision_at, registry=registry),
                "amihud_illiquidity_20d": lambda p=eligible_prices, s=security_id: calculate_amihud_illiquidity_20d(p, security_id=s, formation_date=formation_date, decision_at=decision_at, registry=registry),
                "return_on_assets_change_yoy": lambda f=eligible_facts, s=security_id: calculate_return_on_assets_change_yoy(f, security_id=s, formation_date=formation_date, decision_at=decision_at, registry=registry),
            }
            for feature_key, calculator in calculations.items():
                outcome = _outcome(definitions[feature_key], security_id, formation_date, calculator)
                outcomes.append(outcome)
                if outcome.unavailable_reason:
                    missingness[feature_key][outcome.unavailable_reason] += 1
                    if outcome.unavailable_reason == "point_in_time_violation":
                        violations[feature_key] += 1
        ranks = build_sector_aware_percentile_ranks(
            outcomes,
            sectors,
            formation_date=formation_date,
            decision_at=decision_at,
            universe_security_ids=security_ids,
            registry=registry,
            allow_static_tier_b_grouping=True,
        )
        for rank in ranks:
            if rank.percentile is not None:
                candidate_ranks[formation_date][rank.feature_key][rank.security_id] = rank.percentile
        print(f"diagnostic_progress={index}/{len(formation_dates)}; formation_date={formation_date}", flush=True)
    reports = evaluate_candidate_diagnostics(
        formation_dates=formation_dates,
        universe_security_ids=security_ids,
        candidate_ranks=candidate_ranks,
        baseline_ranks=baseline,
        missingness=missingness,
        point_in_time_violations=violations,
        registry=registry,
    )
    payload: dict[str, object] = {
        "protocol_version": DIAGNOSTIC_PROTOCOL_VERSION,
        "candidate_set_version": NEXT_GENERATION_CANDIDATE_SET_VERSION,
        "candidate_registry_hash": registry.registry_hash,
        "active_registry_hash": baseline_feature_registry().registry_hash,
        "cohort_code": CURRENT_SURVIVORS_COHORT,
        "data_capability_tier": "B",
        "survivorship_biased": True,
        "static_sector_grouping": True,
        "development_only": True,
        "holdout_used": False,
        "start_date": formation_dates[0].isoformat(),
        "end_date": formation_dates[-1].isoformat(),
        "formation_count": len(formation_dates),
        "security_count": len(security_ids),
        "thresholds": {
            "minimum_aggregate_coverage": str(MINIMUM_AGGREGATE_COVERAGE),
            "minimum_monthly_coverage": str(MINIMUM_MONTHLY_COVERAGE),
            "maximum_redundancy_correlation": str(MAXIMUM_REDUNDANCY_CORRELATION),
            "minimum_rank_stability": str(MINIMUM_RANK_STABILITY),
            "maximum_median_top_20_turnover": str(MAXIMUM_MEDIAN_TOP_20_TURNOVER),
        },
        "features": [
            {
                **asdict(report),
                "aggregate_coverage": str(report.aggregate_coverage),
                "minimum_monthly_coverage": str(report.minimum_monthly_coverage),
                "median_absolute_active_correlation": str(report.median_absolute_active_correlation) if report.median_absolute_active_correlation is not None else None,
                "median_consecutive_rank_correlation": str(report.median_consecutive_rank_correlation) if report.median_consecutive_rank_correlation is not None else None,
                "median_top_20_turnover": str(report.median_top_20_turnover) if report.median_top_20_turnover is not None else None,
                "missingness": dict(report.missingness),
                "rejection_reasons": list(report.rejection_reasons),
            }
            for report in reports
        ],
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload["result_sha256"] = sha256(canonical).hexdigest()
    return payload


def _settings(env_file: Path):
    from .config import Settings

    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run immutable pre-holdout diagnostics for Phase 9 candidate features")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    if arguments.output.exists():
        raise DataQualityError(f"refusing to overwrite immutable candidate diagnostic: {arguments.output}")
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    report = run_candidate_diagnostics(settings.database_url)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    accepted = sum(bool(feature["accepted"]) for feature in report["features"])
    print(f"candidate_features={len(report['features'])}; accepted={accepted}; rejected={len(report['features']) - accepted}; result_sha256={report['result_sha256']}")


if __name__ == "__main__":
    main()
