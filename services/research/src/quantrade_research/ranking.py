"""Sector-aware, point-in-time percentile normalization for feature values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable

from .feature_diagnostics import FeatureOutcome
from .features import FeatureDefinition, FeatureRegistry, baseline_feature_registry
from .quality import DataQualityError


@dataclass(frozen=True, slots=True)
class SectorClassification:
    security_id: str
    sector_code: str
    as_of_date: date
    available_at: datetime


@dataclass(frozen=True, slots=True)
class SectorPercentileRank:
    security_id: str
    formation_date: date
    feature_key: str
    feature_version: str
    definition_hash: str
    sector_code: str
    peer_count: int
    percentile: Decimal | None
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        if (self.percentile is None) == (self.unavailable_reason is None):
            raise DataQualityError(
                "a sector percentile rank requires exactly one of percentile or unavailable_reason"
            )


def _as_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DataQualityError(f"{label} must include a UTC offset")
    return value.astimezone(timezone.utc)


def _definitions(registry: FeatureRegistry | None) -> tuple[FeatureDefinition, ...]:
    definitions = (registry or baseline_feature_registry()).definitions()
    if not definitions:
        raise DataQualityError("ranking requires at least one feature definition")
    return definitions


def _sector_index(
    classifications: Iterable[SectorClassification],
    *,
    universe_security_ids: set[str],
    formation_date: date,
    decision_at: datetime,
) -> dict[str, SectorClassification]:
    decision = _as_utc(decision_at, "decision_at")
    selected: dict[str, SectorClassification] = {}
    for classification in classifications:
        if classification.security_id not in universe_security_ids:
            continue
        if classification.as_of_date > formation_date:
            raise DataQualityError(
                f"sector classification for {classification.security_id} has a future as_of_date"
            )
        if _as_utc(classification.available_at, "sector available_at") > decision:
            raise DataQualityError(
                f"sector classification for {classification.security_id} was unavailable at decision_at"
            )
        if not classification.sector_code.strip():
            raise DataQualityError(f"sector classification for {classification.security_id} is blank")
        if classification.security_id in selected:
            raise DataQualityError(f"duplicate sector classification for {classification.security_id}")
        selected[classification.security_id] = classification
    missing = universe_security_ids - selected.keys()
    if missing:
        raise DataQualityError(f"missing sector classification for: {', '.join(sorted(missing))}")
    return selected


def _outcome_index(
    outcomes: Iterable[FeatureOutcome],
    *,
    universe_security_ids: set[str],
    formation_date: date,
    definitions: tuple[FeatureDefinition, ...],
) -> dict[tuple[str, str, str], FeatureOutcome]:
    definition_by_identity = {(item.key, item.version): item for item in definitions}
    index: dict[tuple[str, str, str], FeatureOutcome] = {}
    for outcome in outcomes:
        if outcome.formation_date != formation_date:
            raise DataQualityError("all feature outcomes must use the requested formation date")
        if outcome.security_id not in universe_security_ids:
            raise DataQualityError(f"outcome security is outside the requested universe: {outcome.security_id}")
        definition = definition_by_identity.get((outcome.feature_key, outcome.feature_version))
        if definition is None or outcome.definition_hash != definition.definition_hash:
            raise DataQualityError(
                f"outcome does not match a registered feature definition: {outcome.feature_key}@{outcome.feature_version}"
            )
        identity = (outcome.security_id, outcome.feature_key, outcome.feature_version)
        if identity in index:
            raise DataQualityError(f"duplicate feature outcome: {identity}")
        index[identity] = outcome
    for security_id in universe_security_ids:
        for definition in definitions:
            if (security_id, definition.key, definition.version) not in index:
                raise DataQualityError(
                    f"missing explicit feature outcome: {(security_id, definition.key, definition.version)}"
                )
    return index


def _percentiles(
    entries: list[FeatureOutcome], definition: FeatureDefinition
) -> dict[str, Decimal]:
    """Return tie-aware 0–1 percentiles, oriented so higher is always better."""
    ordered = sorted(entries, key=lambda item: (item.value, item.security_id))
    denominator = Decimal(len(ordered) - 1)
    result: dict[str, Decimal] = {}
    position = 0
    while position < len(ordered):
        end = position
        while end + 1 < len(ordered) and ordered[end + 1].value == ordered[position].value:
            end += 1
        raw_percentile = Decimal(position + end) / Decimal("2") / denominator
        percentile = raw_percentile if definition.direction == "higher_is_better" else Decimal("1") - raw_percentile
        for item in ordered[position : end + 1]:
            result[item.security_id] = percentile
        position = end + 1
    return result


def build_sector_aware_percentile_ranks(
    outcomes: Iterable[FeatureOutcome],
    classifications: Iterable[SectorClassification],
    *,
    formation_date: date,
    decision_at: datetime,
    universe_security_ids: Iterable[str],
    registry: FeatureRegistry | None = None,
    minimum_peer_count: int = 2,
) -> tuple[SectorPercentileRank, ...]:
    """Normalize explicit feature outcomes within dated sector cohorts."""
    if minimum_peer_count < 2:
        raise DataQualityError("minimum_peer_count must be at least two")
    universe = set(universe_security_ids)
    if not universe:
        raise DataQualityError("ranking requires a non-empty universe")
    definitions = _definitions(registry)
    sectors = _sector_index(
        classifications,
        universe_security_ids=universe,
        formation_date=formation_date,
        decision_at=decision_at,
    )
    index = _outcome_index(
        outcomes,
        universe_security_ids=universe,
        formation_date=formation_date,
        definitions=definitions,
    )
    ranks: list[SectorPercentileRank] = []
    for definition in definitions:
        sector_entries: dict[str, list[FeatureOutcome]] = {}
        for security_id in universe:
            outcome = index[(security_id, definition.key, definition.version)]
            if outcome.value is not None:
                sector_entries.setdefault(sectors[security_id].sector_code, []).append(outcome)
        values_by_sector = {
            sector: _percentiles(entries, definition)
            for sector, entries in sector_entries.items()
            if len(entries) >= minimum_peer_count
        }
        for security_id in sorted(universe):
            outcome = index[(security_id, definition.key, definition.version)]
            sector = sectors[security_id].sector_code
            peers = sector_entries.get(sector, [])
            if outcome.value is None:
                percentile = None
                reason = f"feature_unavailable:{outcome.unavailable_reason}"
            elif len(peers) < minimum_peer_count:
                percentile = None
                reason = "insufficient_sector_peers"
            else:
                percentile = values_by_sector[sector][security_id]
                reason = None
            ranks.append(
                SectorPercentileRank(
                    security_id,
                    formation_date,
                    definition.key,
                    definition.version,
                    definition.definition_hash,
                    sector,
                    len(peers),
                    percentile,
                    reason,
                )
            )
    return tuple(ranks)
