"""Development-only calibration context for monthly model portfolios."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
from statistics import fmean

from .config import Settings
from .quality import DataQualityError
from .register_research_model import MODEL_VERSION
from .regularized_training import (
    TrainingExample,
    build_time_ordered_folds,
    fit_regularized_model,
    load_development_examples,
)
from .score_run import _dotenv_values


CONTEXT_SCHEMA_VERSION = "development_monthly_calibration_v1"
PORTFOLIO_SIZE = 20
LOWER_QUANTILE = 0.10
UPPER_QUANTILE = 0.90


@dataclass(frozen=True, slots=True)
class PredictionObservation:
    score_date: date
    prediction: float
    actual: float


@dataclass(frozen=True, slots=True)
class MonthlyBasketObservation:
    formation_date: date
    raw_prediction: float
    actual: float


def _quantile(values: list[float], probability: float) -> float:
    if not values or not 0 <= probability <= 1:
        raise DataQualityError("calibration quantile requires finite observations and a valid probability")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _linear_calibration(predictions: list[float], actuals: list[float]) -> tuple[float, float]:
    if len(predictions) != len(actuals) or len(predictions) < 10:
        raise DataQualityError("calibration requires at least ten paired observations")
    prediction_mean = fmean(predictions)
    actual_mean = fmean(actuals)
    variance = fmean((value - prediction_mean) ** 2 for value in predictions)
    if variance <= 1e-16:
        raise DataQualityError("calibration predictions have no usable variance")
    covariance = fmean(
        (prediction - prediction_mean) * (actual - actual_mean)
        for prediction, actual in zip(predictions, actuals)
    )
    slope = covariance / variance
    if not math.isfinite(slope):
        raise DataQualityError("development calibration slope must be finite")
    return actual_mean - slope * prediction_mean, slope


def _selected_parameters(experiment: dict[str, object]) -> tuple[str, float, float]:
    try:
        selected = experiment["selected_candidate"]
        final_model = experiment["final_development_model"]
        if not isinstance(selected, dict) or not isinstance(final_model, dict):
            raise TypeError
        parameters = (
            str(selected["family"]),
            float(selected["l1_penalty"]),
            float(selected["l2_penalty"]),
        )
        final_parameters = (
            str(final_model["family"]),
            float(final_model["l1_penalty"]),
            float(final_model["l2_penalty"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise DataQualityError("development experiment has invalid selected-model metadata") from error
    if parameters != final_parameters:
        raise DataQualityError("selected and final development models do not match")
    return parameters


def _out_of_fold_observations(
    examples: tuple[TrainingExample, ...], experiment: dict[str, object]
) -> tuple[PredictionObservation, ...]:
    if experiment.get("holdout_used") is not False or experiment.get("holdout_excluded_from_input") is not True:
        raise DataQualityError("prediction context source must exclude the locked holdout")
    family, l1_penalty, l2_penalty = _selected_parameters(experiment)
    observations: list[PredictionObservation] = []
    for fold in build_time_ordered_folds(examples):
        training = [example for example in examples if example.score_date <= fold.training_end_date]
        validation = [
            example for example in examples
            if fold.validation_start_date <= example.score_date <= fold.validation_end_date
        ]
        if not training or not validation:
            raise DataQualityError("calibration fold has no training or validation observations")
        model = fit_regularized_model(
            training,
            family=family,
            l1_penalty=l1_penalty,
            l2_penalty=l2_penalty,
        )
        observations.extend(
            PredictionObservation(example.score_date, model.predict(example.features), example.target)
            for example in validation
        )
    if not observations:
        raise DataQualityError("development calibration produced no out-of-fold observations")
    return tuple(observations)


def _monthly_baskets(
    observations: tuple[PredictionObservation, ...]
) -> tuple[MonthlyBasketObservation, ...]:
    by_date: dict[date, list[PredictionObservation]] = defaultdict(list)
    for observation in observations:
        by_date[observation.score_date].append(observation)
    dates_by_month: dict[tuple[int, int], list[date]] = defaultdict(list)
    for score_date in by_date:
        dates_by_month[(score_date.year, score_date.month)].append(score_date)
    baskets: list[MonthlyBasketObservation] = []
    for month_dates in dates_by_month.values():
        formation_date = max(month_dates)
        candidates = sorted(
            by_date[formation_date], key=lambda item: item.prediction, reverse=True
        )
        if len(candidates) < PORTFOLIO_SIZE:
            continue
        selected = candidates[:PORTFOLIO_SIZE]
        baskets.append(MonthlyBasketObservation(
            formation_date,
            fmean(item.prediction for item in selected),
            fmean(item.actual for item in selected),
        ))
    baskets.sort(key=lambda item: item.formation_date)
    if len(baskets) < 10:
        raise DataQualityError("monthly calibration requires at least ten development formations")
    return tuple(baskets)


def summarize_basket_calibration(
    baskets: tuple[MonthlyBasketObservation, ...]
) -> tuple[str, float | None, float | None, list[float], float]:
    """Return supported calibration parameters or raw-output residuals."""
    predictions = [item.raw_prediction for item in baskets]
    actuals = [item.actual for item in baskets]
    observed_intercept, observed_slope = _linear_calibration(predictions, actuals)
    calibration_supported = observed_slope > 0
    status = "supported" if calibration_supported else "unsupported_nonpositive_slope"
    residuals = [
        actual - (
            observed_intercept + observed_slope * prediction
            if calibration_supported
            else prediction
        )
        for prediction, actual in zip(predictions, actuals)
    ]
    return (
        status,
        observed_intercept if calibration_supported else None,
        observed_slope if calibration_supported else None,
        residuals,
        observed_slope,
    )


def build_prediction_context(
    *, examples: tuple[TrainingExample, ...], experiment_bytes: bytes
) -> dict[str, object]:
    """Build calibration and empirical error context from purged development folds only."""
    try:
        experiment = json.loads(experiment_bytes)
    except json.JSONDecodeError as error:
        raise DataQualityError("development experiment is not valid JSON") from error
    if not isinstance(experiment, dict):
        raise DataQualityError("development experiment must be a JSON object")
    observations = _out_of_fold_observations(examples, experiment)
    baskets = _monthly_baskets(observations)
    calibration_status, intercept, slope, residuals, observed_slope = summarize_basket_calibration(baskets)
    lower = _quantile(residuals, LOWER_QUANTILE)
    upper = _quantile(residuals, UPPER_QUANTILE)
    calibration_values = [observed_slope, lower, upper]
    calibration_values.extend(value for value in (intercept, slope) if value is not None)
    if not all(math.isfinite(value) for value in calibration_values):
        raise DataQualityError("development calibration produced a non-finite result")
    return {
        "context_schema_version": CONTEXT_SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "benchmark_ticker": "SPY",
        "horizon_sessions": 20,
        "portfolio_size": PORTFOLIO_SIZE,
        "holdout_used": False,
        "holdout_excluded_from_input": True,
        "source_experiment_sha256": sha256(experiment_bytes).hexdigest(),
        "development_validation_start": min(item.score_date for item in observations).isoformat(),
        "development_validation_end": max(item.score_date for item in observations).isoformat(),
        "validation_example_count": len(observations),
        "monthly_formation_count": len(baskets),
        "basket_calibration": {
            "method": "ordinary least squares on purged out-of-fold monthly top-20 baskets",
            "status": calibration_status,
            "intercept": intercept,
            "slope": slope,
            "observed_development_slope": observed_slope,
        },
        "basket_empirical_error_range": {
            "lower_quantile": LOWER_QUANTILE,
            "upper_quantile": UPPER_QUANTILE,
            "lower_residual": lower,
            "upper_residual": upper,
        },
        "limitations": [
            "Calibration uses development folds only; the consumed 2025-2026 holdout was not fitted.",
            "When calibration is unsupported, the range is centered on raw model output rather than a calibrated estimate.",
            "The range is an empirical development error range, not a confidence guarantee.",
            "Monthly formations overlap through 20-session outcomes and are not independent trials.",
            "Tier B current-survivors data remains survivorship-biased with static sector classifications.",
        ],
    }


def serialize_prediction_context(context: dict[str, object]) -> bytes:
    return (json.dumps(context, indent=2, sort_keys=True) + "\n").encode("utf-8")


def record_prediction_context(
    *, database_url: str, context: dict[str, object], artifact_uri: str, artifact_sha256: str
) -> None:
    calibration = context["basket_calibration"]
    error_range = context["basket_empirical_error_range"]
    if not isinstance(calibration, dict) or not isinstance(error_range, dict):
        raise DataQualityError("prediction context has invalid calibration metadata")
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO quantrade.model_prediction_contexts
                   (model_version, context_schema_version, benchmark_ticker, horizon_sessions,
                    portfolio_size, calibration_status, calibration_intercept, calibration_slope,
                    residual_lower_quantile, residual_upper_quantile,
                    development_validation_start, development_validation_end,
                    validation_example_count, monthly_formation_count, artifact_uri,
                    artifact_sha256, source_experiment_sha256, holdout_used, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, %s)""",
            (
                context["model_version"], context["context_schema_version"],
                context["benchmark_ticker"], context["horizon_sessions"],
                context["portfolio_size"], calibration["status"],
                calibration["intercept"], calibration["slope"],
                error_range["lower_residual"], error_range["upper_residual"],
                context["development_validation_start"], context["development_validation_end"],
                context["validation_example_count"], context["monthly_formation_count"],
                artifact_uri, artifact_sha256, context["source_experiment_sha256"],
                datetime.now(timezone.utc),
            ),
        )
        connection.commit()


def _settings(env_file: Path) -> Settings:
    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build development-only model prediction context")
    parser.add_argument("--training-dataset", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    if arguments.output.exists():
        raise DataQualityError(f"refusing to overwrite immutable prediction context: {arguments.output}")
    experiment_bytes = arguments.experiment.read_bytes()
    context = build_prediction_context(
        examples=load_development_examples(arguments.training_dataset),
        experiment_bytes=experiment_bytes,
    )
    artifact_bytes = serialize_prediction_context(context)
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_bytes(artifact_bytes)
    try:
        record_prediction_context(
            database_url=settings.database_url,
            context=context,
            artifact_uri=arguments.output.resolve().as_uri(),
            artifact_sha256=sha256(artifact_bytes).hexdigest(),
        )
    except Exception:
        arguments.output.unlink(missing_ok=True)
        raise
    print(
        f"model={MODEL_VERSION}; monthly_formations={context['monthly_formation_count']}; "
        f"validation_examples={context['validation_example_count']}; holdout_used=false"
    )


if __name__ == "__main__":
    main()
