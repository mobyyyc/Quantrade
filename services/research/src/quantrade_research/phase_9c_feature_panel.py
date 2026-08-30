"""Materialize the frozen, lineage-bearing Phase 9C weekly feature panel."""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import csv
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .historical_cohorts import CURRENT_SURVIVORS_COHORT
from .quality import DataQualityError
from .quarterly_accounting import AccountingValue, endpoint_shares, latest_endpoint, true_ttm
from .score_run import _dotenv_values
from .sec_fact_resolver import PostgresSecFactResolver, ResolvedSecFact
from .phase_9c_features import (
    ACCOUNTING_FAMILIES, FAMILY_KEYS, FAMILY_MEMBERS, FEATURE_RULE_VERSION,
    MARKET_FAMILIES, MAX_ACCOUNTING_STALENESS_DAYS, RAW_FEATURE_KEYS, RAW_FEATURE_SPECS,
    FamilyCell, PriceBar, RankedFeatureCell, RawFeatureCell,
    centered_cross_sectional_ranks, compose_families, market_feature_cells, missing,
)


PANEL_KEY = "phase_9c_weekly_feature_panel"
PANEL_VERSION = "v1"
DEFAULT_START = date(2022, 1, 7)
DEFAULT_END = date(2025, 6, 30)
PRICE_START = date(2020, 12, 1)
FACT_START = date(2020, 1, 1)
TORONTO = ZoneInfo("America/Toronto")
STRUCTURAL_ACTIONS = frozenset({
    "cash_merger", "spin_off", "stock_and_cash_merger", "stock_merger",
    "stock_dividend", "rights_distribution", "redemption", "reorganization",
    "worthless_removal", "partial_call",
})
SPLIT_ACTIONS = frozenset({"forward_split", "reverse_split", "unit_split"})
US_GAAP_CONCEPTS = (
    "NetIncomeLoss", "ProfitLoss", "NetCashProvidedByUsedInOperatingActivities",
    "Assets", "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
)
DEI_CONCEPTS = ("EntityCommonStockSharesOutstanding",)


@dataclass(frozen=True, slots=True)
class CorporateAction:
    action_id: str
    security_id: str
    action_type: str
    effective_date: date | None
    process_date: date
    numerator: Decimal | None
    denominator: Decimal | None
    available_at: datetime
    source_reference: str

    @property
    def event_date(self) -> date:
        return self.effective_date or self.process_date


@dataclass(frozen=True, slots=True)
class AccountingSnapshot:
    net_income: AccountingValue
    operating_cash_flow: AccountingValue
    assets: AccountingValue
    prior_assets: AccountingValue
    equity: AccountingValue
    shares: AccountingValue
    prior_shares: AccountingValue


@dataclass(slots=True)
class CorrelationAccumulator:
    count: int = 0
    sum_x: float = 0.0
    sum_y: float = 0.0
    sum_xx: float = 0.0
    sum_yy: float = 0.0
    sum_xy: float = 0.0

    def add(self, x: Decimal, y: Decimal) -> None:
        left, right = float(x), float(y)
        self.count += 1
        self.sum_x += left
        self.sum_y += right
        self.sum_xx += left * left
        self.sum_yy += right * right
        self.sum_xy += left * right

    def correlation(self) -> float | None:
        if self.count < 3:
            return None
        numerator = self.count * self.sum_xy - self.sum_x * self.sum_y
        left = self.count * self.sum_xx - self.sum_x * self.sum_x
        right = self.count * self.sum_yy - self.sum_y * self.sum_y
        if left <= 0 or right <= 0:
            return None
        return numerator / math.sqrt(left * right)


def _decision_at(formation: date) -> datetime:
    return datetime.combine(formation, time(20, 0), tzinfo=TORONTO)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_context(database_url: str, *, start: date, end: date):
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
            """SELECT session_date FROM quantrade.benchmark_daily_price_bars
                WHERE benchmark_ticker='SPY' AND session='regular'
                  AND adjustment_basis='split_adjusted' AND session_date BETWEEN %s AND %s
                ORDER BY session_date""",
            (start, end),
        )
        weeks: dict[tuple[int, int], date] = {}
        for (session,) in cursor:
            year, week, _ = session.isocalendar()
            weeks[(year, week)] = session
        formations = tuple(sorted(weeks.values()))
        if len(security_ids) != 500 or not formations:
            raise DataQualityError("Phase 9C panel requires 500 securities and non-empty weekly formations")
        latest_decision = _decision_at(formations[-1])
        cursor.execute(
            """SELECT daily_price_bar_id::text,security_id::text,session_date,close_price,
                      available_at,adjustment_basis
                 FROM quantrade.daily_price_bars
                WHERE security_id=ANY(%s::uuid[]) AND session='regular'
                  AND adjustment_basis=ANY(ARRAY['split_adjusted','unadjusted'])
                  AND session_date BETWEEN %s AND %s AND available_at<=%s
                ORDER BY security_id,adjustment_basis,session_date""",
            (list(security_ids), PRICE_START, formations[-1], latest_decision),
        )
        prices: dict[tuple[str, str], list[PriceBar]] = defaultdict(list)
        for row in cursor:
            prices[(str(row[1]), str(row[5]))].append(PriceBar(*row))
        cursor.execute(
            """SELECT concat_ws('|',benchmark_ticker,session_date::text,adjustment_basis),
                      benchmark_ticker,session_date,close_price,available_at,adjustment_basis
                 FROM quantrade.benchmark_daily_price_bars
                WHERE benchmark_ticker='SPY' AND session='regular' AND adjustment_basis='split_adjusted'
                  AND session_date BETWEEN %s AND %s AND available_at<=%s ORDER BY session_date""",
            (PRICE_START, formations[-1], latest_decision),
        )
        benchmark = tuple(PriceBar(*row) for row in cursor)
        cursor.execute(
            """SELECT corporate_action_id::text,security_id::text,action_type,effective_date,process_date,
                      ratio_numerator,ratio_denominator,available_at,source_reference
                 FROM quantrade.corporate_actions
                WHERE security_id=ANY(%s::uuid[]) AND COALESCE(effective_date,process_date)<=%s
                  AND available_at<=%s
                ORDER BY security_id,available_at,corporate_action_id""",
            (list(security_ids), formations[-1], latest_decision),
        )
        actions: dict[str, list[CorporateAction]] = defaultdict(list)
        for row in cursor:
            actions[str(row[1])].append(CorporateAction(*row))
    return security_ids, formations, prices, benchmark, actions


def _load_sec_facts(
    database_url: str, security_ids: Sequence[str], formations: Sequence[date],
) -> dict[str, tuple[ResolvedSecFact, ...]]:
    resolver = PostgresSecFactResolver(database_url)
    try:
        latest, decision = formations[-1], _decision_at(formations[-1])
        facts = (
            *resolver.load_candidates(
                security_ids=security_ids, taxonomy="us-gaap", concepts=US_GAAP_CONCEPTS,
                earliest_period_end=FACT_START, formation_date=latest, decision_at=decision,
            ),
            *resolver.load_candidates(
                security_ids=security_ids, taxonomy="dei", concepts=DEI_CONCEPTS,
                earliest_period_end=FACT_START, formation_date=latest, decision_at=decision,
            ),
        )
    finally:
        resolver.close()
    grouped: dict[str, list[ResolvedSecFact]] = defaultdict(list)
    for fact in facts:
        grouped[fact.security_id].append(fact)
    return {
        security_id: tuple(sorted(items, key=lambda item: (_fact_eligibility(item), item.lineage_key)))
        for security_id, items in grouped.items()
    }


def _fact_eligibility(fact: ResolvedSecFact) -> datetime:
    return max(fact.available_at, datetime.combine(fact.period_end, time.min, tzinfo=TORONTO))


def _fact_selection_key(fact: ResolvedSecFact) -> tuple[datetime, datetime, str]:
    return (
        fact.available_at,
        fact.observed_at or datetime.min.replace(tzinfo=timezone.utc),
        fact.lineage_key,
    )


def _comparable_prior(
    facts: Sequence[ResolvedSecFact], current: AccountingValue, *, concepts: Sequence[str],
    taxonomy: str, unit: str, require_positive: bool,
) -> AccountingValue:
    if not current.available or current.period_end is None:
        return AccountingValue(None, None, None, None, None, "comparable_prior", (), "missing_current_endpoint")
    candidates = [
        item for item in facts
        if 330 <= (current.period_end - item.period_end).days <= 400
    ]
    if not candidates:
        return AccountingValue(None, None, None, None, None, "comparable_prior", (), "missing_comparable_prior_endpoint")
    return latest_endpoint(
        candidates, concepts=concepts, taxonomy=taxonomy, unit=unit,
        formation_date=max(item.period_end for item in candidates), require_positive=require_positive,
    )


def _accounting_snapshot(facts: Sequence[ResolvedSecFact], formation: date) -> AccountingSnapshot:
    net_income = true_ttm(facts, concepts=("NetIncomeLoss", "ProfitLoss"), formation_date=formation)
    cash_flow = true_ttm(
        facts, concepts=("NetCashProvidedByUsedInOperatingActivities",), formation_date=formation,
    )
    assets = latest_endpoint(
        facts, concepts=("Assets",), taxonomy="us-gaap", unit="USD",
        formation_date=formation, require_positive=True,
    )
    equity = latest_endpoint(
        facts,
        concepts=("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
        taxonomy="us-gaap", unit="USD", formation_date=formation,
    )
    shares = endpoint_shares(facts, formation_date=formation)
    return AccountingSnapshot(
        net_income, cash_flow, assets,
        _comparable_prior(
            facts, assets, concepts=("Assets",), taxonomy="us-gaap", unit="USD", require_positive=True,
        ),
        equity, shares,
        _comparable_prior(
            facts, shares, concepts=("EntityCommonStockSharesOutstanding",),
            taxonomy="dei", unit="shares", require_positive=True,
        ),
    )


def _accounting_token(value: AccountingValue, catalog: dict[str, dict[str, object]]) -> str:
    token = f"accounting:{value.digest()}"
    catalog.setdefault(token, {
        "value": str(value.value) if value.value is not None else None,
        "unit": value.unit,
        "period_start": value.period_start.isoformat() if value.period_start else None,
        "period_end": value.period_end.isoformat() if value.period_end else None,
        "concept": value.concept,
        "operation": value.operation,
        "rule_version": value.rule_version,
        "exclusion": value.exclusion,
        "selected_facts": [asdict(item) for item in value.lineage],
    })
    return token


def _stale(value: AccountingValue, formation: date) -> bool:
    return bool(
        value.available and value.period_end
        and (formation - value.period_end).days > MAX_ACCOUNTING_STALENESS_DAYS
    )


def _usable(
    value: AccountingValue, formation: date, *, label: str,
) -> str | None:
    if not value.available:
        return f"{label}:{value.exclusion or 'unavailable'}"
    if _stale(value, formation):
        return f"{label}:stale_over_{MAX_ACCOUNTING_STALENESS_DAYS}d"
    return None


def _available_comparator(value: AccountingValue, *, label: str) -> str | None:
    if not value.available:
        return f"{label}:{value.exclusion or 'unavailable'}"
    return None


def _action_adjustment(
    actions: Iterable[CorporateAction], *, start: date, end: date, decision: datetime,
) -> tuple[Decimal | None, tuple[str, ...], str | None]:
    relevant = tuple(
        item for item in actions
        if start < item.event_date <= end and item.available_at <= decision
    )
    structural = tuple(item for item in relevant if item.action_type in STRUCTURAL_ACTIONS)
    if structural:
        return None, tuple(f"action:{item.action_id}" for item in structural), "structural_corporate_action"
    factor = Decimal("1")
    lineage: list[str] = []
    for item in relevant:
        if item.action_type not in SPLIT_ACTIONS:
            continue
        lineage.append(f"action:{item.action_id}")
        if item.numerator is None or item.denominator is None or item.numerator <= 0 or item.denominator <= 0:
            return None, tuple(lineage), "invalid_split_ratio"
        factor *= item.numerator / item.denominator
    return factor, tuple(lineage), None


def _accounting_feature_cells(
    snapshot: AccountingSnapshot, *, formation: date, raw_close: PriceBar | None,
    actions: Sequence[CorporateAction], catalog: dict[str, dict[str, object]],
) -> dict[str, RawFeatureCell]:
    keys = (
        "book_to_market", "earnings_yield_ttm", "operating_cash_flow_yield_ttm",
        "return_on_assets_ttm", "operating_cash_flow_profitability_ttm",
        "accrual_quality_ttm", "asset_growth_yoy", "net_share_issuance_yoy",
    )
    result = {key: missing("accounting_inputs_unavailable") for key in keys}
    decision = _decision_at(formation)
    if raw_close is None or raw_close.close_price <= 0 or raw_close.available_at > decision:
        market_cap_reason = "missing_positive_unadjusted_formation_close"
        market_cap = None
        market_lineage: tuple[str, ...] = ()
    else:
        shares_reason = _usable(snapshot.shares, formation, label="shares")
        if shares_reason:
            market_cap_reason = shares_reason
            market_cap = None
            market_lineage = ()
        else:
            assert snapshot.shares.value is not None
            market_cap = raw_close.close_price * snapshot.shares.value
            market_cap_reason = None if market_cap > 0 else "nonpositive_market_cap"
            market_lineage = (
                f"price:{raw_close.lineage_id}", _accounting_token(snapshot.shares, catalog),
            )

    if market_cap is not None and market_cap_reason is None:
        for feature_key, value, label in (
            ("book_to_market", snapshot.equity, "equity"),
            ("earnings_yield_ttm", snapshot.net_income, "net_income_ttm"),
            ("operating_cash_flow_yield_ttm", snapshot.operating_cash_flow, "operating_cash_flow_ttm"),
        ):
            reason = _usable(value, formation, label=label)
            if reason is None:
                assert value.value is not None
                result[feature_key] = RawFeatureCell(
                    value.value / market_cap,
                    (*market_lineage, _accounting_token(value, catalog)),
                )
            else:
                result[feature_key] = missing(reason)
    else:
        for feature_key in ("book_to_market", "earnings_yield_ttm", "operating_cash_flow_yield_ttm"):
            result[feature_key] = missing(market_cap_reason or "market_cap_unavailable")

    assets_reason = _usable(snapshot.assets, formation, label="assets")
    prior_assets_reason = _available_comparator(snapshot.prior_assets, label="prior_assets")
    if assets_reason is None and prior_assets_reason is None:
        assert snapshot.assets.value is not None and snapshot.prior_assets.value is not None
        average_assets = (snapshot.assets.value + snapshot.prior_assets.value) / Decimal("2")
        asset_lineage = (
            _accounting_token(snapshot.prior_assets, catalog),
            _accounting_token(snapshot.assets, catalog),
        )
        if average_assets > 0:
            for feature_key, value, label in (
                ("return_on_assets_ttm", snapshot.net_income, "net_income_ttm"),
                ("operating_cash_flow_profitability_ttm", snapshot.operating_cash_flow, "operating_cash_flow_ttm"),
            ):
                reason = _usable(value, formation, label=label)
                if reason is None:
                    assert value.value is not None
                    result[feature_key] = RawFeatureCell(
                        value.value / average_assets,
                        (*asset_lineage, _accounting_token(value, catalog)),
                    )
                else:
                    result[feature_key] = missing(reason)
            income_reason = _usable(snapshot.net_income, formation, label="net_income_ttm")
            cash_reason = _usable(snapshot.operating_cash_flow, formation, label="operating_cash_flow_ttm")
            aligned = (
                snapshot.net_income.period_end is not None
                and snapshot.operating_cash_flow.period_end is not None
                and abs((snapshot.net_income.period_end - snapshot.operating_cash_flow.period_end).days) <= 7
            )
            if income_reason is None and cash_reason is None and aligned:
                assert snapshot.net_income.value is not None and snapshot.operating_cash_flow.value is not None
                result["accrual_quality_ttm"] = RawFeatureCell(
                    (snapshot.net_income.value - snapshot.operating_cash_flow.value) / average_assets,
                    (*asset_lineage, _accounting_token(snapshot.net_income, catalog),
                     _accounting_token(snapshot.operating_cash_flow, catalog)),
                )
            else:
                result["accrual_quality_ttm"] = missing(
                    income_reason or cash_reason or "misaligned_ttm_periods"
                )
            result["asset_growth_yoy"] = RawFeatureCell(
                snapshot.assets.value / snapshot.prior_assets.value - Decimal("1"), asset_lineage,
            )
        else:
            for feature_key in (
                "return_on_assets_ttm", "operating_cash_flow_profitability_ttm",
                "accrual_quality_ttm", "asset_growth_yoy",
            ):
                result[feature_key] = missing("nonpositive_average_assets")
    else:
        reason = assets_reason or prior_assets_reason or "asset_endpoints_unavailable"
        for feature_key in (
            "return_on_assets_ttm", "operating_cash_flow_profitability_ttm",
            "accrual_quality_ttm", "asset_growth_yoy",
        ):
            result[feature_key] = missing(reason)

    shares_reason = _usable(snapshot.shares, formation, label="shares")
    prior_shares_reason = _available_comparator(snapshot.prior_shares, label="prior_shares")
    if shares_reason is None and prior_shares_reason is None:
        assert snapshot.shares.value is not None and snapshot.prior_shares.value is not None
        assert snapshot.shares.period_end is not None and snapshot.prior_shares.period_end is not None
        factor, action_lineage, action_reason = _action_adjustment(
            actions, start=snapshot.prior_shares.period_end, end=snapshot.shares.period_end, decision=decision,
        )
        if factor is not None and action_reason is None:
            denominator = snapshot.prior_shares.value * factor
            if denominator > 0:
                result["net_share_issuance_yoy"] = RawFeatureCell(
                    snapshot.shares.value / denominator - Decimal("1"),
                    (_accounting_token(snapshot.prior_shares, catalog), *action_lineage,
                     _accounting_token(snapshot.shares, catalog)),
                )
            else:
                result["net_share_issuance_yoy"] = missing("nonpositive_split_adjusted_prior_shares")
        else:
            result["net_share_issuance_yoy"] = RawFeatureCell(None, action_lineage, action_reason)
    else:
        result["net_share_issuance_yoy"] = missing(
            shares_reason or prior_shares_reason or "share_endpoints_unavailable"
        )
    return result


def _history_as_of(
    bars: Sequence[PriceBar], formation: date, decision: datetime,
) -> tuple[PriceBar, ...]:
    end = bisect_right(bars, formation, key=lambda item: item.session_date)
    return tuple(item for item in bars[:end] if item.available_at <= decision)


def _formation_rows(
    *, formation: date, security_ids: Sequence[str], prices: Mapping[tuple[str, str], Sequence[PriceBar]],
    benchmark: Sequence[PriceBar], accounting: Mapping[str, AccountingSnapshot],
    actions: Mapping[str, Sequence[CorporateAction]], catalog: dict[str, dict[str, object]],
) -> tuple[dict[str, dict[str, RawFeatureCell]], dict[str, dict[str, RankedFeatureCell]], dict[str, dict[str, FamilyCell]]]:
    decision = _decision_at(formation)
    benchmark_history = _history_as_of(benchmark, formation, decision)
    raw_by_security: dict[str, dict[str, RawFeatureCell]] = {}
    for security_id in security_ids:
        split_history = _history_as_of(prices.get((security_id, "split_adjusted"), ()), formation, decision)
        unadjusted_history = _history_as_of(prices.get((security_id, "unadjusted"), ()), formation, decision)
        raw_close = unadjusted_history[-1] if unadjusted_history and unadjusted_history[-1].session_date == formation else None
        cells = market_feature_cells(split_history, benchmark_history, formation_date=formation)
        cells.update(_accounting_feature_cells(
            accounting[security_id], formation=formation, raw_close=raw_close,
            actions=actions.get(security_id, ()), catalog=catalog,
        ))
        if set(cells) != set(RAW_FEATURE_KEYS):
            raise DataQualityError("Phase 9C raw feature construction is incomplete")
        raw_by_security[security_id] = cells
    ranked_by_security: dict[str, dict[str, RankedFeatureCell]] = {
        security_id: {} for security_id in security_ids
    }
    for spec in RAW_FEATURE_SPECS:
        cross_section = centered_cross_sectional_ranks(
            {security_id: raw_by_security[security_id][spec.key] for security_id in security_ids},
            direction=spec.direction,
        )
        for security_id, cell in cross_section.items():
            ranked_by_security[security_id][spec.key] = cell
    families = {
        security_id: compose_families(ranked_by_security[security_id])
        for security_id in security_ids
    }
    return raw_by_security, ranked_by_security, families


def _formation_digest(
    security_ids: Sequence[str], raw: Mapping[str, Mapping[str, RawFeatureCell]],
    ranked: Mapping[str, Mapping[str, RankedFeatureCell]],
    families: Mapping[str, Mapping[str, FamilyCell]],
) -> str:
    rows: list[str] = []
    for security_id in security_ids:
        payload = {
            "security_id": security_id,
            "raw": {
                key: {
                    "digest": raw[security_id][key].digest(key),
                    "rank": str(ranked[security_id][key].centered_rank),
                }
                for key in RAW_FEATURE_KEYS
            },
            "families": {
                key: {
                    "value": str(families[security_id][key].value),
                    "availability": str(families[security_id][key].availability),
                    "informative": families[security_id][key].informative,
                }
                for key in FAMILY_KEYS
            },
        }
        rows.append(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return sha256("\n".join(rows).encode()).hexdigest()


def _fieldnames() -> list[str]:
    fields = [
        "security_id", "formation_date", "decision_at", "calendar_month",
        "formation_weight", "score_eligible", "informative_family_count",
    ]
    for key in RAW_FEATURE_KEYS:
        fields.extend((
            f"{key}_raw", f"{key}_centered_rank", f"{key}_available",
            f"{key}_exclusion",
        ))
    for family in FAMILY_KEYS:
        fields.extend((
            f"{family}_value", f"{family}_availability",
            f"{family}_informative", f"{family}_available_feature_count",
        ))
    fields.append("row_hash")
    return fields


def _row_hash(row: Mapping[str, object]) -> str:
    payload = {key: row[key] for key in sorted(row) if key != "row_hash"}
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_panel(
    database_url: str, *, start: date, end: date, destination: Path,
) -> dict[str, object]:
    panel_base = destination.with_suffix("") if destination.suffix == ".gz" else destination
    metadata_path = panel_base.with_suffix(".json")
    lineage_path = panel_base.with_suffix(".lineage.tsv.gz")
    for path in (destination, metadata_path, lineage_path):
        if path.exists():
            raise DataQualityError(f"refusing to overwrite immutable Phase 9C artifact: {path}")
    security_ids, formations, prices, benchmark, actions = _load_context(
        database_url, start=start, end=end,
    )
    facts = _load_sec_facts(database_url, security_ids, formations)
    formation_counts = Counter((item.year, item.month) for item in formations)
    fact_positions = {security_id: 0 for security_id in security_ids}
    fact_state: dict[str, dict[str, ResolvedSecFact]] = {security_id: {} for security_id in security_ids}
    accounting_cache: dict[str, AccountingSnapshot] = {}
    accounting_catalog: dict[str, dict[str, object]] = {}
    written_catalog: set[str] = set()
    raw_available = Counter()
    family_informative = Counter()
    raw_minimum = {key: 1.0 for key in RAW_FEATURE_KEYS}
    family_minimum = {key: 1.0 for key in FAMILY_KEYS}
    score_eligible_total = 0
    score_minimum = 1.0
    exclusions: dict[str, Counter[str]] = {key: Counter() for key in RAW_FEATURE_KEYS}
    lineage_violations = 0
    lineage_record_count = 0
    issuers_below_three = Counter()
    month_weights: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    correlations = {
        (left, right): CorrelationAccumulator()
        for index, left in enumerate(RAW_FEATURE_KEYS)
        for right in RAW_FEATURE_KEYS[index + 1:]
    }
    row_hashes: list[str] = []
    formation_hashes: list[str] = []
    last_formation_payload = None
    destination.parent.mkdir(parents=True, exist_ok=True)
    panel_context = (
        gzip.open(destination, "wt", encoding="utf-8", newline="")
        if destination.suffix == ".gz"
        else destination.open("w", encoding="utf-8", newline="")
    )
    with panel_context as panel_handle, gzip.open(lineage_path, "wt", encoding="utf-8", newline="\n") as lineage_handle:
        writer = csv.DictWriter(panel_handle, fieldnames=_fieldnames(), lineterminator="\n")
        writer.writeheader()
        lineage_handle.write("record_type\tsecurity_id\tformation_date\tfeature_or_token\tpayload\n")
        for formation_index, formation in enumerate(formations, start=1):
            decision = _decision_at(formation)
            for security_id in security_ids:
                events = facts.get(security_id, ())
                position = fact_positions[security_id]
                state = fact_state[security_id]
                changed = security_id not in accounting_cache
                while position < len(events) and _fact_eligibility(events[position]) <= decision:
                    fact = events[position]
                    current = state.get(fact.filing_fact_key)
                    if current is None or _fact_selection_key(fact) > _fact_selection_key(current):
                        state[fact.filing_fact_key] = fact
                        changed = True
                    position += 1
                fact_positions[security_id] = position
                if changed:
                    resolved = tuple(sorted(
                        state.values(), key=lambda item: (item.concept, item.period_end, item.lineage_key),
                    ))
                    accounting_cache[security_id] = _accounting_snapshot(resolved, formation)
            raw, ranked, families = _formation_rows(
                formation=formation, security_ids=security_ids, prices=prices, benchmark=benchmark,
                accounting=accounting_cache, actions=actions, catalog=accounting_catalog,
            )
            formation_digest = _formation_digest(security_ids, raw, ranked, families)
            formation_hashes.append(f"{formation.isoformat()}|{formation_digest}")
            eligible = {
                security_id: sum(item.informative for item in families[security_id].values()) >= 3
                for security_id in security_ids
            }
            eligible_count = sum(eligible.values())
            score_coverage = eligible_count / len(security_ids)
            score_minimum = min(score_minimum, score_coverage)
            score_eligible_total += eligible_count
            month_key = formation.strftime("%Y-%m")
            formation_weight = (
                Decimal("1") / Decimal(formation_counts[(formation.year, formation.month)]) / Decimal(eligible_count)
                if eligible_count else Decimal("0")
            )
            for key in RAW_FEATURE_KEYS:
                count = sum(raw[security_id][key].available for security_id in security_ids)
                raw_available[key] += count
                raw_minimum[key] = min(raw_minimum[key], count / len(security_ids))
            for family in FAMILY_KEYS:
                count = sum(families[security_id][family].informative for security_id in security_ids)
                family_informative[family] += count
                family_minimum[family] = min(family_minimum[family], count / len(security_ids))
            for security_id in security_ids:
                informative_count = sum(item.informative for item in families[security_id].values())
                if informative_count < 3:
                    issuers_below_three[security_id] += 1
                if eligible[security_id]:
                    month_weights[month_key] += formation_weight
                row: dict[str, object] = {
                    "security_id": security_id,
                    "formation_date": formation.isoformat(),
                    "decision_at": decision.isoformat(),
                    "calendar_month": month_key,
                    "formation_weight": str(formation_weight),
                    "score_eligible": str(eligible[security_id]).lower(),
                    "informative_family_count": informative_count,
                }
                for key in RAW_FEATURE_KEYS:
                    raw_cell, ranked_cell = raw[security_id][key], ranked[security_id][key]
                    row.update({
                        f"{key}_raw": str(raw_cell.value) if raw_cell.value is not None else "",
                        f"{key}_centered_rank": str(ranked_cell.centered_rank),
                        f"{key}_available": str(raw_cell.available).lower(),
                        f"{key}_exclusion": raw_cell.exclusion or "",
                    })
                    if raw_cell.available and not raw_cell.lineage:
                        lineage_violations += 1
                    if not raw_cell.available:
                        exclusions[key][raw_cell.exclusion or "unknown"] += 1
                    if raw_cell.available:
                        lineage_handle.write("\t".join((
                            "feature_cell", security_id, formation.isoformat(), key,
                            json.dumps(raw_cell.lineage, separators=(",", ":")),
                        )) + "\n")
                        lineage_record_count += 1
                for family in FAMILY_KEYS:
                    cell = families[security_id][family]
                    row.update({
                        f"{family}_value": str(cell.value),
                        f"{family}_availability": str(cell.availability),
                        f"{family}_informative": str(cell.informative).lower(),
                        f"{family}_available_feature_count": cell.available_feature_count,
                    })
                for (left, right), accumulator in correlations.items():
                    if raw[security_id][left].available and raw[security_id][right].available:
                        accumulator.add(ranked[security_id][left].centered_rank, ranked[security_id][right].centered_rank)
                row["row_hash"] = _row_hash(row)
                row_hashes.append(str(row["row_hash"]))
                writer.writerow(row)
            for token in sorted(set(accounting_catalog) - written_catalog):
                lineage_handle.write("\t".join((
                    "accounting_source", "", "", token,
                    json.dumps(accounting_catalog[token], sort_keys=True, separators=(",", ":")),
                )) + "\n")
                written_catalog.add(token)
                lineage_record_count += 1
            last_formation_payload = (raw, ranked, families)
            if formation_index == 1 or formation_index % 20 == 0 or formation_index == len(formations):
                print(
                    f"feature_panel_progress={formation_index}/{len(formations)}; "
                    f"formation={formation.isoformat()}; score_coverage={score_coverage:.4f}",
                    flush=True,
                )

    if last_formation_payload is None:
        raise DataQualityError("Phase 9C panel produced no formations")
    raw_last, ranked_last, families_last = last_formation_payload
    replay_hash_a = _formation_digest(security_ids, raw_last, ranked_last, families_last)
    replay_raw, replay_ranked, replay_families = _formation_rows(
        formation=formations[-1], security_ids=security_ids, prices=prices,
        benchmark=benchmark, accounting=accounting_cache, actions=actions,
        catalog=accounting_catalog,
    )
    replay_hash_b = _formation_digest(
        security_ids, replay_raw, replay_ranked, replay_families,
    )
    observation_count = len(formations) * len(security_ids)
    raw_aggregate = {key: raw_available[key] / observation_count for key in RAW_FEATURE_KEYS}
    family_aggregate = {key: family_informative[key] / observation_count for key in FAMILY_KEYS}
    score_aggregate = score_eligible_total / observation_count
    correlation_report = {
        f"{left}|{right}": {"count": value.count, "correlation": value.correlation()}
        for (left, right), value in correlations.items()
    }
    within_family_redundancy = {
        pair: item for pair, item in correlation_report.items()
        if any(set(pair.split("|")) <= set(members) for members in FAMILY_MEMBERS.values())
        and item["correlation"] is not None and abs(float(item["correlation"])) >= 0.95
    }
    gates = {
        "point_in_time_lineage": lineage_violations == 0,
        "deterministic_replay": replay_hash_a == replay_hash_b == formation_hashes[-1].split("|", 1)[1],
        "raw_feature_aggregate_coverage": all(value >= 0.70 for value in raw_aggregate.values()),
        "market_family_minimum_coverage": all(family_minimum[key] >= 0.90 for key in MARKET_FAMILIES),
        "accounting_family_aggregate_coverage": all(family_aggregate[key] >= 0.80 for key in ACCOUNTING_FAMILIES),
        "accounting_family_minimum_coverage": all(family_minimum[key] >= 0.70 for key in ACCOUNTING_FAMILIES),
        "score_aggregate_coverage": score_aggregate >= 0.95,
        "score_minimum_coverage": score_minimum >= 0.90,
        "minimum_three_informative_families": all(
            not eligible or sum(item.informative for item in families_last[security_id].values()) >= 3
            for security_id, eligible in {
                security_id: sum(item.informative for item in families_last[security_id].values()) >= 3
                for security_id in security_ids
            }.items()
        ),
        "calendar_month_weight": all(abs(value - Decimal("1")) <= Decimal("1e-24") for value in month_weights.values()),
        "within_family_redundancy": not within_family_redundancy,
    }
    metadata: dict[str, object] = {
        "panel_key": PANEL_KEY,
        "panel_version": PANEL_VERSION,
        "feature_rule_version": FEATURE_RULE_VERSION,
        "research_cohort": CURRENT_SURVIVORS_COHORT,
        "data_capability_tier": "B",
        "survivorship_biased": True,
        "holdout_used": False,
        "start_date": formations[0].isoformat(),
        "end_date": formations[-1].isoformat(),
        "formation_count": len(formations),
        "security_count": len(security_ids),
        "row_count": observation_count,
        "raw_feature_specs": [asdict(item) for item in RAW_FEATURE_SPECS],
        "family_members": FAMILY_MEMBERS,
        "availability_enters_model": False,
        "neutral_missing_rank": "0",
        "minimum_informative_families": 3,
        "accounting_staleness_days": MAX_ACCOUNTING_STALENESS_DAYS,
        "redundancy_threshold": 0.95,
        "raw_aggregate_coverage": raw_aggregate,
        "raw_minimum_formation_coverage": raw_minimum,
        "family_aggregate_informative_coverage": family_aggregate,
        "family_minimum_informative_coverage": family_minimum,
        "score_aggregate_coverage": score_aggregate,
        "score_minimum_coverage": score_minimum,
        "exclusions": {key: dict(sorted(value.items())) for key, value in exclusions.items()},
        "issuers_below_three_informative_families": dict(sorted(issuers_below_three.items())),
        "month_weight_sums": {key: str(value) for key, value in sorted(month_weights.items())},
        "correlations": correlation_report,
        "within_family_redundancy_failures": within_family_redundancy,
        "lineage_violations": lineage_violations,
        "lineage_record_count": lineage_record_count,
        "replay_formation": formations[-1].isoformat(),
        "replay_hash": replay_hash_a,
        "panel_hash": sha256("\n".join(row_hashes).encode()).hexdigest(),
        "formation_panel_hash": sha256("\n".join(formation_hashes).encode()).hexdigest(),
        "panel_file_sha256": _sha256_file(destination),
        "lineage_file_sha256": _sha256_file(lineage_path),
        "gates": gates,
        "passed": all(gates.values()),
        "limitations": [
            "current-survivors S&P 500 cohort; historical performance remains survivorship biased",
            "market-wide ranks; historical SIC/FF12 is not used",
            "direct gross profitability is excluded",
            "weighted-average shares are never a primary endpoint fallback",
            "availability measures are diagnostics and do not enter the v1 model",
        ],
    }
    metadata["report_hash"] = sha256(
        json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize the frozen Phase 9C weekly feature panel")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--start", type=date.fromisoformat, default=DEFAULT_START)
    parser.add_argument("--end", type=date.fromisoformat, default=DEFAULT_END)
    parser.add_argument("--output", type=Path, default=Path("data/derived/phase_9c_weekly_feature_panel_v1.csv.gz"))
    arguments = parser.parse_args()
    database_url = _dotenv_values(Path(arguments.env_file)).get("DATABASE_URL")
    if not database_url:
        raise DataQualityError("DATABASE_URL is required")
    metadata = build_panel(
        database_url, start=arguments.start, end=arguments.end, destination=arguments.output,
    )
    print(json.dumps({
        "passed": metadata["passed"],
        "row_count": metadata["row_count"],
        "raw_aggregate_coverage": metadata["raw_aggregate_coverage"],
        "family_minimum_informative_coverage": metadata["family_minimum_informative_coverage"],
        "score_aggregate_coverage": metadata["score_aggregate_coverage"],
        "score_minimum_coverage": metadata["score_minimum_coverage"],
        "report_hash": metadata["report_hash"],
    }, sort_keys=True))
    if not metadata["passed"]:
        raise DataQualityError("Phase 9C weekly feature panel failed frozen gates")


if __name__ == "__main__":
    main()
