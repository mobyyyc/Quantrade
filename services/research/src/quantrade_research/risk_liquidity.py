"""Point-in-time risk and liquidity features from approved daily-bar inputs."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable

from .features import FeatureDefinition, FeatureRegistry, FeatureValue, baseline_feature_registry
from .momentum import (
    FeaturePriceObservation,
    SPLIT_ADJUSTED,
    eligible_split_adjusted_history,
    require_price_window,
)
from .quality import DataQualityError, assert_available_as_of


UNADJUSTED = "unadjusted"


def _as_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DataQualityError(f"{label} must include a UTC offset")
    return value.astimezone(timezone.utc)


def _definition(registry: FeatureRegistry | None, key: str) -> FeatureDefinition:
    return (registry or baseline_feature_registry()).get(key, "v1")


def calculate_trailing_volatility_60d(
    observations: Iterable[FeaturePriceObservation],
    *,
    security_id: str,
    formation_date: date,
    decision_at: datetime,
    registry: FeatureRegistry | None = None,
) -> FeatureValue:
    """Annualize the sample deviation of 60 split-adjusted daily log returns."""
    definition = _definition(registry, "trailing_volatility_60d")
    if definition.required_inputs != ("daily_price_bars:split_adjusted",):
        raise DataQualityError("trailing_volatility_60d@v1 does not have the approved price input")
    prices = require_price_window(
        eligible_split_adjusted_history(
            observations,
            security_id=security_id,
            formation_date=formation_date,
            decision_at=decision_at,
        ),
        61,
        "trailing_volatility_60d",
    )
    returns = [
        (current.close_price / previous.close_price).ln()
        for previous, current in zip(prices, prices[1:])
    ]
    mean = sum(returns, Decimal("0")) / Decimal(len(returns))
    variance = sum((value - mean) ** 2 for value in returns) / Decimal(len(returns) - 1)
    value = variance.sqrt() * Decimal("252").sqrt()
    return FeatureValue(
        security_id=security_id,
        formation_date=formation_date,
        feature_key=definition.key,
        feature_version=definition.version,
        definition_hash=definition.definition_hash,
        value=value,
    )


def _unadjusted_history(
    observations: Iterable[FeaturePriceObservation],
    *,
    security_id: str,
    formation_date: date,
    decision_at: datetime,
) -> list[FeaturePriceObservation]:
    decision = _as_utc(decision_at, "decision_at")
    selected = [
        observation
        for observation in observations
        if observation.security_id == security_id
        and observation.adjustment_basis == UNADJUSTED
        and observation.session_date <= formation_date
    ]
    assert_available_as_of(selected, decision, "unadjusted price history")
    by_date: dict[date, FeaturePriceObservation] = {}
    for observation in selected:
        if observation.session_date in by_date:
            raise DataQualityError(
                f"duplicate unadjusted price observation for {security_id} on {observation.session_date}"
            )
        if observation.close_price < 0:
            raise DataQualityError(
                f"negative unadjusted close for {security_id} on {observation.session_date}"
            )
        if observation.volume is None or observation.volume < 0:
            raise DataQualityError(
                f"missing or negative volume for {security_id} on {observation.session_date}"
            )
        by_date[observation.session_date] = observation
    ordered = [by_date[session] for session in sorted(by_date)]
    if not ordered or ordered[-1].session_date != formation_date:
        raise DataQualityError(
            f"{security_id} has no unadjusted close for formation date {formation_date}"
        )
    return ordered


def calculate_median_dollar_volume_20d(
    observations: Iterable[FeaturePriceObservation],
    *,
    security_id: str,
    formation_date: date,
    decision_at: datetime,
    registry: FeatureRegistry | None = None,
) -> FeatureValue:
    """Calculate the median of unadjusted close times volume over 20 sessions."""
    definition = _definition(registry, "median_dollar_volume_20d")
    if definition.required_inputs != ("daily_price_bars:unadjusted",):
        raise DataQualityError("median_dollar_volume_20d@v1 does not have the approved price input")
    history = _unadjusted_history(
        observations,
        security_id=security_id,
        formation_date=formation_date,
        decision_at=decision_at,
    )
    if len(history) < 20:
        raise DataQualityError("median_dollar_volume_20d requires 20 completed unadjusted sessions")
    values = sorted(item.close_price * item.volume for item in history[-20:] if item.volume is not None)
    value = (values[9] + values[10]) / Decimal("2")
    return FeatureValue(
        security_id=security_id,
        formation_date=formation_date,
        feature_key=definition.key,
        feature_version=definition.version,
        definition_hash=definition.definition_hash,
        value=value,
    )
