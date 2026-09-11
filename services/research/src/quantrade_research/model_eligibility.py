"""Shared active-model input eligibility and prediction semantics."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .active_model import ActiveModelArtifact
from .quality import DataQualityError


ALL_SERIALIZED_INPUTS_V1 = "all_serialized_inputs_v1"
EXACT_ZERO_COEFFICIENTS_V1 = "exact_zero_coefficients_v1"
SUPPORTED_ELIGIBILITY_CONTRACTS = frozenset({
    ALL_SERIALIZED_INPUTS_V1,
    EXACT_ZERO_COEFFICIENTS_V1,
})


def ignores_exact_zero_coefficients(contract_version: str) -> bool:
    """Resolve a named eligibility contract without approximate-zero behavior."""
    if contract_version not in SUPPORTED_ELIGIBILITY_CONTRACTS:
        raise DataQualityError(f"unsupported score eligibility contract: {contract_version}")
    return contract_version == EXACT_ZERO_COEFFICIENTS_V1


@dataclass(frozen=True, slots=True)
class ModelInputEvaluation:
    prediction: float | None
    missing_required_columns: tuple[str, ...]

    @property
    def eligible(self) -> bool:
        return self.prediction is not None


def required_model_columns(
    model: ActiveModelArtifact, *, ignore_exact_zero_coefficients: bool,
) -> tuple[str, ...]:
    """Return required inputs using exact serialized floating-point equality."""
    if ignore_exact_zero_coefficients:
        return tuple(
            column
            for column, coefficient in zip(
                model.feature_columns, model.coefficients, strict=True,
            )
            if coefficient != 0.0
        )
    return model.feature_columns


def evaluate_model_inputs(
    model: ActiveModelArtifact,
    values: Mapping[str, float | None],
    *,
    ignore_exact_zero_coefficients: bool,
) -> ModelInputEvaluation:
    """Validate one row and replay the artifact without approximate-zero logic.

    Missing exact-zero inputs are replaced with their frozen means. This keeps
    the full serialized arithmetic sequence intact, so a previously complete
    row produces the same IEEE-754 prediction under either eligibility policy.
    """
    required = set(required_model_columns(
        model, ignore_exact_zero_coefficients=ignore_exact_zero_coefficients,
    ))
    missing = tuple(
        column for column in model.feature_columns
        if column in required and values.get(column) is None
    )
    if missing:
        return ModelInputEvaluation(None, missing)

    ordered_values: list[float] = []
    for column, mean, coefficient in zip(
        model.feature_columns,
        model.feature_means,
        model.coefficients,
        strict=True,
    ):
        value = values.get(column)
        if value is None:
            if not ignore_exact_zero_coefficients or coefficient != 0.0:
                raise DataQualityError("model input eligibility and prediction disagree")
            value = mean
        ordered_values.append(float(value))

    prediction = model.target_mean + sum(
        coefficient * ((value - mean) / scale)
        for value, mean, scale, coefficient in zip(
            ordered_values,
            model.feature_means,
            model.feature_scales,
            model.coefficients,
            strict=True,
        )
    )
    return ModelInputEvaluation(prediction, ())
