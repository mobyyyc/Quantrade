"""Pre-registered gates for selecting one next-generation shadow challenger."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .quality import DataQualityError


MINIMUM_FEATURE_COVERAGE = Decimal("0.90")
MINIMUM_IC_IMPROVEMENT = Decimal("0.005")
MAXIMUM_SPREAD_REGRESSION = Decimal("0.0025")
MAXIMUM_POSITIVE_IC_SHARE_REGRESSION = Decimal("0.03")
MAXIMUM_RANK_STABILITY_REGRESSION = Decimal("0.05")
MAXIMUM_TURNOVER_INCREASE = Decimal("0.10")
MAXIMUM_ABSOLUTE_TURNOVER = Decimal("0.75")
MAXIMUM_POSITIVE_MONTH_SHARE_REGRESSION = Decimal("0.05")
MAXIMUM_ERROR_MULTIPLIER = Decimal("1.02")
MINIMUM_POSITIVE_SHARE = Decimal("0.50")
MINIMUM_FOLD_COUNT = 3


@dataclass(frozen=True, slots=True)
class ChallengerMetrics:
    model_version: str
    observation_count: int
    score_date_count: int
    fold_count: int
    monthly_formation_count: int
    feature_coverage: Decimal
    mean_daily_spearman_ic: Decimal
    top_minus_bottom_spread: Decimal
    positive_ic_share: Decimal
    fold_mean_ics: tuple[Decimal, ...]
    consecutive_rank_correlation: Decimal
    mean_monthly_turnover: Decimal
    relative_return_after_20bps: Decimal
    positive_month_share: Decimal
    mae: Decimal
    rmse: Decimal
    point_in_time_violations: int = 0
    unresolved_data_quality_issues: int = 0

    def __post_init__(self) -> None:
        if not self.model_version.strip():
            raise DataQualityError("model version is required")
        if min(self.observation_count, self.score_date_count, self.monthly_formation_count) < 1:
            raise DataQualityError("comparison counts must be positive")
        if self.fold_count < MINIMUM_FOLD_COUNT or len(self.fold_mean_ics) != self.fold_count:
            raise DataQualityError("comparison requires one IC value for each of at least three folds")
        if self.point_in_time_violations < 0 or self.unresolved_data_quality_issues < 0:
            raise DataQualityError("quality issue counts cannot be negative")
        numeric_values = (
            self.feature_coverage,
            self.mean_daily_spearman_ic,
            self.top_minus_bottom_spread,
            self.positive_ic_share,
            *self.fold_mean_ics,
            self.consecutive_rank_correlation,
            self.mean_monthly_turnover,
            self.relative_return_after_20bps,
            self.positive_month_share,
            self.mae,
            self.rmse,
        )
        if any(not value.is_finite() for value in numeric_values):
            raise DataQualityError("comparison metrics must be finite")
        for name, value in (
            ("feature coverage", self.feature_coverage),
            ("positive IC share", self.positive_ic_share),
            ("monthly turnover", self.mean_monthly_turnover),
            ("positive month share", self.positive_month_share),
        ):
            if not Decimal("0") <= value <= Decimal("1"):
                raise DataQualityError(f"{name} must be between zero and one")
        if self.mae < 0 or self.rmse < 0:
            raise DataQualityError("MAE and RMSE cannot be negative")
        for name, value in (
            ("mean daily Spearman IC", self.mean_daily_spearman_ic),
            ("consecutive-rank correlation", self.consecutive_rank_correlation),
            *(("fold mean IC", value) for value in self.fold_mean_ics),
        ):
            if not Decimal("-1") <= value <= Decimal("1"):
                raise DataQualityError(f"{name} must be between negative one and one")


@dataclass(frozen=True, slots=True)
class ChallengerGateResult:
    gate: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ChallengerDecision:
    active_model_version: str
    challenger_model_version: str
    protocol_version: str
    freeze_eligible: bool
    results: tuple[ChallengerGateResult, ...]


def _minimum(reference: Decimal, regression: Decimal, floor: Decimal) -> Decimal:
    return max(floor, reference - regression)


def evaluate_challenger(active: ChallengerMetrics, challenger: ChallengerMetrics) -> ChallengerDecision:
    """Apply every frozen gate on one like-for-like development comparison."""
    common_sample = (
        active.observation_count == challenger.observation_count
        and active.score_date_count == challenger.score_date_count
        and active.fold_count == challenger.fold_count
        and active.monthly_formation_count == challenger.monthly_formation_count
    )
    positive_ic_minimum = _minimum(
        active.positive_ic_share,
        MAXIMUM_POSITIVE_IC_SHARE_REGRESSION,
        MINIMUM_POSITIVE_SHARE,
    )
    positive_month_minimum = _minimum(
        active.positive_month_share,
        MAXIMUM_POSITIVE_MONTH_SHARE_REGRESSION,
        MINIMUM_POSITIVE_SHARE,
    )
    turnover_maximum = min(
        MAXIMUM_ABSOLUTE_TURNOVER,
        active.mean_monthly_turnover + MAXIMUM_TURNOVER_INCREASE,
    )
    results = (
        ChallengerGateResult(
            "point_in_time_integrity",
            challenger.point_in_time_violations == 0,
            f"point-in-time violations={challenger.point_in_time_violations}",
        ),
        ChallengerGateResult(
            "data_quality",
            challenger.unresolved_data_quality_issues == 0,
            f"unresolved data-quality issues={challenger.unresolved_data_quality_issues}",
        ),
        ChallengerGateResult(
            "common_sample",
            common_sample,
            "active and challenger counts must match for observations, dates, folds, and formations",
        ),
        ChallengerGateResult(
            "feature_coverage",
            challenger.feature_coverage >= MINIMUM_FEATURE_COVERAGE,
            f"coverage={challenger.feature_coverage}; minimum={MINIMUM_FEATURE_COVERAGE}",
        ),
        ChallengerGateResult(
            "rank_ic_improvement",
            challenger.mean_daily_spearman_ic - active.mean_daily_spearman_ic >= MINIMUM_IC_IMPROVEMENT,
            f"delta={challenger.mean_daily_spearman_ic - active.mean_daily_spearman_ic}; minimum={MINIMUM_IC_IMPROVEMENT}",
        ),
        ChallengerGateResult(
            "spread_noninferiority",
            challenger.top_minus_bottom_spread >= active.top_minus_bottom_spread - MAXIMUM_SPREAD_REGRESSION,
            f"challenger={challenger.top_minus_bottom_spread}; floor={active.top_minus_bottom_spread - MAXIMUM_SPREAD_REGRESSION}",
        ),
        ChallengerGateResult(
            "fold_stability",
            all(value > 0 for value in challenger.fold_mean_ics),
            f"fold_mean_ics={','.join(str(value) for value in challenger.fold_mean_ics)}",
        ),
        ChallengerGateResult(
            "positive_ic_share",
            challenger.positive_ic_share >= positive_ic_minimum,
            f"challenger={challenger.positive_ic_share}; minimum={positive_ic_minimum}",
        ),
        ChallengerGateResult(
            "rank_stability",
            challenger.consecutive_rank_correlation >= active.consecutive_rank_correlation - MAXIMUM_RANK_STABILITY_REGRESSION,
            f"challenger={challenger.consecutive_rank_correlation}; floor={active.consecutive_rank_correlation - MAXIMUM_RANK_STABILITY_REGRESSION}",
        ),
        ChallengerGateResult(
            "turnover",
            challenger.mean_monthly_turnover <= turnover_maximum,
            f"challenger={challenger.mean_monthly_turnover}; maximum={turnover_maximum}",
        ),
        ChallengerGateResult(
            "cost_robustness",
            challenger.relative_return_after_20bps >= active.relative_return_after_20bps,
            f"challenger={challenger.relative_return_after_20bps}; active={active.relative_return_after_20bps}",
        ),
        ChallengerGateResult(
            "positive_month_share",
            challenger.positive_month_share >= positive_month_minimum,
            f"challenger={challenger.positive_month_share}; minimum={positive_month_minimum}",
        ),
        ChallengerGateResult(
            "mae_noninferiority",
            challenger.mae <= active.mae * MAXIMUM_ERROR_MULTIPLIER,
            f"challenger={challenger.mae}; maximum={active.mae * MAXIMUM_ERROR_MULTIPLIER}",
        ),
        ChallengerGateResult(
            "rmse_noninferiority",
            challenger.rmse <= active.rmse * MAXIMUM_ERROR_MULTIPLIER,
            f"challenger={challenger.rmse}; maximum={active.rmse * MAXIMUM_ERROR_MULTIPLIER}",
        ),
    )
    return ChallengerDecision(
        active.model_version,
        challenger.model_version,
        "tier_b_challenger_selection_v1",
        all(result.passed for result in results),
        results,
    )


def challenger_selection_key(metrics: ChallengerMetrics) -> tuple[Decimal, Decimal, Decimal, Decimal, str]:
    """Sort passing candidates using the pre-registered deterministic order."""
    return (
        -metrics.mean_daily_spearman_ic,
        -metrics.top_minus_bottom_spread,
        metrics.mean_monthly_turnover,
        metrics.rmse,
        metrics.model_version,
    )
