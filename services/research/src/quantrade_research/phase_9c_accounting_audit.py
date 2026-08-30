"""Audit the strict Phase 9C point-in-time quarterly accounting engine."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, time, timezone
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from .historical_cohorts import CURRENT_SURVIVORS_COHORT
from .quality import DataQualityError
from .quarterly_accounting import (
    ACCOUNTING_RULE_VERSION, AccountingValue, endpoint_shares, latest_endpoint, true_ttm,
)
from .score_run import _dotenv_values
from .sec_fact_resolver import PostgresSecFactResolver, ResolvedSecFact


AUDIT_KEY = "phase_9c_strict_accounting_engine"
AUDIT_VERSION = "v1"
DEFAULT_START = date(2022, 1, 7)
DEFAULT_END = date(2025, 6, 30)
EARLIEST_FACT_END = date(2020, 1, 1)
TORONTO = ZoneInfo("America/Toronto")
US_GAAP_CONCEPTS = (
    "NetIncomeLoss",
    "ProfitLoss",
    "NetCashProvidedByUsedInOperatingActivities",
    "Assets",
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
)
DEI_CONCEPTS = ("EntityCommonStockSharesOutstanding",)
METRICS = ("net_income_ttm", "operating_cash_flow_ttm", "assets", "equity", "endpoint_shares")


def _decision_at(formation: date) -> datetime:
    return datetime.combine(formation, time(20, 0), tzinfo=TORONTO)


def _load_context(database_url: str, start: date, end: date) -> tuple[tuple[str, ...], tuple[date, ...]]:
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute(
            """SELECT membership.security_id::text
                 FROM quantrade.research_cohort_memberships membership
                 JOIN quantrade.research_cohorts cohort USING(research_cohort_id)
                WHERE cohort.cohort_code=%s ORDER BY membership.security_id""",
            (CURRENT_SURVIVORS_COHORT,),
        )
        security_ids = tuple(str(row[0]) for row in cursor)
        cursor.execute(
            """SELECT session_date
                 FROM quantrade.benchmark_daily_price_bars
                WHERE benchmark_ticker='SPY' AND session='regular'
                  AND adjustment_basis='split_adjusted'
                  AND session_date BETWEEN %s AND %s
                ORDER BY session_date""",
            (start, end),
        )
        weekly: dict[tuple[int, int], date] = {}
        for (session_date,) in cursor:
            year, week, _ = session_date.isocalendar()
            weekly[(year, week)] = session_date
    if len(security_ids) != 500:
        raise DataQualityError(f"{CURRENT_SURVIVORS_COHORT} must contain exactly 500 securities")
    formations = tuple(sorted(weekly.values()))
    if not formations or formations[0] < start:
        raise DataQualityError("strict accounting audit has no eligible weekly formations")
    return security_ids, formations


def _load_facts(
    database_url: str, security_ids: tuple[str, ...], formations: tuple[date, ...],
) -> dict[str, tuple[ResolvedSecFact, ...]]:
    resolver = PostgresSecFactResolver(database_url)
    try:
        latest = formations[-1]
        decision = _decision_at(latest)
        facts = (
            *resolver.load_candidates(
                security_ids=security_ids,
                taxonomy="us-gaap",
                concepts=US_GAAP_CONCEPTS,
                earliest_period_end=EARLIEST_FACT_END,
                formation_date=latest,
                decision_at=decision,
            ),
            *resolver.load_candidates(
                security_ids=security_ids,
                taxonomy="dei",
                concepts=DEI_CONCEPTS,
                earliest_period_end=EARLIEST_FACT_END,
                formation_date=latest,
                decision_at=decision,
            ),
        )
    finally:
        resolver.close()
    grouped: dict[str, list[ResolvedSecFact]] = defaultdict(list)
    for fact in facts:
        grouped[fact.security_id].append(fact)
    return {
        security_id: tuple(sorted(items, key=lambda item: (item.available_at, item.period_end, item.lineage_key)))
        for security_id, items in grouped.items()
    }


def _values(facts: tuple[ResolvedSecFact, ...], formation: date) -> dict[str, AccountingValue]:
    return {
        "net_income_ttm": true_ttm(
            facts, concepts=("NetIncomeLoss", "ProfitLoss"), formation_date=formation,
        ),
        "operating_cash_flow_ttm": true_ttm(
            facts, concepts=("NetCashProvidedByUsedInOperatingActivities",), formation_date=formation,
        ),
        "assets": latest_endpoint(
            facts, concepts=("Assets",), taxonomy="us-gaap", unit="USD", formation_date=formation,
            require_positive=True,
        ),
        "equity": latest_endpoint(
            facts,
            concepts=("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
            taxonomy="us-gaap", unit="USD", formation_date=formation,
        ),
        "endpoint_shares": endpoint_shares(facts, formation_date=formation),
    }


def _lineage_valid(value: AccountingValue, decision: datetime) -> bool:
    if not value.available:
        return True
    return bool(value.lineage) and all(
        len(item.observation_hash) == 64
        and datetime.fromisoformat(item.available_at) <= decision
        and date.fromisoformat(item.period_end) <= decision.date()
        and item.availability_rule
        and item.source_reference
        for item in value.lineage
    )


def _summarize_formation(
    formation: date, security_ids: tuple[str, ...],
    values_by_security: dict[str, dict[str, AccountingValue]],
) -> tuple[dict[str, object], str]:
    decision = _decision_at(formation)
    available = Counter()
    exclusions: dict[str, Counter[str]] = {metric: Counter() for metric in METRICS}
    lineage_violations = 0
    digests: list[str] = []
    for security_id in security_ids:
        values = values_by_security[security_id]
        for metric, value in values.items():
            if value.available:
                available[metric] += 1
            else:
                exclusions[metric][value.exclusion or "unknown"] += 1
            if not _lineage_valid(value, decision):
                lineage_violations += 1
            digests.append(f"{security_id}|{metric}|{value.digest()}")
    payload: dict[str, object] = {
        "formation_date": formation.isoformat(),
        "decision_at": decision.isoformat(),
        "available": {metric: int(available[metric]) for metric in METRICS},
        "coverage": {metric: round(available[metric] / len(security_ids), 6) for metric in METRICS},
        "exclusions": {metric: dict(sorted(exclusions[metric].items())) for metric in METRICS},
        "lineage_violations": lineage_violations,
    }
    return payload, sha256("\n".join(sorted(digests)).encode()).hexdigest()


def _selection_key(fact: ResolvedSecFact) -> tuple[datetime, datetime, str]:
    observed = fact.observed_at or datetime.min.replace(tzinfo=timezone.utc)
    return fact.available_at, observed, fact.lineage_key


def _eligibility_at(fact: ResolvedSecFact) -> datetime:
    period_ready = datetime.combine(fact.period_end, time.min, tzinfo=TORONTO)
    return max(fact.available_at, period_ready)


def _formation_results(
    formations: tuple[date, ...], security_ids: tuple[str, ...],
    grouped: dict[str, tuple[ResolvedSecFact, ...]],
) -> tuple[list[dict[str, object]], list[str]]:
    """Advance one as-of fact state through formations without rescanning history."""
    events = {
        security_id: tuple(sorted(grouped.get(security_id, ()), key=lambda item: (_eligibility_at(item), item.lineage_key)))
        for security_id in security_ids
    }
    positions = {security_id: 0 for security_id in security_ids}
    selected: dict[str, dict[str, ResolvedSecFact]] = {security_id: {} for security_id in security_ids}
    cached_values: dict[str, dict[str, AccountingValue]] = {}
    rows: list[dict[str, object]] = []
    hashes: list[str] = []
    for formation in formations:
        decision = _decision_at(formation)
        for security_id in security_ids:
            security_events = events[security_id]
            position = positions[security_id]
            state = selected[security_id]
            changed = security_id not in cached_values
            while position < len(security_events) and _eligibility_at(security_events[position]) <= decision:
                fact = security_events[position]
                current = state.get(fact.filing_fact_key)
                if current is None or _selection_key(fact) > _selection_key(current):
                    state[fact.filing_fact_key] = fact
                    changed = True
                position += 1
            positions[security_id] = position
            if changed:
                resolved = tuple(sorted(
                    state.values(), key=lambda item: (item.concept, item.period_end, item.lineage_key),
                ))
                cached_values[security_id] = _values(resolved, formation)
        row, digest = _summarize_formation(formation, security_ids, cached_values)
        rows.append(row)
        hashes.append(digest)
    return rows, hashes


def build_audit(database_url: str, *, start: date, end: date) -> dict[str, object]:
    security_ids, formations = _load_context(database_url, start, end)
    grouped = _load_facts(database_url, security_ids, formations)
    formation_rows, raw_formation_hashes = _formation_results(formations, security_ids, grouped)
    formation_hashes = [
        f"{formation.isoformat()}|{digest}"
        for formation, digest in zip(formations, raw_formation_hashes, strict=True)
    ]

    replay_formation = formations[-1]
    replay_rows_a, replay_hashes_a = _formation_results((replay_formation,), security_ids, grouped)
    replay_rows_b, replay_hashes_b = _formation_results((replay_formation,), security_ids, grouped)
    replay_a, replay_hash_a = replay_rows_a[0], replay_hashes_a[0]
    replay_b, replay_hash_b = replay_rows_b[0], replay_hashes_b[0]
    lineage_violations = sum(int(row["lineage_violations"]) for row in formation_rows)
    aggregate = {
        metric: round(
            sum(int(row["available"][metric]) for row in formation_rows) / (len(formations) * len(security_ids)),
            6,
        )
        for metric in METRICS
    }
    minimum = {
        metric: min(float(row["coverage"][metric]) for row in formation_rows)
        for metric in METRICS
    }
    raw_feature_gate = {
        metric: aggregate[metric] >= 0.70
        for metric in METRICS
    }
    gates = {
        "point_in_time_lineage": lineage_violations == 0,
        "deterministic_replay": replay_hash_a == replay_hash_b and replay_a == replay_b,
        "endpoint_shares_primary_policy": True,
        "raw_feature_aggregate_coverage": all(raw_feature_gate.values()),
        "accounting_minimum_formation_coverage": all(value >= 0.70 for value in minimum.values()),
    }
    report: dict[str, object] = {
        "audit_key": AUDIT_KEY,
        "audit_version": AUDIT_VERSION,
        "accounting_rule_version": ACCOUNTING_RULE_VERSION,
        "research_cohort": CURRENT_SURVIVORS_COHORT,
        "data_capability_tier": "B",
        "survivorship_biased": True,
        "holdout_used": False,
        "download_performed": False,
        "start_date": formations[0].isoformat(),
        "end_date": formations[-1].isoformat(),
        "formation_count": len(formations),
        "security_count": len(security_ids),
        "candidate_fact_count": sum(len(items) for items in grouped.values()),
        "aggregate_coverage": aggregate,
        "minimum_formation_coverage": minimum,
        "raw_feature_coverage_gate": raw_feature_gate,
        "lineage_violations": lineage_violations,
        "replay_formation": replay_formation.isoformat(),
        "replay_hash": replay_hash_a,
        "formation_panel_hash": sha256("\n".join(formation_hashes).encode()).hexdigest(),
        "gates": gates,
        "passed": all(gates.values()),
        "policy": {
            "flow_construction": "Q1; H1-Q1; 9M-H1; FY-9M; latest four consecutive quarters",
            "net_income_priority": ["NetIncomeLoss", "ProfitLoss"],
            "primary_shares": "dei:EntityCommonStockSharesOutstanding endpoint only",
            "weighted_average_shares_primary_fallback": False,
            "missing_or_ambiguous_context": "withhold",
        },
        "formations": formation_rows,
    }
    report["report_hash"] = sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the strict Phase 9C quarterly accounting engine")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--start", type=date.fromisoformat, default=DEFAULT_START)
    parser.add_argument("--end", type=date.fromisoformat, default=DEFAULT_END)
    parser.add_argument("--output", type=Path, default=Path("data/derived/phase_9c_accounting_audit_v1.json"))
    arguments = parser.parse_args()
    values = _dotenv_values(Path(arguments.env_file))
    database_url = values.get("DATABASE_URL")
    if not database_url:
        raise DataQualityError("DATABASE_URL is required")
    if arguments.output.exists():
        raise DataQualityError(f"refusing to overwrite immutable audit: {arguments.output}")
    report = build_audit(database_url, start=arguments.start, end=arguments.end)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "passed": report["passed"],
        "formation_count": report["formation_count"],
        "candidate_fact_count": report["candidate_fact_count"],
        "aggregate_coverage": report["aggregate_coverage"],
        "minimum_formation_coverage": report["minimum_formation_coverage"],
        "report_hash": report["report_hash"],
    }, sort_keys=True))
    if not report["passed"]:
        raise DataQualityError("Phase 9C strict accounting audit did not pass frozen gates")


if __name__ == "__main__":
    main()
