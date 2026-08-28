"""Read-only Phase 9C data-feasibility audit.

This module measures the existing store. It does not download, mutate, build a
training dataset, or inspect candidate outcomes.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import json
import os
from pathlib import Path
from typing import Iterable

from .historical_cohorts import CURRENT_SURVIVORS_COHORT
from .quality import DataQualityError
from .score_run import _dotenv_values


AUDIT_KEY = "phase_9c_data_feasibility"
AUDIT_VERSION = "v1"
DEFAULT_START = date(2021, 1, 1)
DEFAULT_END = date(2025, 6, 30)
COMPLEX_ACTIONS = {
    "cash_merger", "stock_merger", "stock_and_cash_merger", "spin_off",
    "stock_dividend", "rights_distribution", "redemption", "reorganization",
    "worthless_removal", "partial_call",
}
FLOW_CONCEPTS = (
    "NetIncomeLoss", "ProfitLoss", "NetCashProvidedByUsedInOperatingActivities",
    "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "GrossProfit",
)
BALANCE_CONCEPTS = ("Assets", "StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")
SHARE_CONCEPTS = ("EntityCommonStockSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic")


def _capability(status: str, *, evidence: dict[str, object], reasons: Iterable[str]) -> dict[str, object]:
    if status not in {"pass", "restricted", "deferred", "blocked"}:
        raise ValueError(f"invalid capability status: {status}")
    return {"status": status, "evidence": evidence, "reasons": list(reasons)}


def classify_capabilities(raw: dict[str, object]) -> dict[str, dict[str, object]]:
    """Convert measured evidence into conservative pre-result capability decisions."""
    cohort_size = int(raw["cohort_size"])
    market = raw["market"]
    actions = raw["corporate_actions"]
    sec = raw["sec"]
    shares = raw["shares"]
    sic = raw["historical_sic"]
    weekly = raw["weekly_market_features"]

    split_security_count = int(market["equity_basis"].get("split_adjusted", {}).get("security_count", 0))
    raw_security_count = int(market["equity_basis"].get("unadjusted", {}).get("security_count", 0))
    spy_split_rows = int(market["benchmark_basis"].get("split_adjusted", {}).get("row_count", 0))
    total_security_count = int(market["equity_basis"].get("total_return_adjusted", {}).get("security_count", 0))
    total_start = market["equity_basis"].get("total_return_adjusted", {}).get("start_date")
    ordinary_actions = int(actions.get("cash_dividend", 0)) + int(actions.get("forward_split", 0)) + int(actions.get("reverse_split", 0))
    complex_actions = sum(int(actions.get(key, 0)) for key in COMPLEX_ACTIONS)
    market_restricted_reasons: list[str] = []
    if split_security_count < cohort_size or raw_security_count < cohort_size or spy_split_rows == 0:
        market_restricted_reasons.append("raw/split equity or SPY coverage is incomplete")
    if total_security_count < cohort_size:
        market_restricted_reasons.append("provider total-return bars do not cover the full development cohort")
    elif total_start is None or str(total_start) > str(raw["development_start"]):
        market_restricted_reasons.append("provider total-return bars begin after the development period starts")
    market_restricted_reasons.append("ordinary dividends and splits still require a deterministic wealth-ledger reconciliation")
    if complex_actions:
        market_restricted_reasons.append("labels crossing unresolved complex actions must be withheld")

    ttm_sets = sec["candidate_complete_flow_sets"]
    best_ttm_security_count = max((int(item["security_count"]) for item in ttm_sets.values()), default=0)
    ttm_reasons = [
        "candidate Q1/H1/9M/FY sets are not proof of context-compatible standalone quarters",
        "the fail-closed quarterly/TTM resolver is not implemented yet",
    ]
    if best_ttm_security_count == 0:
        ttm_reasons.append("no candidate complete flow sets were measured")

    endpoint_count = int(shares.get("endpoint_security_count", 0))
    endpoint_status = "restricted" if endpoint_count else "blocked"
    endpoint_reasons = ["split and structural-action reconciliation is not yet implemented for the primary endpoint path"]
    if endpoint_count < cohort_size:
        endpoint_reasons.append("dated endpoint-share facts do not cover the full cohort")

    sic_count = int(sic.get("normalized_security_count", 0))
    sic_status = "pass" if cohort_size and sic_count / cohort_size >= 0.95 else "deferred"
    sic_reasons = [] if sic_status == "pass" else [
        "accession-dated ASSIGNED-SIC is not normalized with the required cohort coverage",
        "current static sectors cannot substitute for historical SIC",
    ]

    min_weekly_252 = float(weekly.get("minimum_252_session_coverage_after_eligibility", 0.0))
    first_eligible_252 = weekly.get("first_90pct_252_session_formation")
    weekly_status = "pass" if first_eligible_252 and min_weekly_252 >= 0.90 else "blocked"
    weekly_reasons: list[str] = []
    if first_eligible_252 and str(first_eligible_252) > str(weekly.get("first_formation")):
        weekly_status = "restricted"
        weekly_reasons.append(
            f"252-session features become eligible only on {first_eligible_252}; earlier formations must be excluded"
        )
    elif weekly_status == "blocked":
        weekly_reasons.append("no weekly formation reaches 90% cohort coverage for 252-session features")

    return {
        "corporate_action_wealth_label": _capability(
            "restricted" if ordinary_actions and split_security_count and raw_security_count and spy_split_rows else "blocked",
            evidence={
                "ordinary_action_count": ordinary_actions,
                "complex_action_count": complex_actions,
                "split_adjusted_security_count": split_security_count,
                "unadjusted_security_count": raw_security_count,
                "total_return_security_count": total_security_count,
                "total_return_start_date": total_start,
                "spy_split_adjusted_rows": spy_split_rows,
            },
            reasons=market_restricted_reasons,
        ),
        "point_in_time_quarterly_ttm": _capability(
            "restricted" if best_ttm_security_count else "blocked",
            evidence={
                "best_candidate_complete_flow_set_security_count": best_ttm_security_count,
                "candidate_complete_flow_sets": ttm_sets,
                "immutable_observation_count": sec["immutable_observation_count"],
            },
            reasons=ttm_reasons,
        ),
        "endpoint_shares": _capability(
            endpoint_status,
            evidence=shares,
            reasons=endpoint_reasons,
        ),
        "historical_sic_ff12": _capability(sic_status, evidence=sic, reasons=sic_reasons),
        "weekly_market_features": _capability(weekly_status, evidence=weekly, reasons=weekly_reasons),
    }


def _basis_summary(cursor, table: str, ticker_clause: str = "") -> dict[str, dict[str, object]]:
    security_column = "COUNT(DISTINCT security_id)" if table == "quantrade.daily_price_bars" else "1"
    cursor.execute(
        f"""SELECT adjustment_basis,COUNT(*),{security_column},MIN(session_date),MAX(session_date)
              FROM {table}
             WHERE session='regular' {ticker_clause}
             GROUP BY adjustment_basis ORDER BY adjustment_basis"""
    )
    return {
        str(basis): {
            "row_count": int(rows), "security_count": int(securities),
            "start_date": start.isoformat(), "end_date": end.isoformat(),
        }
        for basis, rows, securities, start, end in cursor
    }


def _weekly_coverage(cursor, *, start: date, end: date, cohort_size: int) -> dict[str, object]:
    cursor.execute(
        """SELECT session_date FROM quantrade.benchmark_daily_price_bars
            WHERE benchmark_ticker='SPY' AND session='regular' AND adjustment_basis='split_adjusted'
              AND session_date BETWEEN %s AND %s ORDER BY session_date""",
        (start, end),
    )
    sessions = [row[0] for row in cursor]
    formations: dict[tuple[int, int], date] = {}
    for session in sessions:
        iso_year, iso_week, _ = session.isocalendar()
        formations[(iso_year, iso_week)] = session
    weekly_dates = sorted(formations.values())
    if not weekly_dates or cohort_size <= 0:
        return {
            "formation_count": 0, "minimum_60_session_coverage": 0.0,
            "minimum_252_session_coverage": 0.0, "months_with_unequal_raw_weight": 0,
        }
    cursor.execute(
        """WITH cohort AS (
                 SELECT membership.security_id
                   FROM quantrade.research_cohort_memberships membership
                   JOIN quantrade.research_cohorts cohort USING(research_cohort_id)
                  WHERE cohort.cohort_code=%s
             )
             SELECT bar.security_id::text,bar.session_date
               FROM quantrade.daily_price_bars bar
               JOIN cohort USING(security_id)
              WHERE bar.session='regular' AND bar.adjustment_basis='split_adjusted'
                AND bar.session_date <= %s
              ORDER BY bar.security_id,bar.session_date""",
        (CURRENT_SURVIVORS_COHORT, end),
    )
    history: dict[str, list[date]] = defaultdict(list)
    for security_id, session in cursor:
        history[str(security_id)].append(session)
    import bisect

    cover_60: list[tuple[date, float]] = []
    cover_252: list[tuple[date, float]] = []
    for formation in weekly_dates:
        counts = [bisect.bisect_right(dates, formation) for dates in history.values()]
        cover_60.append((formation, sum(value >= 61 for value in counts) / cohort_size))
        cover_252.append((formation, sum(value >= 253 for value in counts) / cohort_size))
    eligible_60 = [(formation, coverage) for formation, coverage in cover_60 if coverage >= 0.90]
    eligible_252 = [(formation, coverage) for formation, coverage in cover_252 if coverage >= 0.90]
    first_60 = eligible_60[0][0] if eligible_60 else None
    first_252 = eligible_252[0][0] if eligible_252 else None
    after_60 = [coverage for formation, coverage in cover_60 if first_60 and formation >= first_60]
    after_252 = [coverage for formation, coverage in cover_252 if first_252 and formation >= first_252]
    month_formations = Counter((item.year, item.month) for item in weekly_dates)
    raw_month_weights = {f"{year:04d}-{month:02d}": count for (year, month), count in sorted(month_formations.items())}
    return {
        "formation_count": len(weekly_dates),
        "first_formation": weekly_dates[0].isoformat(),
        "last_formation": weekly_dates[-1].isoformat(),
        "first_90pct_60_session_formation": first_60.isoformat() if first_60 else None,
        "first_90pct_252_session_formation": first_252.isoformat() if first_252 else None,
        "minimum_60_session_coverage": round(min(value for _, value in cover_60), 6),
        "minimum_60_session_coverage_after_eligibility": round(min(after_60), 6) if after_60 else 0.0,
        "median_60_session_coverage": round(sorted(value for _, value in cover_60)[len(cover_60) // 2], 6),
        "minimum_252_session_coverage": round(min(value for _, value in cover_252), 6),
        "minimum_252_session_coverage_after_eligibility": round(min(after_252), 6) if after_252 else 0.0,
        "median_252_session_coverage": round(sorted(value for _, value in cover_252)[len(cover_252) // 2], 6),
        "eligible_252_formation_count": len(after_252),
        "months_with_four_formations": sum(value == 4 for value in month_formations.values()),
        "months_with_five_formations": sum(value == 5 for value in month_formations.values()),
        "months_with_unequal_raw_weight": len(set(month_formations.values())) > 1,
        "monthly_formation_counts": raw_month_weights,
        "required_weight_rule": "each calendar month totals 1; divide by weeks then eligible securities",
    }


def load_audit(database_url: str, *, start: date, end: date) -> dict[str, object]:
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute(
            """SELECT COUNT(*) FROM quantrade.research_cohort_memberships membership
                JOIN quantrade.research_cohorts cohort USING(research_cohort_id)
               WHERE cohort.cohort_code=%s""",
            (CURRENT_SURVIVORS_COHORT,),
        )
        cohort_size = int(cursor.fetchone()[0])
        market = {
            "equity_basis": _basis_summary(cursor, "quantrade.daily_price_bars"),
            "benchmark_basis": _basis_summary(
                cursor, "quantrade.benchmark_daily_price_bars", "AND benchmark_ticker='SPY'",
            ),
        }
        cursor.execute(
            """SELECT action_type,COUNT(*) FROM quantrade.corporate_actions action
                JOIN quantrade.research_cohort_memberships membership USING(security_id)
                JOIN quantrade.research_cohorts cohort USING(research_cohort_id)
               WHERE cohort.cohort_code=%s
                 AND COALESCE(action.effective_date,action.process_date) BETWEEN %s AND %s
               GROUP BY action_type ORDER BY action_type""",
            (CURRENT_SURVIVORS_COHORT, start, end),
        )
        actions = {str(action_type): int(count) for action_type, count in cursor}
        cursor.execute(
            """SELECT ff.concept,COUNT(DISTINCT ff.security_id),COUNT(*),
                      COUNT(*) FILTER (WHERE ff.period_start IS NOT NULL)
                 FROM quantrade.filing_facts ff
                 JOIN quantrade.filings filing USING(filing_id)
                 JOIN quantrade.research_cohort_memberships membership ON membership.security_id=ff.security_id
                 JOIN quantrade.research_cohorts cohort USING(research_cohort_id)
                WHERE cohort.cohort_code=%s AND ff.concept=ANY(%s)
                  AND ff.period_end >= %s::date - interval '18 months'
                  AND filing.accepted_at + interval '5 minutes' <= (%s::date + time '20:00') AT TIME ZONE 'America/Toronto'
                GROUP BY ff.concept ORDER BY ff.concept""",
            (CURRENT_SURVIVORS_COHORT, list(FLOW_CONCEPTS + BALANCE_CONCEPTS + SHARE_CONCEPTS), start, end),
        )
        concept_coverage = {
            str(concept): {
                "security_count": int(securities), "fact_count": int(facts),
                "duration_fact_count": int(duration_facts),
            }
            for concept, securities, facts, duration_facts in cursor
        }
        cursor.execute(
            """WITH eligible AS (
                   SELECT ff.security_id,ff.concept,ff.unit,ff.fiscal_year,
                          array_agg(DISTINCT ff.fiscal_period) AS periods
                     FROM quantrade.filing_facts ff
                     JOIN quantrade.filings filing USING(filing_id)
                     JOIN quantrade.research_cohort_memberships membership ON membership.security_id=ff.security_id
                     JOIN quantrade.research_cohorts cohort USING(research_cohort_id)
                    WHERE cohort.cohort_code=%s AND ff.concept=ANY(%s)
                      AND ff.period_start IS NOT NULL AND ff.fiscal_year IS NOT NULL
                      AND ff.fiscal_year BETWEEN %s AND %s
                      AND ff.fiscal_period=ANY(ARRAY['Q1','Q2','Q3','FY'])
                      AND filing.accepted_at + interval '5 minutes' <= (%s::date + time '20:00') AT TIME ZONE 'America/Toronto'
                    GROUP BY ff.security_id,ff.concept,ff.unit,ff.fiscal_year
               ), complete AS (
                   SELECT * FROM eligible
                    WHERE periods @> ARRAY['Q1','Q2','Q3','FY']::text[]
               )
               SELECT concept,COUNT(DISTINCT security_id),COUNT(*)
                 FROM complete GROUP BY concept ORDER BY concept""",
            (CURRENT_SURVIVORS_COHORT, list(FLOW_CONCEPTS), start.year - 1, end.year, end),
        )
        complete_sets = {
            str(concept): {"security_count": int(securities), "security_year_unit_sets": int(sets)}
            for concept, securities, sets in cursor
        }
        cursor.execute("SELECT COUNT(*) FROM quantrade.filing_fact_observations")
        observation_count = int(cursor.fetchone()[0])
        cursor.execute(
            """SELECT
                 COUNT(DISTINCT ff.security_id) FILTER (WHERE ff.concept='EntityCommonStockSharesOutstanding'),
                 COUNT(DISTINCT ff.security_id) FILTER (WHERE ff.concept='WeightedAverageNumberOfSharesOutstandingBasic'),
                 COUNT(DISTINCT ff.security_id) FILTER (WHERE ff.concept='EntityCommonStockSharesOutstanding' AND ff.taxonomy='dei')
               FROM quantrade.filing_facts ff
               JOIN quantrade.filings filing USING(filing_id)
               JOIN quantrade.research_cohort_memberships membership ON membership.security_id=ff.security_id
               JOIN quantrade.research_cohorts cohort USING(research_cohort_id)
              WHERE cohort.cohort_code=%s
                AND ff.period_end >= %s::date - interval '18 months'
                AND filing.accepted_at + interval '5 minutes' <= (%s::date + time '20:00') AT TIME ZONE 'America/Toronto'""",
            (CURRENT_SURVIVORS_COHORT, start, end),
        )
        endpoint, average_basic, dei_endpoint = (int(value) for value in cursor.fetchone())
        cursor.execute(
            """SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema='quantrade' AND column_name IN ('assigned_sic','sic_code')"""
        )
        sic_columns = int(cursor.fetchone()[0])
        weekly = _weekly_coverage(cursor, start=start, end=end, cohort_size=cohort_size)

    raw: dict[str, object] = {
        "audit_key": AUDIT_KEY,
        "audit_version": AUDIT_VERSION,
        "research_cohort": CURRENT_SURVIVORS_COHORT,
        "data_capability_tier": "B",
        "survivorship_biased": True,
        "holdout_used": False,
        "download_performed": False,
        "development_start": start.isoformat(),
        "development_end": end.isoformat(),
        "cohort_size": cohort_size,
        "market": market,
        "corporate_actions": actions,
        "sec": {
            "concept_coverage": concept_coverage,
            "candidate_complete_flow_sets": complete_sets,
            "immutable_observation_count": observation_count,
            "candidate_set_warning": "fiscal-period presence is only a feasibility screen; context validation remains required",
        },
        "shares": {
            "endpoint_security_count": endpoint,
            "dei_endpoint_security_count": dei_endpoint,
            "weighted_average_basic_security_count": average_basic,
            "primary_policy": "endpoint shares only; weighted-average basic shares are robustness-only",
        },
        "historical_sic": {
            "normalized_column_count": sic_columns,
            "normalized_security_count": 0,
            "current_static_sector_is_not_substitute": True,
        },
        "weekly_market_features": weekly,
        "limitations": [
            "fixed current-survivors cohort; historical membership and delistings are not verified",
            "legacy SEC facts use the documented acceptance-plus-five-minute Tier-B rule",
            "candidate quarterly component counts do not prove context-compatible TTM values",
            "no candidate return, prediction, or holdout outcome was inspected",
        ],
    }
    raw["capabilities"] = classify_capabilities(raw)
    raw["overall_status"] = (
        "blocked" if any(item["status"] == "blocked" for item in raw["capabilities"].values())
        else "restricted" if any(item["status"] in {"restricted", "deferred"} for item in raw["capabilities"].values())
        else "pass"
    )
    return raw


def _settings(env_file: Path):
    from .config import Settings

    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the read-only Phase 9C data-feasibility audit")
    parser.add_argument("--start", type=date.fromisoformat, default=DEFAULT_START)
    parser.add_argument("--end", type=date.fromisoformat, default=DEFAULT_END)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    if arguments.start > arguments.end:
        parser.error("--start must not be after --end")
    if arguments.output.exists():
        raise DataQualityError(f"refusing to overwrite immutable audit: {arguments.output}")
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    report = load_audit(settings.database_url, start=arguments.start, end=arguments.end)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    statuses = ",".join(f"{key}={value['status']}" for key, value in report["capabilities"].items())
    print(f"overall_status={report['overall_status']}; {statuses}")


if __name__ == "__main__":
    main()
