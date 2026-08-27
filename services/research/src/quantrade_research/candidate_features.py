"""Point-in-time calculations for the isolated Phase 9 free-data candidates."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable

from .features import FeatureDefinition, FeatureRegistry, FeatureValue, next_generation_candidate_registry
from .fundamentals import (
    ANNUAL_MAX_DAYS,
    ANNUAL_MIN_DAYS,
    ASSET_PERIOD_ALIGNMENT_TOLERANCE_DAYS,
    FundamentalFactObservation,
    NET_INCOME_CONCEPTS,
)
from .momentum import FeaturePriceObservation, eligible_split_adjusted_history, require_price_window
from .quality import DataQualityError, assert_available_as_of
from .risk_liquidity import eligible_unadjusted_history


ANNUAL_PERIOD_GAP_MIN_DAYS = 330
ANNUAL_PERIOD_GAP_MAX_DAYS = 400


def _definition(registry: FeatureRegistry | None, key: str) -> FeatureDefinition:
    return (registry or next_generation_candidate_registry()).get(key, "v1")


def _value(
    definition: FeatureDefinition,
    *,
    security_id: str,
    formation_date: date,
    value: Decimal,
) -> FeatureValue:
    return FeatureValue(
        security_id=security_id,
        formation_date=formation_date,
        feature_key=definition.key,
        feature_version=definition.version,
        definition_hash=definition.definition_hash,
        value=value,
    )


def calculate_short_term_reversal_20d(
    observations: Iterable[FeaturePriceObservation],
    *,
    security_id: str,
    formation_date: date,
    decision_at: datetime,
    registry: FeatureRegistry | None = None,
) -> FeatureValue:
    definition = _definition(registry, "short_term_reversal_20d")
    prices = require_price_window(
        eligible_split_adjusted_history(
            observations,
            security_id=security_id,
            formation_date=formation_date,
            decision_at=decision_at,
        ),
        21,
        "short_term_reversal_20d",
    )
    return _value(
        definition,
        security_id=security_id,
        formation_date=formation_date,
        value=prices[-1].close_price / prices[0].close_price - Decimal("1"),
    )


def calculate_downside_volatility_60d(
    observations: Iterable[FeaturePriceObservation],
    *,
    security_id: str,
    formation_date: date,
    decision_at: datetime,
    registry: FeatureRegistry | None = None,
) -> FeatureValue:
    definition = _definition(registry, "downside_volatility_60d")
    prices = require_price_window(
        eligible_split_adjusted_history(
            observations,
            security_id=security_id,
            formation_date=formation_date,
            decision_at=decision_at,
        ),
        61,
        "downside_volatility_60d",
    )
    returns = [
        (current.close_price / previous.close_price).ln()
        for previous, current in zip(prices, prices[1:])
    ]
    downside_squares = [min(value, Decimal("0")) ** 2 for value in returns]
    result = (sum(downside_squares, Decimal("0")) / Decimal(len(returns)) * Decimal("252")).sqrt()
    return _value(
        definition,
        security_id=security_id,
        formation_date=formation_date,
        value=result,
    )


def calculate_amihud_illiquidity_20d(
    observations: Iterable[FeaturePriceObservation],
    *,
    security_id: str,
    formation_date: date,
    decision_at: datetime,
    registry: FeatureRegistry | None = None,
) -> FeatureValue:
    definition = _definition(registry, "amihud_illiquidity_20d")
    supplied = list(observations)
    adjusted = require_price_window(
        eligible_split_adjusted_history(
            supplied,
            security_id=security_id,
            formation_date=formation_date,
            decision_at=decision_at,
        ),
        21,
        "amihud_illiquidity_20d split-adjusted history",
    )
    unadjusted = {
        item.session_date: item
        for item in eligible_unadjusted_history(
            supplied,
            security_id=security_id,
            formation_date=formation_date,
            decision_at=decision_at,
        )
    }
    values: list[Decimal] = []
    for previous, current in zip(adjusted, adjusted[1:]):
        raw = unadjusted.get(current.session_date)
        if raw is None:
            raise DataQualityError("amihud_illiquidity_20d requires matching adjusted and unadjusted sessions")
        assert raw.volume is not None  # validated by eligible_unadjusted_history
        dollar_volume = raw.close_price * raw.volume
        if dollar_volume <= 0:
            raise DataQualityError("amihud_illiquidity_20d requires positive dollar volume")
        simple_return = current.close_price / previous.close_price - Decimal("1")
        values.append(abs(simple_return) / dollar_volume)
    return _value(
        definition,
        security_id=security_id,
        formation_date=formation_date,
        value=sum(values, Decimal("0")) / Decimal(len(values)),
    )


def _as_utc(value: datetime, label: str = "fact available_at") -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DataQualityError(f"{label} must include a UTC offset")
    return value.astimezone(timezone.utc)


def _latest_fact(facts: Iterable[FundamentalFactObservation], label: str) -> FundamentalFactObservation:
    candidates = list(facts)
    if not candidates:
        raise DataQualityError(f"missing {label}")
    return max(candidates, key=lambda fact: (fact.period_end, _as_utc(fact.available_at), fact.filing_id))


def _annual_income_history(
    facts: list[FundamentalFactObservation],
) -> list[FundamentalFactObservation]:
    by_period: dict[date, FundamentalFactObservation] = {}
    concept_priority = {concept: index for index, concept in enumerate(reversed(NET_INCOME_CONCEPTS))}
    for fact in facts:
        if (
            fact.taxonomy != "us-gaap"
            or fact.concept not in NET_INCOME_CONCEPTS
            or fact.unit != "USD"
            or fact.period_start is None
            or not ANNUAL_MIN_DAYS <= (fact.period_end - fact.period_start).days <= ANNUAL_MAX_DAYS
        ):
            continue
        existing = by_period.get(fact.period_end)
        candidate_key = (concept_priority[fact.concept], _as_utc(fact.available_at), fact.filing_id)
        existing_key = (
            concept_priority[existing.concept], _as_utc(existing.available_at), existing.filing_id
        ) if existing else None
        if existing_key is None or candidate_key > existing_key:
            by_period[fact.period_end] = fact
    return [by_period[period_end] for period_end in sorted(by_period)]


def _annual_roa(
    income: FundamentalFactObservation,
    assets: list[FundamentalFactObservation],
) -> Decimal:
    assert income.period_start is not None
    beginning = _latest_fact(
        (
            fact for fact in assets
            if 0 <= (income.period_start - fact.period_end).days <= ASSET_PERIOD_ALIGNMENT_TOLERANCE_DAYS
        ),
        f"assets at {income.period_start}",
    )
    ending = _latest_fact(
        (fact for fact in assets if fact.period_end == income.period_end),
        f"assets at {income.period_end}",
    )
    if beginning.value <= 0 or ending.value <= 0:
        raise DataQualityError("total assets must be positive")
    return income.value / ((beginning.value + ending.value) / Decimal("2"))


def calculate_return_on_assets_change_yoy(
    observations: Iterable[FundamentalFactObservation],
    *,
    security_id: str,
    formation_date: date,
    decision_at: datetime,
    registry: FeatureRegistry | None = None,
) -> FeatureValue:
    definition = _definition(registry, "return_on_assets_change_yoy")
    eligible = [
        fact for fact in observations
        if fact.security_id == security_id
        and fact.period_end <= formation_date
        and fact.taxonomy == "us-gaap"
        and fact.unit == "USD"
        and (fact.concept in NET_INCOME_CONCEPTS or fact.concept == "Assets")
    ]
    assert_available_as_of(eligible, _as_utc(decision_at, "decision_at"), "fundamental-change facts")
    income_history = _annual_income_history(eligible)
    if len(income_history) < 2:
        raise DataQualityError("return_on_assets_change_yoy requires two eligible annual periods")
    assets = [
        fact for fact in eligible
        if fact.taxonomy == "us-gaap" and fact.concept == "Assets" and fact.unit == "USD"
    ]
    previous, latest = income_history[-2:]
    period_gap = (latest.period_end - previous.period_end).days
    if not ANNUAL_PERIOD_GAP_MIN_DAYS <= period_gap <= ANNUAL_PERIOD_GAP_MAX_DAYS:
        raise DataQualityError("return_on_assets_change_yoy requires consecutive annual periods")
    result = _annual_roa(latest, assets) - _annual_roa(previous, assets)
    return _value(
        definition,
        security_id=security_id,
        formation_date=formation_date,
        value=result,
    )
