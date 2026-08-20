"""Explicit, conservative gates for research-model approval."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from .quality import DataQualityError


ApprovalScope = Literal["private_beta", "public_performance_claim"]


@dataclass(frozen=True, slots=True)
class ModelApprovalEvidence:
    data_capability_tier: str
    walk_forward_fold_count: int
    feature_coverage: Decimal
    holdout_evaluated: bool
    holdout_relative_return_after_20bps: Decimal | None
    point_in_time_violations: int
    unresolved_data_quality_issues: int


@dataclass(frozen=True, slots=True)
class ApprovalGateResult:
    gate: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ModelApprovalDecision:
    scope: ApprovalScope
    approved: bool
    results: tuple[ApprovalGateResult, ...]


MINIMUM_FEATURE_COVERAGE = Decimal("0.90")
MINIMUM_WALK_FORWARD_FOLDS = 3


def evaluate_model_approval(
    evidence: ModelApprovalEvidence, *, scope: ApprovalScope
) -> ModelApprovalDecision:
    """Evaluate fixed governance gates without making a performance claim."""
    if scope not in ("private_beta", "public_performance_claim"):
        raise DataQualityError(f"unsupported model approval scope: {scope}")
    if evidence.data_capability_tier not in ("A", "B", "C"):
        raise DataQualityError("data capability tier must be A, B, or C")
    if not Decimal("0") <= evidence.feature_coverage <= Decimal("1"):
        raise DataQualityError("feature coverage must be between zero and one")
    if evidence.walk_forward_fold_count < 0:
        raise DataQualityError("walk-forward fold count cannot be negative")
    if evidence.point_in_time_violations < 0 or evidence.unresolved_data_quality_issues < 0:
        raise DataQualityError("quality-issue counts cannot be negative")
    results = (
        ApprovalGateResult(
            "point_in_time_integrity",
            evidence.point_in_time_violations == 0,
            f"point-in-time violations={evidence.point_in_time_violations}",
        ),
        ApprovalGateResult(
            "data_quality",
            evidence.unresolved_data_quality_issues == 0,
            f"unresolved data-quality issues={evidence.unresolved_data_quality_issues}",
        ),
        ApprovalGateResult(
            "feature_coverage",
            evidence.feature_coverage >= MINIMUM_FEATURE_COVERAGE,
            f"feature coverage={evidence.feature_coverage}; minimum={MINIMUM_FEATURE_COVERAGE}",
        ),
        ApprovalGateResult(
            "walk_forward_validation",
            evidence.walk_forward_fold_count >= MINIMUM_WALK_FORWARD_FOLDS,
            f"walk-forward folds={evidence.walk_forward_fold_count}; minimum={MINIMUM_WALK_FORWARD_FOLDS}",
        ),
        ApprovalGateResult(
            "locked_holdout",
            evidence.holdout_evaluated and evidence.holdout_relative_return_after_20bps is not None,
            "final holdout must be evaluated under the 20-bps one-way sensitivity",
        ),
        ApprovalGateResult(
            "cost_robustness",
            evidence.holdout_relative_return_after_20bps is not None
            and evidence.holdout_relative_return_after_20bps >= Decimal("0"),
            "holdout benchmark-relative return after 20 bps one-way cost must be non-negative",
        ),
        ApprovalGateResult(
            "data_capability",
            evidence.data_capability_tier in (("A", "B") if scope == "private_beta" else ("A",)),
            "private beta permits Tier A/B; public performance claims require Tier A",
        ),
    )
    return ModelApprovalDecision(scope, all(result.passed for result in results), results)
