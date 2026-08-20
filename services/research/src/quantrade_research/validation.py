"""Chronological expanding-window and walk-forward validation planning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from .quality import DataQualityError


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    fold_number: int
    training_dates: tuple[date, ...]
    validation_dates: tuple[date, ...]

    def __post_init__(self) -> None:
        if not self.training_dates or not self.validation_dates:
            raise DataQualityError("walk-forward folds require training and validation dates")
        if set(self.training_dates) & set(self.validation_dates):
            raise DataQualityError("walk-forward training and validation dates must not overlap")
        if max(self.training_dates) >= min(self.validation_dates):
            raise DataQualityError("walk-forward validation must occur strictly after training")


def build_expanding_window_folds(
    observation_dates: Iterable[date],
    *,
    minimum_training_observations: int,
    validation_observations: int,
    step_observations: int | None = None,
) -> tuple[WalkForwardFold, ...]:
    """Create non-overlapping future validation windows from expanding history."""
    if minimum_training_observations < 1:
        raise DataQualityError("minimum training observations must be positive")
    if validation_observations < 1:
        raise DataQualityError("validation observations must be positive")
    step = step_observations or validation_observations
    if step < 1:
        raise DataQualityError("walk-forward step observations must be positive")
    dates = sorted(observation_dates)
    if len(set(dates)) != len(dates):
        raise DataQualityError("walk-forward observation dates must be unique")
    if len(dates) < minimum_training_observations + validation_observations:
        raise DataQualityError("not enough observations for one expanding-window fold")
    folds: list[WalkForwardFold] = []
    validation_start = minimum_training_observations
    while validation_start + validation_observations <= len(dates):
        folds.append(
            WalkForwardFold(
                len(folds) + 1,
                tuple(dates[:validation_start]),
                tuple(dates[validation_start : validation_start + validation_observations]),
            )
        )
        validation_start += step
    return tuple(folds)


def assert_walk_forward_plan_is_chronological(folds: Iterable[WalkForwardFold]) -> None:
    """Reject plans that reuse a future validation date in an earlier training set."""
    plan = list(folds)
    if not plan:
        raise DataQualityError("walk-forward plan cannot be empty")
    previous_validation_end: date | None = None
    for expected_number, fold in enumerate(plan, start=1):
        if fold.fold_number != expected_number:
            raise DataQualityError("walk-forward fold numbers must be consecutive")
        if previous_validation_end is not None and min(fold.validation_dates) <= previous_validation_end:
            raise DataQualityError("walk-forward validation windows must not overlap or go backward")
        if previous_validation_end is not None and previous_validation_end not in fold.training_dates:
            raise DataQualityError("later expanding windows must include prior validation history")
        previous_validation_end = max(fold.validation_dates)
