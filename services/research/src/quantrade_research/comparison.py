"""Guarded comparison of regularized linear candidates against the approved baseline."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from .approval import ModelApprovalDecision
from .baseline import BASELINE_MODEL_VERSION
from .evaluation import PerformanceMetrics
from .quality import DataQualityError


RegularizedLinearFamily = Literal["ridge", "elastic_net"]


@dataclass(frozen=True, slots=True)
class RegularizedLinearModelSpec:
    model_version: str
    family: RegularizedLinearFamily
    l1_penalty: Decimal
    l2_penalty: Decimal
    feature_registry_hash: str

    def __post_init__(self) -> None:
        if not self.model_version.strip() or len(self.feature_registry_hash) != 64:
            raise DataQualityError("candidate model version and feature registry hash are required")
        if self.family not in ("ridge", "elastic_net"):
            raise DataQualityError("candidate must be a supported regularized linear family")
        if self.l1_penalty < 0 or self.l2_penalty < 0:
            raise DataQualityError("regularization penalties cannot be negative")
        if self.family == "ridge" and (self.l1_penalty != 0 or self.l2_penalty <= 0):
            raise DataQualityError("ridge requires zero L1 and positive L2 penalty")
        if self.family == "elastic_net" and (self.l1_penalty <= 0 or self.l2_penalty <= 0):
            raise DataQualityError("elastic net requires positive L1 and L2 penalties")


@dataclass(frozen=True, slots=True)
class ModelComparison:
    baseline_model_version: str
    candidate_model_version: str
    candidate_family: RegularizedLinearFamily
    baseline_relative_return: Decimal
    candidate_relative_return: Decimal
    relative_return_delta: Decimal
    baseline_sharpe_ratio: Decimal | None
    candidate_sharpe_ratio: Decimal | None


def compare_regularized_candidate(
    baseline_decision: ModelApprovalDecision,
    baseline_metrics: PerformanceMetrics,
    baseline_feature_registry_hash: str,
    candidate: RegularizedLinearModelSpec,
    candidate_metrics: PerformanceMetrics,
) -> ModelComparison:
    """Compare a regularized candidate after—not before—the baseline passes approval."""
    if baseline_decision.scope != "private_beta" or not baseline_decision.approved:
        raise DataQualityError("regularized candidates may only compare against an approved private-beta baseline")
    if baseline_feature_registry_hash != candidate.feature_registry_hash:
        raise DataQualityError("candidate must use the approved baseline feature registry")
    if baseline_metrics.observation_count != candidate_metrics.observation_count:
        raise DataQualityError("baseline and candidate metrics must use the same observation count")
    return ModelComparison(
        BASELINE_MODEL_VERSION,
        candidate.model_version,
        candidate.family,
        baseline_metrics.benchmark_relative_return,
        candidate_metrics.benchmark_relative_return,
        candidate_metrics.benchmark_relative_return - baseline_metrics.benchmark_relative_return,
        baseline_metrics.sharpe_ratio,
        candidate_metrics.sharpe_ratio,
    )
