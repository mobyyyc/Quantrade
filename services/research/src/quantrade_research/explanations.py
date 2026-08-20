"""Clear, reproducible feature contributions for the transparent baseline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from .baseline import BASELINE_MODEL_VERSION, CompositeBaselineScore, build_equal_weight_baseline
from .features import FeatureDefinition, FeatureRegistry, baseline_feature_registry
from .quality import DataQualityError
from .ranking import SectorPercentileRank


@dataclass(frozen=True, slots=True)
class BaselineFeatureContribution:
    security_id: str
    formation_date: date
    model_version: str
    feature_key: str
    feature_version: str
    definition_hash: str
    sector_code: str
    percentile: Decimal | None
    weight: Decimal
    contribution: Decimal | None
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        if (self.percentile is None) != (self.contribution is None):
            raise DataQualityError("percentile and contribution must be available together")
        if self.percentile is None and self.unavailable_reason is None:
            raise DataQualityError("unavailable contribution requires a reason")
        if self.percentile is not None and self.unavailable_reason is not None:
            raise DataQualityError("available contribution cannot have an unavailable reason")


def _definitions(registry: FeatureRegistry | None) -> tuple[FeatureDefinition, ...]:
    definitions = (registry or baseline_feature_registry()).definitions()
    if not definitions:
        raise DataQualityError("explanations require at least one feature definition")
    return definitions


def build_baseline_feature_contributions(
    scores: Iterable[CompositeBaselineScore],
    ranks: Iterable[SectorPercentileRank],
    *,
    formation_date: date,
    universe_security_ids: Iterable[str],
    registry: FeatureRegistry | None = None,
) -> tuple[BaselineFeatureContribution, ...]:
    """Explain each baseline score with every required rank and its fixed weight."""
    universe = set(universe_security_ids)
    if not universe:
        raise DataQualityError("explanations require a non-empty universe")
    definitions = _definitions(registry)
    active_registry = registry or baseline_feature_registry()
    rank_list = list(ranks)
    expected_scores = {
        item.security_id: item
        for item in build_equal_weight_baseline(
            rank_list,
            formation_date=formation_date,
            universe_security_ids=universe,
            registry=active_registry,
        )
    }
    score_index: dict[str, CompositeBaselineScore] = {}
    for score in scores:
        if score.formation_date != formation_date:
            raise DataQualityError("all baseline scores must use the requested formation date")
        if score.security_id not in universe:
            raise DataQualityError(f"score security is outside the requested universe: {score.security_id}")
        if score.security_id in score_index:
            raise DataQualityError(f"duplicate baseline score for {score.security_id}")
        if score != expected_scores[score.security_id]:
            raise DataQualityError(f"baseline score does not match its registered ranks: {score.security_id}")
        score_index[score.security_id] = score
    if set(score_index) != universe:
        raise DataQualityError("missing explicit baseline score for one or more universe securities")
    rank_index = {
        (rank.security_id, rank.feature_key, rank.feature_version): rank for rank in rank_list
    }
    weight = Decimal("1") / Decimal(len(definitions))
    contributions: list[BaselineFeatureContribution] = []
    for security_id in sorted(universe):
        for definition in definitions:
            rank = rank_index[(security_id, definition.key, definition.version)]
            contribution = rank.percentile * weight if rank.percentile is not None else None
            contributions.append(
                BaselineFeatureContribution(
                    security_id,
                    formation_date,
                    BASELINE_MODEL_VERSION,
                    definition.key,
                    definition.version,
                    definition.definition_hash,
                    rank.sector_code,
                    rank.percentile,
                    weight,
                    contribution,
                    rank.unavailable_reason,
                )
            )
    return tuple(contributions)
