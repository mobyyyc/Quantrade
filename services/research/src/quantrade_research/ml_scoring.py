"""Cross-sectional daily scores from the deployed regularized linear model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from .active_model import ActiveModelArtifact
from .features import FeatureRegistry
from .quality import DataQualityError
from .ranking import SectorPercentileRank


@dataclass(frozen=True, slots=True)
class ModelScore:
    security_id: str
    formation_date: date
    model_version: str
    feature_registry_hash: str
    eligible: bool
    normalized_score: Decimal | None
    display_score: Decimal | None
    predicted_relative_return: Decimal | None
    unavailable_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ModelFeatureContribution:
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


def _rank_index(ranks: Iterable[SectorPercentileRank], formation_date: date) -> dict[tuple[str, str], SectorPercentileRank]:
    index: dict[tuple[str, str], SectorPercentileRank] = {}
    for rank in ranks:
        if rank.formation_date != formation_date:
            raise DataQualityError("model ranks must use the requested formation date")
        key = (rank.security_id, rank.feature_key)
        if key in index:
            raise DataQualityError(f"duplicate model rank: {rank.security_id}:{rank.feature_key}")
        index[key] = rank
    return index


def _validate_model(model: ActiveModelArtifact, registry: FeatureRegistry) -> None:
    if model.feature_registry_hash != registry.registry_hash:
        raise DataQualityError("active model feature registry does not match the scoring registry")
    registered = {f"{definition.key}_percentile" for definition in registry.definitions()}
    if set(model.feature_columns) != registered:
        raise DataQualityError("active model features do not match the scoring registry")


def _rank_feature_key(model_column: str) -> str:
    if not model_column.endswith("_percentile"):
        raise DataQualityError(f"active model feature is not a percentile input: {model_column}")
    return model_column.removesuffix("_percentile")


def build_model_scores(*, ranks: Iterable[SectorPercentileRank], formation_date: date,
                       universe_security_ids: Iterable[str], registry: FeatureRegistry,
                       model: ActiveModelArtifact) -> tuple[ModelScore, ...]:
    _validate_model(model, registry)
    universe = tuple(sorted(set(universe_security_ids)))
    if not universe:
        raise DataQualityError("model scoring requires a non-empty universe")
    index = _rank_index(ranks, formation_date)
    raw: dict[str, float] = {}
    unavailable: dict[str, str] = {}
    for security_id in universe:
        values: list[float] = []
        missing: list[str] = []
        for feature in model.feature_columns:
            rank_key = _rank_feature_key(feature)
            rank = index.get((security_id, rank_key))
            if rank is None:
                raise DataQualityError(f"missing explicit model rank: {security_id}:{rank_key}")
            if rank.percentile is None:
                missing.append(f"{rank_key}@{rank.feature_version}:{rank.unavailable_reason}")
            else:
                values.append(float(rank.percentile))
        if missing:
            unavailable[security_id] = "required_feature_rank_unavailable=" + ",".join(missing)
            continue
        raw[security_id] = model.target_mean + sum(
            coefficient * ((value - mean) / scale)
            for value, mean, scale, coefficient in zip(values, model.feature_means, model.feature_scales, model.coefficients)
        )
    ordered = sorted(raw, key=lambda security_id: (raw[security_id], security_id))
    denomin = max(1, len(ordered) - 1)
    normalized = {security_id: Decimal(index) / Decimal(denomin) for index, security_id in enumerate(ordered)}
    return tuple(
        ModelScore(
            security_id=security_id,
            formation_date=formation_date,
            model_version=model.model_version,
            feature_registry_hash=model.feature_registry_hash,
            eligible=security_id in normalized,
            normalized_score=normalized.get(security_id),
            display_score=(normalized[security_id] * Decimal("100")).quantize(Decimal("0.01")) if security_id in normalized else None,
            predicted_relative_return=Decimal(str(raw[security_id])).quantize(Decimal("0.000000000001")) if security_id in raw else None,
            unavailable_reason=unavailable.get(security_id),
        )
        for security_id in universe
    )


def build_model_feature_contributions(*, ranks: Iterable[SectorPercentileRank], formation_date: date,
                                      universe_security_ids: Iterable[str], registry: FeatureRegistry,
                                      model: ActiveModelArtifact) -> tuple[ModelFeatureContribution, ...]:
    _validate_model(model, registry)
    index = _rank_index(ranks, formation_date)
    coefficients = dict(zip(model.feature_columns, model.coefficients))
    means = dict(zip(model.feature_columns, model.feature_means))
    scales = dict(zip(model.feature_columns, model.feature_scales))
    active_columns = tuple(column for column in model.feature_columns if coefficients[column] != 0)
    total_absolute_coefficient = sum(abs(coefficients[column]) for column in active_columns)
    if total_absolute_coefficient <= 0:
        raise DataQualityError("active model has no non-zero feature coefficients")
    rows: list[ModelFeatureContribution] = []
    for security_id in sorted(set(universe_security_ids)):
        for feature in active_columns:
            rank_key = _rank_feature_key(feature)
            rank = index[(security_id, rank_key)]
            coefficient = Decimal(str(abs(coefficients[feature]) / total_absolute_coefficient))
            contribution = None if rank.percentile is None else Decimal(str(
                coefficients[feature] * ((float(rank.percentile) - means[feature]) / scales[feature])
            ))
            rows.append(ModelFeatureContribution(
                security_id, formation_date, model.model_version, feature, rank.feature_version,
                rank.definition_hash, rank.sector_code, rank.percentile, coefficient, contribution,
                rank.unavailable_reason,
            ))
    return tuple(rows)
