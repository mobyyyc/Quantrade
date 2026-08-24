"""Point-in-time fundamental features defined by the approved registry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable

from .features import FeatureDefinition, FeatureRegistry, FeatureValue, baseline_feature_registry
from .momentum import FeaturePriceObservation, SPLIT_ADJUSTED
from .quality import DataQualityError, assert_available_as_of


ANNUAL_MIN_DAYS = 330
ANNUAL_MAX_DAYS = 370
ASSET_PERIOD_ALIGNMENT_TOLERANCE_DAYS = 7
FUNDAMENTAL_FEATURE_VERSION = "v2"
NET_INCOME_CONCEPTS = ("NetIncomeLoss", "ProfitLoss")


@dataclass(frozen=True, slots=True)
class FundamentalFactObservation:
    security_id: str
    filing_id: str
    taxonomy: str
    concept: str
    unit: str
    value: Decimal
    period_start: date | None
    period_end: date
    available_at: datetime


def _as_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DataQualityError(f"{label} must include a UTC offset")
    return value.astimezone(timezone.utc)


def _definition(registry: FeatureRegistry | None, key: str) -> FeatureDefinition:
    return (registry or baseline_feature_registry()).get(key, FUNDAMENTAL_FEATURE_VERSION)


def _eligible_facts(
    observations: Iterable[FundamentalFactObservation],
    *,
    security_id: str,
    formation_date: date,
    decision_at: datetime,
    taxonomy: str,
    concept: str,
    unit: str,
) -> list[FundamentalFactObservation]:
    decision = _as_utc(decision_at, "decision_at")
    selected = [
        fact
        for fact in observations
        if fact.security_id == security_id
        and fact.taxonomy == taxonomy
        and fact.concept == concept
        and fact.unit == unit
        and fact.period_end <= formation_date
    ]
    assert_available_as_of(selected, decision, f"{taxonomy}:{concept} facts")
    if not selected:
        raise DataQualityError(f"{security_id} lacks eligible {taxonomy}:{concept} facts")
    return selected


def _latest(
    facts: Iterable[FundamentalFactObservation], *, label: str
) -> FundamentalFactObservation:
    candidates = list(facts)
    if not candidates:
        raise DataQualityError(f"missing {label}")
    return max(
        candidates,
        key=lambda fact: (fact.period_end, _as_utc(fact.available_at, "fact available_at"), fact.filing_id),
    )


def _annual_net_income(
    observations: Iterable[FundamentalFactObservation],
    *,
    security_id: str,
    formation_date: date,
    decision_at: datetime,
) -> FundamentalFactObservation:
    decision = _as_utc(decision_at, "decision_at")
    for concept in NET_INCOME_CONCEPTS:
        facts = [
            fact
            for fact in observations
            if fact.security_id == security_id
            and fact.taxonomy == "us-gaap"
            and fact.concept == concept
            and fact.unit == "USD"
            and fact.period_end <= formation_date
        ]
        assert_available_as_of(facts, decision, f"us-gaap:{concept} facts")
        annual = [
            fact
            for fact in facts
            if fact.period_start is not None
            and ANNUAL_MIN_DAYS <= (fact.period_end - fact.period_start).days <= ANNUAL_MAX_DAYS
        ]
        if annual:
            return _latest(annual, label=f"eligible annual {concept} fact")
    raise DataQualityError("missing eligible annual NetIncomeLoss or ProfitLoss fact")


def _formation_close(
    observations: Iterable[FeaturePriceObservation],
    *,
    security_id: str,
    formation_date: date,
    decision_at: datetime,
) -> Decimal:
    decision = _as_utc(decision_at, "decision_at")
    selected = [
        observation
        for observation in observations
        if observation.security_id == security_id
        and observation.session_date == formation_date
        and observation.adjustment_basis == SPLIT_ADJUSTED
    ]
    assert_available_as_of(selected, decision, "formation price")
    if len(selected) != 1:
        raise DataQualityError(
            f"{security_id} requires exactly one split-adjusted close for formation date {formation_date}"
        )
    if selected[0].close_price <= 0:
        raise DataQualityError(f"{security_id} has a non-positive formation close")
    return selected[0].close_price


def calculate_earnings_yield_ttm(
    facts: Iterable[FundamentalFactObservation],
    prices: Iterable[FeaturePriceObservation],
    *,
    security_id: str,
    formation_date: date,
    decision_at: datetime,
    registry: FeatureRegistry | None = None,
) -> FeatureValue:
    """Calculate annual reported net income divided by eligible market capitalization."""
    definition = _definition(registry, "earnings_yield_ttm")
    net_income = _annual_net_income(
        facts,
        security_id=security_id,
        formation_date=formation_date,
        decision_at=decision_at,
    )
    shares = _latest(
        _eligible_facts(
            facts,
            security_id=security_id,
            formation_date=formation_date,
            decision_at=decision_at,
            taxonomy="dei",
            concept="EntityCommonStockSharesOutstanding",
            unit="shares",
        ),
        label="eligible shares outstanding fact",
    )
    if shares.value <= 0:
        raise DataQualityError("shares outstanding must be positive")
    close = _formation_close(
        prices,
        security_id=security_id,
        formation_date=formation_date,
        decision_at=decision_at,
    )
    return FeatureValue(
        security_id=security_id,
        formation_date=formation_date,
        feature_key=definition.key,
        feature_version=definition.version,
        definition_hash=definition.definition_hash,
        value=net_income.value / (close * shares.value),
    )


def calculate_return_on_assets_ttm(
    facts: Iterable[FundamentalFactObservation],
    *,
    security_id: str,
    formation_date: date,
    decision_at: datetime,
    registry: FeatureRegistry | None = None,
) -> FeatureValue:
    """Calculate reported annual net income over average endpoint total assets."""
    definition = _definition(registry, "return_on_assets_ttm")
    net_income = _annual_net_income(
        facts,
        security_id=security_id,
        formation_date=formation_date,
        decision_at=decision_at,
    )
    assert net_income.period_start is not None  # guaranteed by _annual_net_income
    assets = _eligible_facts(
        facts,
        security_id=security_id,
        formation_date=formation_date,
        decision_at=decision_at,
        taxonomy="us-gaap",
        concept="Assets",
        unit="USD",
    )
    beginning_assets = _latest(
        (
            fact
            for fact in assets
            if 0 <= (net_income.period_start - fact.period_end).days <= ASSET_PERIOD_ALIGNMENT_TOLERANCE_DAYS
        ),
        label="total assets at annual-period start",
    )
    ending_assets = _latest(
        (fact for fact in assets if fact.period_end == net_income.period_end),
        label="total assets at annual-period end",
    )
    if beginning_assets.value <= 0 or ending_assets.value <= 0:
        raise DataQualityError("total assets must be positive")
    average_assets = (beginning_assets.value + ending_assets.value) / Decimal("2")
    return FeatureValue(
        security_id=security_id,
        formation_date=formation_date,
        feature_key=definition.key,
        feature_version=definition.version,
        definition_hash=definition.definition_hash,
        value=net_income.value / average_assets,
    )
