"""Point-in-time price features defined by the approved feature registry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable

from .features import FeatureDefinition, FeatureRegistry, baseline_feature_registry
from .quality import DataQualityError, assert_available_as_of


SPLIT_ADJUSTED = "split_adjusted"


@dataclass(frozen=True, slots=True)
class FeaturePriceObservation:
    security_id: str
    session_date: date
    close_price: Decimal
    adjustment_basis: str
    available_at: datetime


@dataclass(frozen=True, slots=True)
class FeatureValue:
    security_id: str
    formation_date: date
    feature_key: str
    feature_version: str
    definition_hash: str
    value: Decimal


def _as_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DataQualityError(f"{label} must include a UTC offset")
    return value.astimezone(timezone.utc)


def _definition(registry: FeatureRegistry | None, key: str) -> FeatureDefinition:
    active_registry = registry or baseline_feature_registry()
    definition = active_registry.get(key, "v1")
    if definition.required_inputs[0] != "daily_price_bars:split_adjusted":
        raise DataQualityError(f"{key}@v1 does not have the approved split-adjusted price input")
    return definition


def _history(
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
        and observation.adjustment_basis == SPLIT_ADJUSTED
        and observation.session_date <= formation_date
    ]
    assert_available_as_of(selected, decision, "price history")
    by_date: dict[date, FeaturePriceObservation] = {}
    for observation in selected:
        if observation.session_date in by_date:
            raise DataQualityError(
                f"duplicate split-adjusted price observation for {security_id} on {observation.session_date}"
            )
        if observation.close_price <= 0:
            raise DataQualityError(
                f"non-positive split-adjusted close for {security_id} on {observation.session_date}"
            )
        by_date[observation.session_date] = observation
    ordered = [by_date[session] for session in sorted(by_date)]
    if not ordered or ordered[-1].session_date != formation_date:
        raise DataQualityError(
            f"{security_id} has no split-adjusted close for formation date {formation_date}"
        )
    return ordered


def _window(history: list[FeaturePriceObservation], size: int, label: str) -> list[FeaturePriceObservation]:
    if len(history) < size:
        raise DataQualityError(f"{label} requires {size} completed split-adjusted sessions")
    return history[-size:]


def calculate_momentum_12_1(
    observations: Iterable[FeaturePriceObservation],
    *,
    security_id: str,
    formation_date: date,
    decision_at: datetime,
    registry: FeatureRegistry | None = None,
) -> FeatureValue:
    """Calculate C(t-21) / C(t-252) - 1 from an eligible 253-session window."""
    definition = _definition(registry, "momentum_12_1")
    history = _window(
        _history(
            observations,
            security_id=security_id,
            formation_date=formation_date,
            decision_at=decision_at,
        ),
        253,
        "momentum_12_1",
    )
    value = history[-22].close_price / history[0].close_price - Decimal("1")
    return FeatureValue(
        security_id=security_id,
        formation_date=formation_date,
        feature_key=definition.key,
        feature_version=definition.version,
        definition_hash=definition.definition_hash,
        value=value,
    )


def calculate_relative_strength_6m(
    security_observations: Iterable[FeaturePriceObservation],
    benchmark_observations: Iterable[FeaturePriceObservation],
    *,
    security_id: str,
    benchmark_security_id: str,
    formation_date: date,
    decision_at: datetime,
    registry: FeatureRegistry | None = None,
) -> FeatureValue:
    """Calculate the six-month security return less matching benchmark return."""
    definition = _definition(registry, "relative_strength_6m")
    if "benchmark_price_bars:split_adjusted" not in definition.required_inputs:
        raise DataQualityError("relative_strength_6m@v1 lacks its approved benchmark input")
    security_window = _window(
        _history(
            security_observations,
            security_id=security_id,
            formation_date=formation_date,
            decision_at=decision_at,
        ),
        127,
        "relative_strength_6m security history",
    )
    benchmark_window = _window(
        _history(
            benchmark_observations,
            security_id=benchmark_security_id,
            formation_date=formation_date,
            decision_at=decision_at,
        ),
        127,
        "relative_strength_6m benchmark history",
    )
    if [item.session_date for item in security_window] != [item.session_date for item in benchmark_window]:
        raise DataQualityError("relative_strength_6m requires matching security and benchmark sessions")
    security_return = security_window[-1].close_price / security_window[0].close_price - Decimal("1")
    benchmark_return = benchmark_window[-1].close_price / benchmark_window[0].close_price - Decimal("1")
    return FeatureValue(
        security_id=security_id,
        formation_date=formation_date,
        feature_key=definition.key,
        feature_version=definition.version,
        definition_hash=definition.definition_hash,
        value=security_return - benchmark_return,
    )
