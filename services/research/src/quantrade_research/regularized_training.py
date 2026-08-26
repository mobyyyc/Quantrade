"""Development-only ridge and elastic-net experiments for the Tier-B export.

The implementation intentionally uses the Python standard library.  With six
fixed percentile features, fitting from sufficient statistics is fast,
deterministic, and avoids adding a heavyweight ML runtime to the private
research workflow.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date
import json
import math
import os
from pathlib import Path
from statistics import fmean
from typing import Iterable, Sequence

from .historical_training_export import HOLDOUT_START
from .quality import DataQualityError
from .score_run import _dotenv_values


FEATURE_COLUMNS = (
    "earnings_yield_ttm_percentile",
    "median_dollar_volume_20d_percentile",
    "momentum_12_1_percentile",
    "relative_strength_6m_percentile",
    "return_on_assets_ttm_percentile",
    "trailing_volatility_60d_percentile",
)
TARGET_COLUMN = "benchmark_relative_return"
PURGE_SESSIONS = 20
DEFAULT_VALIDATION_SESSIONS = 126
DEFAULT_FOLD_COUNT = 3


@dataclass(frozen=True, slots=True)
class TrainingExample:
    score_date: date
    features: tuple[float, ...]
    target: float


@dataclass(frozen=True, slots=True)
class TimeOrderedFold:
    fold_number: int
    training_end_date: date
    purge_start_date: date
    purge_end_date: date
    validation_start_date: date
    validation_end_date: date


@dataclass(frozen=True, slots=True)
class LinearModel:
    family: str
    l1_penalty: float
    l2_penalty: float
    feature_means: tuple[float, ...]
    feature_scales: tuple[float, ...]
    target_mean: float
    coefficients: tuple[float, ...]

    def predict(self, features: Sequence[float]) -> float:
        standardized = ((value - mean) / scale for value, mean, scale in zip(features, self.feature_means, self.feature_scales))
        return self.target_mean + sum(coefficient * value for coefficient, value in zip(self.coefficients, standardized))


def _parse_example(row: dict[str, str], line_number: int) -> TrainingExample:
    if row.get("partition") != "development":
        raise DataQualityError(f"training CSV line {line_number} is not development data")
    try:
        score_date = date.fromisoformat(row["score_date"])
        features = tuple(float(row[column]) for column in FEATURE_COLUMNS)
        target = float(row[TARGET_COLUMN])
    except (KeyError, TypeError, ValueError) as error:
        raise DataQualityError(f"invalid training CSV line {line_number}") from error
    if score_date >= HOLDOUT_START:
        raise DataQualityError(f"training CSV line {line_number} reaches the locked holdout")
    if not all(math.isfinite(value) for value in (*features, target)):
        raise DataQualityError(f"training CSV line {line_number} contains a non-finite value")
    return TrainingExample(score_date, features, target)


def load_development_examples(path: Path) -> tuple[TrainingExample, ...]:
    """Load only completed development rows; reject any holdout contamination."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"partition", "score_date", TARGET_COLUMN, *FEATURE_COLUMNS}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise DataQualityError("training CSV does not have the required wide schema")
        examples = tuple(
            _parse_example(row, line_number)
            for line_number, row in enumerate(reader, start=2)
            if row.get("partition") == "development"
        )
    if not examples:
        raise DataQualityError("training CSV contains no development examples")
    return tuple(sorted(examples, key=lambda item: item.score_date))


def build_time_ordered_folds(
    examples: Iterable[TrainingExample], *, fold_count: int = DEFAULT_FOLD_COUNT,
    validation_sessions: int = DEFAULT_VALIDATION_SESSIONS, purge_sessions: int = PURGE_SESSIONS,
) -> tuple[TimeOrderedFold, ...]:
    """Create non-overlapping later validation windows with a session-count purge."""
    if fold_count < 1 or validation_sessions < 1 or purge_sessions < 1:
        raise DataQualityError("fold count, validation sessions, and purge sessions must be positive")
    sessions = sorted({example.score_date for example in examples})
    needed = (fold_count * validation_sessions) + purge_sessions + 1
    if len(sessions) < needed:
        raise DataQualityError(f"need at least {needed} development sessions for the requested folds")
    first_validation_index = len(sessions) - fold_count * validation_sessions
    folds: list[TimeOrderedFold] = []
    for index in range(fold_count):
        validation_start_index = first_validation_index + index * validation_sessions
        validation_end_index = validation_start_index + validation_sessions - 1
        training_end_index = validation_start_index - purge_sessions - 1
        if training_end_index < 0:
            raise DataQualityError("time-ordered validation leaves no pre-purge training history")
        folds.append(TimeOrderedFold(
            index + 1,
            sessions[training_end_index],
            sessions[training_end_index + 1],
            sessions[validation_start_index - 1],
            sessions[validation_start_index],
            sessions[validation_end_index],
        ))
    return tuple(folds)


def _fit_statistics(examples: Sequence[TrainingExample]) -> tuple[tuple[float, ...], tuple[float, ...], float, list[list[float]], list[float]]:
    if not examples:
        raise DataQualityError("cannot fit a model without training examples")
    width = len(FEATURE_COLUMNS)
    means = tuple(fmean(example.features[index] for example in examples) for index in range(width))
    scales = tuple(math.sqrt(fmean((example.features[index] - means[index]) ** 2 for example in examples)) for index in range(width))
    safe_scales = tuple(scale if scale > 1e-12 else 1.0 for scale in scales)
    target_mean = fmean(example.target for example in examples)
    gram = [[0.0 for _ in range(width)] for _ in range(width)]
    covariance = [0.0 for _ in range(width)]
    for example in examples:
        standardized = tuple((value - means[index]) / safe_scales[index] for index, value in enumerate(example.features))
        centered_target = example.target - target_mean
        for left in range(width):
            covariance[left] += standardized[left] * centered_target
            for right in range(width):
                gram[left][right] += standardized[left] * standardized[right]
    count = float(len(examples))
    return means, safe_scales, target_mean, [[value / count for value in row] for row in gram], [value / count for value in covariance]


def _solve_linear_system(matrix: list[list[float]], values: list[float]) -> tuple[float, ...]:
    """Solve a small full-rank system with deterministic partial pivoting."""
    size = len(values)
    augmented = [row[:] + [values[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) <= 1e-12:
            raise DataQualityError("regularized linear system is singular")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [value - factor * pivot_value for value, pivot_value in zip(augmented[row], augmented[column])]
    return tuple(augmented[index][-1] for index in range(size))


def _soft_threshold(value: float, penalty: float) -> float:
    if value > penalty:
        return value - penalty
    if value < -penalty:
        return value + penalty
    return 0.0


def fit_regularized_model(examples: Sequence[TrainingExample], *, family: str, l1_penalty: float, l2_penalty: float) -> LinearModel:
    if family not in {"ridge", "elastic_net"}:
        raise DataQualityError("only ridge and elastic_net are supported")
    if l1_penalty < 0 or l2_penalty <= 0 or (family == "ridge" and l1_penalty != 0):
        raise DataQualityError("invalid regularization penalties")
    means, scales, target_mean, gram, covariance = _fit_statistics(examples)
    width = len(FEATURE_COLUMNS)
    if family == "ridge":
        system = [row[:] for row in gram]
        for index in range(width):
            system[index][index] += l2_penalty
        coefficients = _solve_linear_system(system, covariance)
    else:
        coefficients = [0.0] * width
        for _ in range(20_000):
            largest_change = 0.0
            for index in range(width):
                partial = covariance[index] - sum(
                    gram[index][other] * coefficients[other] for other in range(width) if other != index
                )
                updated = _soft_threshold(partial, l1_penalty) / (gram[index][index] + l2_penalty)
                largest_change = max(largest_change, abs(updated - coefficients[index]))
                coefficients[index] = updated
            if largest_change < 1e-10:
                break
        else:  # pragma: no cover - six dimensions should converge comfortably
            raise DataQualityError("elastic-net coordinate descent did not converge")
        coefficients = tuple(coefficients)
    return LinearModel(family, l1_penalty, l2_penalty, means, scales, target_mean, tuple(coefficients))


def _metrics(model: LinearModel, examples: Sequence[TrainingExample]) -> dict[str, float]:
    errors = [model.predict(example.features) - example.target for example in examples]
    targets = [example.target for example in examples]
    return {
        "example_count": len(examples),
        "rmse": math.sqrt(fmean(error * error for error in errors)),
        "mae": fmean(abs(error) for error in errors),
        "mean_target": fmean(targets),
        "mean_prediction": fmean(model.predict(example.features) for example in examples),
    }


def _fold_examples(examples: Sequence[TrainingExample], fold: TimeOrderedFold) -> tuple[list[TrainingExample], list[TrainingExample]]:
    train = [example for example in examples if example.score_date <= fold.training_end_date]
    validation = [example for example in examples if fold.validation_start_date <= example.score_date <= fold.validation_end_date]
    if not train or not validation:
        raise DataQualityError("fold has no training or validation examples")
    return train, validation


def _candidate_grid() -> tuple[tuple[str, float, float], ...]:
    return (
        *( ("ridge", 0.0, value) for value in (0.001, 0.01, 0.1, 1.0) ),
        *( ("elastic_net", l1, l2) for l1 in (0.0001, 0.001, 0.01) for l2 in (0.001, 0.01, 0.1) ),
    )


def run_development_experiment(examples: Sequence[TrainingExample]) -> dict[str, object]:
    """Evaluate a fixed regularization grid on purged chronological folds only."""
    folds = build_time_ordered_folds(examples)
    candidates: list[dict[str, object]] = []
    for family, l1_penalty, l2_penalty in _candidate_grid():
        fold_results: list[dict[str, object]] = []
        for fold in folds:
            train, validation = _fold_examples(examples, fold)
            model = fit_regularized_model(train, family=family, l1_penalty=l1_penalty, l2_penalty=l2_penalty)
            fold_results.append({
                "fold": fold.fold_number,
                "training_end_date": fold.training_end_date.isoformat(),
                "purged_sessions": [fold.purge_start_date.isoformat(), fold.purge_end_date.isoformat()],
                "validation_window": [fold.validation_start_date.isoformat(), fold.validation_end_date.isoformat()],
                **_metrics(model, validation),
            })
        candidates.append({
            "family": family,
            "l1_penalty": l1_penalty,
            "l2_penalty": l2_penalty,
            "folds": fold_results,
            "mean_rmse": fmean(float(result["rmse"]) for result in fold_results),
            "mean_mae": fmean(float(result["mae"]) for result in fold_results),
        })
    candidates.sort(key=lambda item: (float(item["mean_rmse"]), float(item["mean_mae"]), str(item["family"]), float(item["l1_penalty"]), float(item["l2_penalty"])))
    selected = candidates[0]
    final_training_end = max(example.score_date for example in examples)
    final_model = fit_regularized_model(
        examples, family=str(selected["family"]), l1_penalty=float(selected["l1_penalty"]), l2_penalty=float(selected["l2_penalty"])
    )
    return {
        "experiment_type": "development_only_regularized_linear_selection",
        "data_capability_tier": "B",
        "cohort_warning": "Current S&P 500 survivors only; not an unbiased historical-performance claim.",
        "holdout_used": False,
        "holdout_excluded_from_input": True,
        "feature_columns": list(FEATURE_COLUMNS),
        "target_column": TARGET_COLUMN,
        "purge_sessions": PURGE_SESSIONS,
        "development_examples": len(examples),
        "development_start_date": min(example.score_date for example in examples).isoformat(),
        "development_end_date": final_training_end.isoformat(),
        "candidates": candidates,
        "selected_candidate": selected,
        "final_development_model": {
            "family": final_model.family,
            "l1_penalty": final_model.l1_penalty,
            "l2_penalty": final_model.l2_penalty,
            "training_end_date": final_training_end.isoformat(),
            "feature_means": list(final_model.feature_means),
            "feature_scales": list(final_model.feature_scales),
            "target_mean": final_model.target_mean,
            "coefficients": list(final_model.coefficients),
        },
        "next_step": "Final holdout remains untouched. Review this development-only experiment before any locked-holdout evaluation.",
    }


def _settings(env_file: Path):
    from .config import Settings

    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def record_experiment(*, database_url: str, experiment_key: str, model_version: str, feature_registry_hash: str,
                      training_end_date: date, validation_end_date: date, result_uri: str) -> None:
    """Append one immutable record after proving the experiment is pre-holdout."""
    if validation_end_date >= HOLDOUT_START:
        raise DataQualityError("development experiment validation reaches the locked holdout")
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT holdout_period_id FROM quantrade.holdout_periods WHERE protocol_version = %s", ("tier_b_20d_v1",))
        holdout = cursor.fetchone()
        if holdout is None:
            raise DataQualityError("locked Tier-B holdout is missing")
        cursor.execute(
            """INSERT INTO quantrade.experiment_records
               (experiment_key, holdout_period_id, created_at, model_version, feature_registry_hash,
                training_end_date, validation_end_date, result_uri)
               VALUES (%s, %s, now(), %s, %s, %s, %s, %s)""",
            (experiment_key, holdout[0], model_version, feature_registry_hash, training_end_date, validation_end_date, result_uri),
        )
        connection.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run purged, development-only ridge and elastic-net selection")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--experiment-key", default="tier_b_regularized_linear_development_v1")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    if arguments.output.exists():
        raise DataQualityError(f"refusing to overwrite immutable experiment result: {arguments.output}")
    examples = load_development_examples(arguments.input)
    result = run_development_experiment(examples)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with arguments.input.open("r", encoding="utf-8", newline="") as handle:
        feature_hashes = {row["feature_registry_hash"] for row in csv.DictReader(handle) if row.get("partition") == "development"}
    if len(feature_hashes) != 1:
        raise DataQualityError("development dataset must use exactly one feature registry hash")
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    record_experiment(
        database_url=settings.database_url,
        experiment_key=arguments.experiment_key,
        model_version="tier_b_regularized_linear_development_v1",
        feature_registry_hash=feature_hashes.pop(),
        training_end_date=max(example.score_date for example in examples),
        validation_end_date=date.fromisoformat(str(result["selected_candidate"]["folds"][-1]["validation_window"][1])),
        result_uri=arguments.output.resolve().as_uri(),
    )
    selected = result["selected_candidate"]
    print(f"development_examples={len(examples)}; selected={selected['family']}; mean_rmse={selected['mean_rmse']:.8f}; holdout_used=false")


if __name__ == "__main__":
    main()
