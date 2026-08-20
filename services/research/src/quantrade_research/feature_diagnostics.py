"""Coverage, missingness, correlation, and turnover diagnostics for features."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import combinations
from typing import Iterable

from .features import FeatureDefinition, FeatureRegistry, baseline_feature_registry
from .quality import DataQualityError


@dataclass(frozen=True, slots=True)
class FeatureOutcome:
    security_id: str
    formation_date: date
    feature_key: str
    feature_version: str
    definition_hash: str
    value: Decimal | None
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        if (self.value is None) == (self.unavailable_reason is None):
            raise DataQualityError(
                "a feature outcome requires exactly one of value or unavailable_reason"
            )
        if self.unavailable_reason is not None and not self.unavailable_reason.strip():
            raise DataQualityError("unavailable_reason cannot be blank")


@dataclass(frozen=True, slots=True)
class FeatureCoverage:
    feature_key: str
    feature_version: str
    eligible_security_count: int
    available_security_count: int
    unavailable_security_count: int
    coverage: Decimal


@dataclass(frozen=True, slots=True)
class FeatureMissingness:
    feature_key: str
    feature_version: str
    reason: str
    security_count: int


@dataclass(frozen=True, slots=True)
class FeatureCorrelation:
    left_feature_key: str
    right_feature_key: str
    paired_security_count: int
    correlation: Decimal | None
    unavailable_reason: str | None


@dataclass(frozen=True, slots=True)
class FeatureTurnover:
    feature_key: str
    feature_version: str
    prior_formation_date: date
    formation_date: date
    selected_count: int
    retained_count: int
    turnover: Decimal


@dataclass(frozen=True, slots=True)
class FeatureDiagnosticsReport:
    formation_date: date
    coverage: tuple[FeatureCoverage, ...]
    missingness: tuple[FeatureMissingness, ...]
    correlations: tuple[FeatureCorrelation, ...]
    turnover: tuple[FeatureTurnover, ...]


def _definitions(registry: FeatureRegistry | None) -> tuple[FeatureDefinition, ...]:
    definitions = (registry or baseline_feature_registry()).definitions()
    if not definitions:
        raise DataQualityError("feature diagnostics requires at least one feature definition")
    return definitions


def _outcome_index(
    outcomes: Iterable[FeatureOutcome],
    *,
    formation_date: date,
    universe_security_ids: set[str],
    definitions: tuple[FeatureDefinition, ...],
) -> dict[tuple[str, str, str], FeatureOutcome]:
    definition_by_identity = {(item.key, item.version): item for item in definitions}
    indexed: dict[tuple[str, str, str], FeatureOutcome] = {}
    for outcome in outcomes:
        if outcome.formation_date != formation_date:
            raise DataQualityError("all feature outcomes must use the requested formation date")
        if outcome.security_id not in universe_security_ids:
            raise DataQualityError(f"outcome security is outside the requested universe: {outcome.security_id}")
        definition = definition_by_identity.get((outcome.feature_key, outcome.feature_version))
        if definition is None:
            raise DataQualityError(
                f"outcome references an unregistered feature: {outcome.feature_key}@{outcome.feature_version}"
            )
        if outcome.definition_hash != definition.definition_hash:
            raise DataQualityError(
                f"outcome definition hash does not match {outcome.feature_key}@{outcome.feature_version}"
            )
        identity = (outcome.security_id, outcome.feature_key, outcome.feature_version)
        if identity in indexed:
            raise DataQualityError(f"duplicate feature outcome: {identity}")
        indexed[identity] = outcome
    for security_id in universe_security_ids:
        for definition in definitions:
            identity = (security_id, definition.key, definition.version)
            if identity not in indexed:
                raise DataQualityError(f"missing explicit feature outcome: {identity}")
    return indexed


def _correlation(values: list[tuple[Decimal, Decimal]]) -> tuple[Decimal | None, str | None]:
    if len(values) < 2:
        return None, "fewer_than_two_paired_observations"
    left = [pair[0] for pair in values]
    right = [pair[1] for pair in values]
    left_mean = sum(left, Decimal("0")) / Decimal(len(left))
    right_mean = sum(right, Decimal("0")) / Decimal(len(right))
    left_centered = [value - left_mean for value in left]
    right_centered = [value - right_mean for value in right]
    left_sum_squares = sum((value**2 for value in left_centered), Decimal("0"))
    right_sum_squares = sum((value**2 for value in right_centered), Decimal("0"))
    if left_sum_squares == 0 or right_sum_squares == 0:
        return None, "zero_variance"
    covariance_numerator = sum(
        (left_value * right_value for left_value, right_value in zip(left_centered, right_centered)),
        Decimal("0"),
    )
    return covariance_numerator / (left_sum_squares * right_sum_squares).sqrt(), None


def _selected_security_ids(
    index: dict[tuple[str, str, str], FeatureOutcome],
    definition: FeatureDefinition,
    universe_security_ids: set[str],
    top_n: int,
) -> set[str]:
    values = [
        index[(security_id, definition.key, definition.version)]
        for security_id in universe_security_ids
        if index[(security_id, definition.key, definition.version)].value is not None
    ]
    values.sort(
        key=lambda item: (item.value, item.security_id),
        reverse=definition.direction == "higher_is_better",
    )
    return {item.security_id for item in values[:top_n]}


def build_feature_diagnostics(
    outcomes: Iterable[FeatureOutcome],
    *,
    formation_date: date,
    universe_security_ids: Iterable[str],
    registry: FeatureRegistry | None = None,
    prior_outcomes: Iterable[FeatureOutcome] | None = None,
    prior_formation_date: date | None = None,
    top_n: int = 20,
) -> FeatureDiagnosticsReport:
    """Build a complete report; every requested feature outcome must be explicit."""
    if top_n < 1:
        raise DataQualityError("top_n must be positive")
    universe = set(universe_security_ids)
    if not universe:
        raise DataQualityError("feature diagnostics requires a non-empty universe")
    definitions = _definitions(registry)
    index = _outcome_index(
        outcomes,
        formation_date=formation_date,
        universe_security_ids=universe,
        definitions=definitions,
    )
    coverage: list[FeatureCoverage] = []
    missingness: list[FeatureMissingness] = []
    for definition in definitions:
        entries = [index[(security_id, definition.key, definition.version)] for security_id in universe]
        available = sum(entry.value is not None for entry in entries)
        coverage.append(
            FeatureCoverage(
                definition.key,
                definition.version,
                len(universe),
                available,
                len(universe) - available,
                Decimal(available) / Decimal(len(universe)),
            )
        )
        reasons = Counter(entry.unavailable_reason for entry in entries if entry.unavailable_reason is not None)
        missingness.extend(
            FeatureMissingness(definition.key, definition.version, reason, count)
            for reason, count in sorted(reasons.items())
        )
    correlations: list[FeatureCorrelation] = []
    for left, right in combinations(definitions, 2):
        pairs = [
            (left_entry.value, right_entry.value)
            for security_id in universe
            if (left_entry := index[(security_id, left.key, left.version)]).value is not None
            and (right_entry := index[(security_id, right.key, right.version)]).value is not None
        ]
        correlation, unavailable_reason = _correlation(pairs)
        correlations.append(
            FeatureCorrelation(left.key, right.key, len(pairs), correlation, unavailable_reason)
        )
    turnover: list[FeatureTurnover] = []
    if prior_outcomes is not None or prior_formation_date is not None:
        if prior_outcomes is None or prior_formation_date is None:
            raise DataQualityError("prior outcomes and prior formation date must be supplied together")
        if prior_formation_date >= formation_date:
            raise DataQualityError("prior formation date must precede formation date")
        prior_index = _outcome_index(
            prior_outcomes,
            formation_date=prior_formation_date,
            universe_security_ids=universe,
            definitions=definitions,
        )
        for definition in definitions:
            current_selected = _selected_security_ids(index, definition, universe, top_n)
            prior_selected = _selected_security_ids(prior_index, definition, universe, top_n)
            selected_count = max(len(current_selected), len(prior_selected))
            retained = len(current_selected & prior_selected)
            turnover_value = (
                Decimal("0")
                if selected_count == 0
                else Decimal("1") - Decimal(retained) / Decimal(selected_count)
            )
            turnover.append(
                FeatureTurnover(
                    definition.key,
                    definition.version,
                    prior_formation_date,
                    formation_date,
                    selected_count,
                    retained,
                    turnover_value,
                )
            )
    return FeatureDiagnosticsReport(
        formation_date,
        tuple(coverage),
        tuple(missingness),
        tuple(correlations),
        tuple(turnover),
    )
