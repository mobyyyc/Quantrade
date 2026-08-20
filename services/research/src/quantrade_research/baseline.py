"""Transparent equal-weight composite baseline for eligible feature ranks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from .features import FeatureDefinition, FeatureRegistry, baseline_feature_registry
from .quality import DataQualityError
from .ranking import SectorPercentileRank


BASELINE_MODEL_VERSION = "baseline_equal_weight_v1"


@dataclass(frozen=True, slots=True)
class CompositeBaselineScore:
    security_id: str
    formation_date: date
    model_version: str
    feature_registry_hash: str
    eligible: bool
    normalized_score: Decimal | None
    display_score: Decimal | None
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        if self.eligible != (self.normalized_score is not None and self.display_score is not None):
            raise DataQualityError("eligible baseline scores require normalized and display scores")
        if self.eligible == (self.unavailable_reason is not None):
            raise DataQualityError("baseline score requires exactly one eligibility state and unavailable reason")
        if self.normalized_score is not None and not Decimal("0") <= self.normalized_score <= Decimal("1"):
            raise DataQualityError("normalized baseline score must be between zero and one")


def _definitions(registry: FeatureRegistry | None) -> tuple[FeatureDefinition, ...]:
    definitions = (registry or baseline_feature_registry()).definitions()
    if not definitions:
        raise DataQualityError("baseline requires at least one feature definition")
    return definitions


def _rank_index(
    ranks: Iterable[SectorPercentileRank],
    *,
    formation_date: date,
    universe_security_ids: set[str],
    definitions: tuple[FeatureDefinition, ...],
) -> dict[tuple[str, str, str], SectorPercentileRank]:
    definition_by_identity = {(definition.key, definition.version): definition for definition in definitions}
    index: dict[tuple[str, str, str], SectorPercentileRank] = {}
    for rank in ranks:
        if rank.formation_date != formation_date:
            raise DataQualityError("all baseline ranks must use the requested formation date")
        if rank.security_id not in universe_security_ids:
            raise DataQualityError(f"rank security is outside the requested universe: {rank.security_id}")
        definition = definition_by_identity.get((rank.feature_key, rank.feature_version))
        if definition is None or rank.definition_hash != definition.definition_hash:
            raise DataQualityError(
                f"rank does not match a registered feature definition: {rank.feature_key}@{rank.feature_version}"
            )
        identity = (rank.security_id, rank.feature_key, rank.feature_version)
        if identity in index:
            raise DataQualityError(f"duplicate sector percentile rank: {identity}")
        index[identity] = rank
    for security_id in universe_security_ids:
        for definition in definitions:
            identity = (security_id, definition.key, definition.version)
            if identity not in index:
                raise DataQualityError(f"missing explicit sector percentile rank: {identity}")
    return index


def build_equal_weight_baseline(
    ranks: Iterable[SectorPercentileRank],
    *,
    formation_date: date,
    universe_security_ids: Iterable[str],
    registry: FeatureRegistry | None = None,
) -> tuple[CompositeBaselineScore, ...]:
    """Average every required rank equally; unavailable inputs make the security ineligible."""
    universe = set(universe_security_ids)
    if not universe:
        raise DataQualityError("baseline requires a non-empty universe")
    definitions = _definitions(registry)
    active_registry = registry or baseline_feature_registry()
    index = _rank_index(
        ranks,
        formation_date=formation_date,
        universe_security_ids=universe,
        definitions=definitions,
    )
    scores: list[CompositeBaselineScore] = []
    for security_id in sorted(universe):
        security_ranks = [
            index[(security_id, definition.key, definition.version)] for definition in definitions
        ]
        unavailable = [
            f"{rank.feature_key}@{rank.feature_version}:{rank.unavailable_reason}"
            for rank in security_ranks
            if rank.percentile is None
        ]
        if unavailable:
            scores.append(
                CompositeBaselineScore(
                    security_id,
                    formation_date,
                    BASELINE_MODEL_VERSION,
                    active_registry.registry_hash,
                    False,
                    None,
                    None,
                    "required_feature_rank_unavailable=" + ",".join(unavailable),
                )
            )
            continue
        normalized_score = sum((rank.percentile for rank in security_ranks), Decimal("0")) / Decimal(
            len(security_ranks)
        )
        scores.append(
            CompositeBaselineScore(
                security_id,
                formation_date,
                BASELINE_MODEL_VERSION,
                active_registry.registry_hash,
                True,
                normalized_score,
                normalized_score * Decimal("100"),
            )
        )
    return tuple(scores)
