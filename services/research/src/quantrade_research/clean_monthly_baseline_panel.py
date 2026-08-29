"""Rebuild monthly baseline ranks from approved point-in-time inputs, never old scores."""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path

from .feature_diagnostics import FeatureOutcome
from .features import baseline_feature_registry
from .fundamentals import (
    FundamentalFactObservation, calculate_earnings_yield_ttm, calculate_return_on_assets_ttm,
)
from .historical_cohorts import CURRENT_SURVIVORS_COHORT
from .momentum import FeaturePriceObservation, calculate_momentum_12_1, calculate_relative_strength_6m
from .quality import DataQualityError
from .ranking import SectorClassification, build_sector_aware_percentile_ranks
from .risk_liquidity import calculate_median_dollar_volume_20d, calculate_trailing_volatility_60d
from .score_run import _dotenv_values, _outcome
from .sec_fact_resolver import PostgresSecFactResolver, resolve_facts_as_of
from .sec_form_scope import RESEARCH_RELEVANT_FORMS


PANEL_KEY = "tier_b_clean_monthly_baseline_panel"
PANEL_VERSION = "v1"
HOLDOUT_START = date(2025, 7, 1)
HOLDOUT_END = date(2026, 6, 30)
FEATURES = (
    "momentum_12_1", "relative_strength_6m", "trailing_volatility_60d",
    "median_dollar_volume_20d", "earnings_yield_ttm", "return_on_assets_ttm",
)


@dataclass(frozen=True, slots=True)
class Formation:
    formation_date: date
    decision_at: datetime


def _load_inputs(database_url: str, start_date: date, end_date: date):
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT membership.security_id::text
               FROM quantrade.research_cohort_memberships membership
               JOIN quantrade.research_cohorts cohort USING(research_cohort_id)
               WHERE cohort.cohort_code=%s ORDER BY membership.security_id""",
            (CURRENT_SURVIVORS_COHORT,),
        )
        security_ids = tuple(str(row[0]) for row in cursor.fetchall())
        if len(security_ids) != 500:
            raise DataQualityError("clean monthly panel requires exactly 500 cohort members")
        cursor.execute(
            """WITH monthly AS (
                   SELECT MAX(score_date) AS formation_date
                   FROM quantrade.score_snapshots
                   WHERE score_date BETWEEN %s AND %s
                   GROUP BY date_trunc('month',score_date)
               )
               SELECT monthly.formation_date,MAX(snapshot.decision_at)
               FROM monthly JOIN quantrade.score_snapshots snapshot
                 ON snapshot.score_date=monthly.formation_date
               GROUP BY monthly.formation_date ORDER BY monthly.formation_date""",
            (start_date, end_date),
        )
        formations = tuple(Formation(row[0], row[1]) for row in cursor.fetchall())
        if not formations:
            raise DataQualityError("clean monthly panel has no formation dates")
        latest = formations[-1]
        cursor.execute(
            """SELECT security_id::text,session_date,close_price,adjustment_basis,available_at,volume
               FROM quantrade.daily_price_bars
               WHERE security_id=ANY(%s::uuid[]) AND session='regular'
                 AND session_date<=%s AND available_at<=%s
                 AND adjustment_basis IN ('split_adjusted','unadjusted')
               ORDER BY security_id,session_date,adjustment_basis""",
            (list(security_ids), latest.formation_date, latest.decision_at),
        )
        prices: dict[str, list[FeaturePriceObservation]] = defaultdict(list)
        for row in cursor:
            prices[str(row[0])].append(FeaturePriceObservation(*row))
        cursor.execute(
            """SELECT %s,session_date,close_price,adjustment_basis,available_at,volume
               FROM quantrade.benchmark_daily_price_bars
               WHERE benchmark_ticker=%s AND session='regular' AND adjustment_basis='split_adjusted'
                 AND session_date<=%s AND available_at<=%s ORDER BY session_date""",
            ("SPY", "SPY", latest.formation_date, latest.decision_at),
        )
        benchmark = tuple(FeaturePriceObservation(*row) for row in cursor.fetchall())
        cursor.execute(
            """SELECT DISTINCT ON (security_id) security_id::text,sector_code,as_of_date,available_at
               FROM quantrade.sector_classifications WHERE security_id=ANY(%s::uuid[])
               ORDER BY security_id,as_of_date DESC,available_at DESC""",
            (list(security_ids),),
        )
        sectors = tuple(SectorClassification(*row) for row in cursor.fetchall())
        cursor.execute(
            """SELECT DISTINCT ON (security_id) security_id::text,ticker
               FROM quantrade.listings WHERE security_id=ANY(%s::uuid[])
               ORDER BY security_id,valid_from DESC""",
            (list(security_ids),),
        )
        tickers = {str(row[0]): str(row[1]) for row in cursor.fetchall()}
    return security_ids, formations, prices, benchmark, sectors, tickers


def _fundamental(fact) -> FundamentalFactObservation:
    return FundamentalFactObservation(
        fact.security_id, fact.filing_id, fact.taxonomy, fact.concept, fact.unit,
        fact.value, fact.period_start, fact.period_end, fact.available_at,
    )


def build_clean_monthly_baseline_panel(
    *, database_url: str, destination: Path,
    start_date: date = date(2022, 1, 1), end_date: date = HOLDOUT_END,
) -> dict[str, object]:
    manifest = destination.with_suffix(".json")
    if destination.exists() or manifest.exists():
        raise DataQualityError("refusing to overwrite immutable clean monthly baseline panel")
    security_ids, formations, prices, benchmark, sectors, tickers = _load_inputs(
        database_url, start_date, end_date,
    )
    latest = formations[-1]
    resolver = PostgresSecFactResolver(database_url)
    try:
        accounting = resolver.load_candidates(
            security_ids=security_ids, taxonomy="us-gaap",
            concepts=("Assets", "NetIncomeLoss", "ProfitLoss"),
            formation_date=latest.formation_date, decision_at=latest.decision_at,
        )
        shares = resolver.load_candidates(
            security_ids=security_ids, taxonomy="dei",
            concepts=("EntityCommonStockSharesOutstanding",),
            formation_date=latest.formation_date, decision_at=latest.decision_at,
        )
    finally:
        resolver.close()
    fact_history = (*accounting, *shares)
    registry = baseline_feature_registry()
    price_dates = {key: [item.session_date for item in rows] for key, rows in prices.items()}
    benchmark_dates = [item.session_date for item in benchmark]
    destination.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "partition", "formation_date", "decision_at", "security_id", "ticker", "sector_code",
        "baseline_rank", *FEATURES, "row_sha256",
    ]
    coverage = Counter()
    exclusions: dict[str, Counter[str]] = defaultdict(Counter)
    row_count = 0
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for index, formation in enumerate(formations, start=1):
            eligible_facts = resolve_facts_as_of(
                (
                    item for item in fact_history
                    if item.period_end <= formation.formation_date and item.available_at <= formation.decision_at
                ),
                decision_at=formation.decision_at,
            )
            facts: dict[str, list[FundamentalFactObservation]] = defaultdict(list)
            for item in eligible_facts:
                facts[item.security_id].append(_fundamental(item))
            benchmark_end = bisect_right(benchmark_dates, formation.formation_date)
            eligible_benchmark = [
                item for item in benchmark[:benchmark_end] if item.available_at <= formation.decision_at
            ]
            outcomes: list[FeatureOutcome] = []
            for security_id in security_ids:
                price_end = bisect_right(price_dates.get(security_id, []), formation.formation_date)
                eligible_prices = [
                    item for item in prices.get(security_id, ())[:price_end]
                    if item.available_at <= formation.decision_at
                ]
                security_facts = facts.get(security_id, ())
                outcomes.extend((
                    _outcome(security_id, formation.formation_date, registry, "momentum_12_1", lambda p=eligible_prices,s=security_id: calculate_momentum_12_1(p,security_id=s,formation_date=formation.formation_date,decision_at=formation.decision_at,registry=registry)),
                    _outcome(security_id, formation.formation_date, registry, "relative_strength_6m", lambda p=eligible_prices,s=security_id: calculate_relative_strength_6m(p,eligible_benchmark,security_id=s,benchmark_security_id="SPY",formation_date=formation.formation_date,decision_at=formation.decision_at,registry=registry)),
                    _outcome(security_id, formation.formation_date, registry, "trailing_volatility_60d", lambda p=eligible_prices,s=security_id: calculate_trailing_volatility_60d(p,security_id=s,formation_date=formation.formation_date,decision_at=formation.decision_at,registry=registry)),
                    _outcome(security_id, formation.formation_date, registry, "median_dollar_volume_20d", lambda p=eligible_prices,s=security_id: calculate_median_dollar_volume_20d(p,security_id=s,formation_date=formation.formation_date,decision_at=formation.decision_at,registry=registry)),
                    _outcome(security_id, formation.formation_date, registry, "earnings_yield_ttm", lambda p=eligible_prices,f=security_facts,s=security_id: calculate_earnings_yield_ttm(f,p,security_id=s,formation_date=formation.formation_date,decision_at=formation.decision_at,registry=registry)),
                    _outcome(security_id, formation.formation_date, registry, "return_on_assets_ttm", lambda f=security_facts,s=security_id: calculate_return_on_assets_ttm(f,security_id=s,formation_date=formation.formation_date,decision_at=formation.decision_at,registry=registry)),
                ))
            ranks = build_sector_aware_percentile_ranks(
                outcomes, sectors, formation_date=formation.formation_date,
                decision_at=formation.decision_at, universe_security_ids=security_ids,
                registry=registry, allow_static_tier_b_grouping=True,
            )
            by_security: dict[str, dict[str, object]] = defaultdict(dict)
            for rank in ranks:
                by_security[rank.security_id][rank.feature_key] = rank
                if rank.percentile is not None:
                    coverage[rank.feature_key] += 1
                else:
                    exclusions[rank.feature_key][rank.unavailable_reason or "unknown"] += 1
            eligible_scores = {
                security_id: sum(
                    (by_security[security_id][feature].percentile for feature in FEATURES), Decimal("0")
                ) / Decimal(len(FEATURES))
                for security_id in security_ids
                if all(by_security[security_id][feature].percentile is not None for feature in FEATURES)
            }
            ordered = sorted(eligible_scores, key=lambda key: (-eligible_scores[key], key))
            baseline_ranks = {security_id: position for position, security_id in enumerate(ordered, start=1)}
            for security_id in security_ids:
                row: dict[str, object] = {
                    "partition": "holdout" if formation.formation_date >= HOLDOUT_START else "development",
                    "formation_date": formation.formation_date.isoformat(),
                    "decision_at": formation.decision_at.isoformat(), "security_id": security_id,
                    "ticker": tickers.get(security_id, "Unavailable"),
                    "sector_code": by_security[security_id][FEATURES[0]].sector_code,
                    "baseline_rank": baseline_ranks.get(security_id, ""),
                }
                for feature in FEATURES:
                    rank = by_security[security_id][feature]
                    row[feature] = str(rank.percentile) if rank.percentile is not None else ""
                digest_payload = {key: row[key] for key in fields if key != "row_sha256"}
                row["row_sha256"] = sha256(
                    json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                writer.writerow(row)
                row_count += 1
            print(
                f"clean_baseline_progress={index}/{len(formations)}; formation_date={formation.formation_date}; "
                f"eligible={len(eligible_scores)}", flush=True,
            )
    metadata: dict[str, object] = {
        "panel_key": PANEL_KEY, "panel_version": PANEL_VERSION,
        "content_sha256": sha256(destination.read_bytes()).hexdigest(),
        "cohort_code": CURRENT_SURVIVORS_COHORT, "data_capability_tier": "B",
        "row_count": row_count, "formation_count": len(formations), "security_count": len(security_ids),
        "development_formation_count": sum(item.formation_date < HOLDOUT_START for item in formations),
        "holdout_formation_count": sum(item.formation_date >= HOLDOUT_START for item in formations),
        "start_date": formations[0].formation_date.isoformat(),
        "end_date": formations[-1].formation_date.isoformat(),
        "features": list(FEATURES), "feature_registry_hash": registry.registry_hash,
        "sec_form_scope": sorted(RESEARCH_RELEVANT_FORMS),
        "source_rule": "recomputed from point-in-time normalized inputs; historical score explanations are not used",
        "holdout_performance_evaluated": False,
        "coverage": {feature: coverage[feature] for feature in FEATURES},
        "exclusions": {feature: dict(sorted(values.items())) for feature, values in exclusions.items()},
        "limitations": [
            "Tier B current-survivors cohort is survivorship-biased",
            "current sectors are static Tier-B groupings, not historical point-in-time classifications",
            "SEC facts are restricted to canonical 10-K, 10-Q, 20-F, 40-F, and 8-K forms",
        ],
    }
    manifest.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata


def _settings(env_file: Path):
    from .config import Settings

    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build clean monthly six-feature ranks through the holdout")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--start", type=date.fromisoformat, default=date(2022, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=HOLDOUT_END)
    arguments = parser.parse_args()
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    metadata = build_clean_monthly_baseline_panel(
        database_url=settings.database_url, destination=arguments.output,
        start_date=arguments.start, end_date=arguments.end,
    )
    print(
        f"clean_baseline_rows={metadata['row_count']}; formations={metadata['formation_count']}; "
        f"sha256={metadata['content_sha256']}; holdout_performance_evaluated=false"
    )


if __name__ == "__main__":
    main()
