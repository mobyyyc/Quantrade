"""Materialize the compact, lineage-bearing Phase 9B monthly feature panel."""

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
from typing import Iterable, Sequence

from .historical_cohorts import CURRENT_SURVIVORS_COHORT
from .quality import DataQualityError
from .score_run import _dotenv_values
from .sec_fact_resolver import PostgresSecFactResolver, ResolvedSecFact


PANEL_KEY = "tier_b_monthly_feature_panel"
PANEL_VERSION = "v1"
FEATURE_RULE_VERSION = "tier_b_monthly_feature_family_v2"
HOLDOUT_START = date(2025, 7, 1)
FEATURES = ("short_term_reversal_20d", "asset_growth_yoy", "net_share_issuance_yoy", "accrual_quality")


@dataclass(frozen=True, slots=True)
class PriceInput:
    price_bar_id: str
    security_id: str
    session_date: date
    close_price: Decimal
    available_at: datetime
    source_reference: str


@dataclass(frozen=True, slots=True)
class ActionInput:
    action_id: str
    security_id: str
    action_type: str
    effective_date: date
    numerator: Decimal | None
    denominator: Decimal | None
    available_at: datetime
    source_reference: str


@dataclass(frozen=True, slots=True)
class FeatureCell:
    value: Decimal | None
    lineage: tuple[str, ...]
    exclusion: str | None = None

    def digest(self, *, security_id: str, formation_date: date, feature_key: str) -> str:
        payload = {
            "security_id": security_id,
            "formation_date": formation_date.isoformat(),
            "feature_key": feature_key,
            "rule_version": FEATURE_RULE_VERSION,
            "value": str(self.value) if self.value is not None else None,
            "lineage": list(self.lineage),
            "exclusion": self.exclusion,
        }
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _latest_per_period(facts: Iterable[ResolvedSecFact]) -> dict[date, ResolvedSecFact]:
    selected: dict[date, ResolvedSecFact] = {}
    for fact in facts:
        current = selected.get(fact.period_end)
        if current is None or (fact.available_at, fact.is_amendment, fact.accession_number) > (
            current.available_at, current.is_amendment, current.accession_number,
        ):
            selected[fact.period_end] = fact
    return selected


def _annual_prior(periods: Sequence[date], current: date) -> date | None:
    candidates = [item for item in periods if 330 <= (current - item).days <= 400]
    return min(candidates, key=lambda item: (abs((current - item).days - 365), -item.toordinal())) if candidates else None


def short_term_reversal(prices: Sequence[PriceInput]) -> FeatureCell:
    """Return t-21 through t-1 performance, deliberately excluding formation day."""
    if len(prices) < 22:
        return FeatureCell(None, (), "insufficient_22_session_price_history")
    start, end = prices[-22], prices[-2]
    if start.close_price <= 0 or end.close_price <= 0:
        return FeatureCell(None, (), "nonpositive_price")
    return FeatureCell(end.close_price / start.close_price - Decimal("1"), (start.price_bar_id, end.price_bar_id))


def asset_growth(facts: Sequence[ResolvedSecFact]) -> FeatureCell:
    periods = _latest_per_period(fact for fact in facts if fact.concept == "Assets" and fact.unit == "USD")
    if not periods:
        return FeatureCell(None, (), "missing_assets")
    current_date = max(periods)
    prior_date = _annual_prior(tuple(periods), current_date)
    if prior_date is None:
        return FeatureCell(None, (), "missing_comparable_prior_assets")
    current, prior = periods[current_date], periods[prior_date]
    if current.value <= 0 or prior.value <= 0:
        return FeatureCell(None, (), "nonpositive_assets")
    return FeatureCell(current.value / prior.value - Decimal("1"), (prior.lineage_key, current.lineage_key))


def net_share_issuance(facts: Sequence[ResolvedSecFact], actions: Sequence[ActionInput]) -> FeatureCell:
    selected: tuple[dict[date, ResolvedSecFact], date, date] | None = None
    for concept in ("EntityCommonStockSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic"):
        candidates = [fact for fact in facts if fact.concept == concept and fact.unit == "shares"]
        if concept == "WeightedAverageNumberOfSharesOutstandingBasic":
            candidates = [
                fact for fact in candidates
                if fact.period_start is not None and 330 <= (fact.period_end - fact.period_start).days <= 370
            ]
        periods = _latest_per_period(candidates)
        if not periods:
            continue
        current_date = max(periods)
        prior_date = _annual_prior(tuple(periods), current_date)
        if prior_date is not None:
            selected = periods, current_date, prior_date
            break
    if selected is None:
        return FeatureCell(None, (), "missing_comparable_prior_shares")
    periods, current_date, prior_date = selected
    structural = [
        item for item in actions
        if prior_date < item.effective_date <= current_date
        and item.action_type in {"cash_merger", "spin_off", "stock_and_cash_merger", "stock_merger"}
    ]
    if structural:
        return FeatureCell(None, tuple(item.action_id for item in structural), "structural_corporate_action")
    split_factor = Decimal("1")
    split_lineage: list[str] = []
    for item in actions:
        if not prior_date < item.effective_date <= current_date:
            continue
        if item.action_type not in {"forward_split", "reverse_split", "unit_split"}:
            continue
        if item.numerator is None or item.denominator is None or item.numerator <= 0 or item.denominator <= 0:
            return FeatureCell(None, (item.action_id,), "invalid_split_ratio")
        split_factor *= item.numerator / item.denominator
        split_lineage.append(item.action_id)
    current, prior = periods[current_date], periods[prior_date]
    if current.value <= 0 or prior.value <= 0:
        return FeatureCell(None, (), "nonpositive_shares")
    value = current.value / (prior.value * split_factor) - Decimal("1")
    return FeatureCell(value, (prior.lineage_key, *split_lineage, current.lineage_key))


def accrual_quality(facts: Sequence[ResolvedSecFact]) -> FeatureCell:
    by_identity: dict[tuple[str, date, date], ResolvedSecFact] = {}
    for fact in facts:
        if fact.period_start is None or not 330 <= (fact.period_end - fact.period_start).days <= 370:
            continue
        if fact.concept not in {"NetIncomeLoss", "ProfitLoss", "NetCashProvidedByUsedInOperatingActivities"}:
            continue
        key = (fact.concept, fact.period_start, fact.period_end)
        current = by_identity.get(key)
        if current is None or (fact.available_at, fact.is_amendment, fact.accession_number) > (
            current.available_at, current.is_amendment, current.accession_number,
        ):
            by_identity[key] = fact
    assets = _latest_per_period(fact for fact in facts if fact.concept == "Assets" and fact.unit == "USD")
    candidates: list[tuple[date, ResolvedSecFact, ResolvedSecFact, ResolvedSecFact, ResolvedSecFact]] = []
    periods = {(start, end) for _, start, end in by_identity}
    for start, end in periods:
        net_income = by_identity.get(("NetIncomeLoss", start, end)) or by_identity.get(("ProfitLoss", start, end))
        cash_flow = by_identity.get(("NetCashProvidedByUsedInOperatingActivities", start, end))
        ending_assets = assets.get(end)
        beginning_dates = [item for item in assets if abs((item - start).days) <= 7]
        beginning_assets = assets[min(beginning_dates, key=lambda item: abs((item - start).days))] if beginning_dates else None
        if net_income and cash_flow and ending_assets and beginning_assets:
            candidates.append((end, net_income, cash_flow, beginning_assets, ending_assets))
    if not candidates:
        return FeatureCell(None, (), "missing_aligned_annual_accrual_inputs")
    _, net_income, cash_flow, beginning_assets, ending_assets = max(candidates, key=lambda item: item[0])
    if beginning_assets.value <= 0 or ending_assets.value <= 0:
        return FeatureCell(None, (), "nonpositive_assets")
    average_assets = (beginning_assets.value + ending_assets.value) / Decimal("2")
    value = (net_income.value - cash_flow.value) / average_assets
    return FeatureCell(
        value,
        (net_income.lineage_key, cash_flow.lineage_key, beginning_assets.lineage_key, ending_assets.lineage_key),
    )


def _load_core_inputs(database_url: str):
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT membership.security_id::text
               FROM quantrade.research_cohort_memberships membership
               JOIN quantrade.research_cohorts cohort USING (research_cohort_id)
               WHERE cohort.cohort_code=%s ORDER BY membership.security_id""",
            (CURRENT_SURVIVORS_COHORT,),
        )
        security_ids = tuple(row[0] for row in cursor.fetchall())
        if len(security_ids) != 500:
            raise DataQualityError(f"{CURRENT_SURVIVORS_COHORT} must contain exactly 500 securities")
        cursor.execute(
            """SELECT MAX(snapshot.score_date), MAX(snapshot.decision_at)
               FROM quantrade.score_snapshots snapshot
               JOIN quantrade.forward_score_outcomes outcome USING (score_snapshot_id)
               WHERE outcome.status='completed' AND outcome.horizon_sessions=20
                 AND outcome.outcome_date < %s
               GROUP BY date_trunc('month', snapshot.score_date)
               ORDER BY MAX(snapshot.score_date)""",
            (HOLDOUT_START,),
        )
        formations = tuple((row[0], row[1]) for row in cursor.fetchall())
        if len(formations) < 24:
            raise DataQualityError("monthly panel requires at least 24 label-safe formations")
        end_date, latest_decision = formations[-1]
        cursor.execute(
            """SELECT daily_price_bar_id::text,security_id::text,session_date,close_price,available_at,source_reference
               FROM quantrade.daily_price_bars
               WHERE security_id=ANY(%s::uuid[]) AND session='regular' AND adjustment_basis='split_adjusted'
                 AND session_date<=%s ORDER BY security_id,session_date""",
            (list(security_ids), end_date),
        )
        prices: dict[str, list[PriceInput]] = defaultdict(list)
        for row in cursor:
            prices[row[1]].append(PriceInput(*row))
        cursor.execute(
            """SELECT corporate_action_id::text,security_id::text,action_type,effective_date,
                      ratio_numerator,ratio_denominator,available_at,source_reference
               FROM quantrade.corporate_actions
               WHERE security_id=ANY(%s::uuid[]) AND effective_date<=%s
               ORDER BY security_id,effective_date,corporate_action_id""",
            (list(security_ids), end_date),
        )
        actions: dict[str, list[ActionInput]] = defaultdict(list)
        for row in cursor:
            actions[row[1]].append(ActionInput(*row))
    return security_ids, formations, prices, actions, end_date, latest_decision


def build_monthly_feature_panel(*, database_url: str, destination: Path) -> dict[str, object]:
    if destination.exists() or destination.with_suffix(".json").exists():
        raise DataQualityError("refusing to overwrite immutable monthly feature panel")
    security_ids, formations, prices, actions, end_date, latest_decision = _load_core_inputs(database_url)
    resolver = PostgresSecFactResolver(database_url)
    try:
        accounting = resolver.resolve(
            security_ids=security_ids, taxonomy="us-gaap",
            concepts=(
                "Assets", "NetIncomeLoss", "ProfitLoss", "NetCashProvidedByUsedInOperatingActivities",
                "WeightedAverageNumberOfSharesOutstandingBasic",
            ),
            formation_date=end_date, decision_at=latest_decision,
        )
        shares = resolver.resolve(
            security_ids=security_ids, taxonomy="dei", concepts=("EntityCommonStockSharesOutstanding",),
            formation_date=end_date, decision_at=latest_decision,
        )
    finally:
        resolver.close()
    facts_by_security: dict[str, list[ResolvedSecFact]] = defaultdict(list)
    for item in (*accounting, *shares):
        facts_by_security[item.security_id].append(item)
    price_dates = {key: [item.session_date for item in value] for key, value in prices.items()}
    destination.parent.mkdir(parents=True, exist_ok=True)
    exclusions: dict[str, Counter[str]] = defaultdict(Counter)
    coverage: dict[str, list[int]] = defaultdict(list)
    row_count = 0
    fieldnames = ["formation_date", "decision_at", "security_id"]
    for feature in FEATURES:
        fieldnames.extend((feature, f"{feature}_lineage", f"{feature}_exclusion", f"{feature}_sha256"))
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for index, (formation_date, decision_at) in enumerate(formations, start=1):
            date_counts = Counter()
            for security_id in security_ids:
                price_end = bisect_right(price_dates.get(security_id, []), formation_date)
                eligible_prices = [
                    item for item in prices.get(security_id, ())[:price_end] if item.available_at <= decision_at
                ]
                eligible_facts = [
                    item for item in facts_by_security.get(security_id, ())
                    if item.period_end <= formation_date and item.available_at <= decision_at
                ]
                eligible_actions = [
                    item for item in actions.get(security_id, ())
                    if item.effective_date <= formation_date and item.available_at <= decision_at
                ]
                cells = {
                    "short_term_reversal_20d": short_term_reversal(eligible_prices),
                    "asset_growth_yoy": asset_growth(eligible_facts),
                    "net_share_issuance_yoy": net_share_issuance(eligible_facts, eligible_actions),
                    "accrual_quality": accrual_quality(eligible_facts),
                }
                row: dict[str, str] = {
                    "formation_date": formation_date.isoformat(),
                    "decision_at": decision_at.isoformat(),
                    "security_id": security_id,
                }
                for feature, cell in cells.items():
                    row[feature] = str(cell.value) if cell.value is not None else ""
                    row[f"{feature}_lineage"] = json.dumps(cell.lineage, separators=(",", ":"))
                    row[f"{feature}_exclusion"] = cell.exclusion or ""
                    row[f"{feature}_sha256"] = cell.digest(
                        security_id=security_id, formation_date=formation_date, feature_key=feature,
                    )
                    if cell.value is not None:
                        date_counts[feature] += 1
                    else:
                        exclusions[feature][cell.exclusion or "unknown"] += 1
                writer.writerow(row)
                row_count += 1
            for feature in FEATURES:
                coverage[feature].append(date_counts[feature])
            print(f"monthly_panel_progress={index}/{len(formations)}; formation_date={formation_date}", flush=True)
    content_hash = sha256(destination.read_bytes()).hexdigest()
    metadata: dict[str, object] = {
        "panel_key": PANEL_KEY,
        "panel_version": PANEL_VERSION,
        "feature_rule_version": FEATURE_RULE_VERSION,
        "content_sha256": content_hash,
        "cohort_code": CURRENT_SURVIVORS_COHORT,
        "data_capability_tier": "B",
        "survivorship_biased": True,
        "static_sector_point_in_time": False,
        "holdout_used": False,
        "formation_count": len(formations),
        "security_count": len(security_ids),
        "row_count": row_count,
        "start_date": formations[0][0].isoformat(),
        "end_date": formations[-1][0].isoformat(),
        "features": list(FEATURES),
        "coverage": {
            feature: {
                "available": sum(counts),
                "aggregate": str(Decimal(sum(counts)) / Decimal(row_count)),
                "minimum_monthly": str(Decimal(min(counts)) / Decimal(len(security_ids))),
            }
            for feature, counts in coverage.items()
        },
        "exclusions": {feature: dict(sorted(reasons.items())) for feature, reasons in exclusions.items()},
        "limitations": [
            "current-survivors cohort; historical membership is not point-in-time verified",
            "legacy SEC facts assume availability at acceptance plus five minutes",
            "corporate-action history is free-source Tier B",
            "current sectors may be used only as a robustness grouping",
        ],
    }
    destination.with_suffix(".json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return metadata


def _settings(env_file: Path):
    from .config import Settings

    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the immutable Phase 9B monthly feature panel")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    metadata = build_monthly_feature_panel(database_url=settings.database_url, destination=arguments.output)
    print(
        f"monthly_panel_rows={metadata['row_count']}; formations={metadata['formation_count']}; "
        f"sha256={metadata['content_sha256']}",
    )


if __name__ == "__main__":
    main()
