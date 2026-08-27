"""Reporting-only diagnostics for the already-consumed Tier-B holdout.

This module never fits, selects, or modifies a model. It applies the frozen
development artifact to the immutable holdout partition and compares each raw
20-session SPY-relative forecast with its completed label.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
import math
from pathlib import Path
from statistics import fmean, median
from typing import Iterable

from .historical_training_export import HOLDOUT_END, HOLDOUT_START
from .holdout_evaluation import load_frozen_model
from .quality import DataQualityError
from .regularized_training import FEATURE_COLUMNS, LinearModel


@dataclass(frozen=True, slots=True)
class PredictionObservation:
    score_date: date
    security_id: str
    ticker: str
    predicted_relative_return: float
    actual_relative_return: float


def _require_reporting_confirmation(confirmed: bool) -> None:
    if not confirmed:
        raise DataQualityError(
            "consumed holdout is reporting-only; rerun with --confirm-consumed-holdout"
        )


def _validate_dataset_manifest(dataset_path: Path, manifest_path: Path) -> dict[str, object]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected_hash = str(manifest["content_sha256"])
        holdout = manifest["holdout"]
        if manifest["dataset_key"] != "sp500_current_survivors_20d" or manifest["dataset_version"] != "v1":
            raise DataQualityError("diagnostics require the frozen Tier-B dataset v1")
        if holdout["start_date"] != HOLDOUT_START.isoformat() or holdout["end_date"] != HOLDOUT_END.isoformat():
            raise DataQualityError("dataset manifest holdout dates do not match the locked period")
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid training dataset manifest") from error
    actual_hash = sha256(dataset_path.read_bytes()).hexdigest()
    if actual_hash != expected_hash:
        raise DataQualityError("training dataset content hash does not match its manifest")
    return manifest


def load_holdout_observations(path: Path, model: LinearModel) -> tuple[PredictionObservation, ...]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"partition", "score_date", "security_id", "ticker", "benchmark_relative_return", *FEATURE_COLUMNS}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise DataQualityError("training CSV does not have the required diagnostic schema")
        observations: list[PredictionObservation] = []
        seen: set[tuple[date, str]] = set()
        for line_number, row in enumerate(reader, start=2):
            if row.get("partition") != "holdout":
                continue
            try:
                score_date = date.fromisoformat(str(row["score_date"]))
                security_id = str(row["security_id"])
                features = tuple(float(row[column]) for column in FEATURE_COLUMNS)
                actual = float(row["benchmark_relative_return"])
                prediction = model.predict(features)
            except (KeyError, TypeError, ValueError) as error:
                raise DataQualityError(f"invalid diagnostic CSV line {line_number}") from error
            identity = (score_date, security_id)
            if not HOLDOUT_START <= score_date <= HOLDOUT_END:
                raise DataQualityError(f"holdout diagnostic line {line_number} is outside the locked period")
            if identity in seen:
                raise DataQualityError(f"duplicate holdout diagnostic example: {score_date}:{security_id}")
            if not all(math.isfinite(value) for value in (*features, actual, prediction)):
                raise DataQualityError(f"non-finite diagnostic value at line {line_number}")
            seen.add(identity)
            observations.append(PredictionObservation(
                score_date, security_id, str(row["ticker"]), prediction, actual,
            ))
    if not observations:
        raise DataQualityError("training CSV contains no holdout observations")
    return tuple(observations)


def _pearson(left: Iterable[float], right: Iterable[float]) -> float:
    x = tuple(left)
    y = tuple(right)
    if len(x) != len(y) or len(x) < 2:
        raise DataQualityError("correlation requires paired observations")
    x_mean = fmean(x)
    y_mean = fmean(y)
    numerator = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y))
    denominator = math.sqrt(sum((a - x_mean) ** 2 for a in x) * sum((b - y_mean) ** 2 for b in y))
    return numerator / denominator if denominator else 0.0


def _tie_ranks(values: Iterable[float]) -> tuple[float, ...]:
    source = tuple(values)
    ordered = sorted(range(len(source)), key=lambda index: (source[index], index))
    ranks = [0.0] * len(source)
    position = 0
    while position < len(ordered):
        end = position
        while end + 1 < len(ordered) and source[ordered[end + 1]] == source[ordered[position]]:
            end += 1
        rank = (position + end) / 2 + 1
        for ordered_index in ordered[position:end + 1]:
            ranks[ordered_index] = rank
        position = end + 1
    return tuple(ranks)


def _spearman(observations: Iterable[PredictionObservation]) -> float:
    rows = tuple(observations)
    return _pearson(
        _tie_ranks(row.predicted_relative_return for row in rows),
        _tie_ranks(row.actual_relative_return for row in rows),
    )


def _metrics(rows: Iterable[PredictionObservation]) -> dict[str, object]:
    source = tuple(rows)
    errors = tuple(row.predicted_relative_return - row.actual_relative_return for row in source)
    directional_hits = sum(
        (row.predicted_relative_return >= 0) == (row.actual_relative_return >= 0)
        for row in source
    )
    predictions = tuple(row.predicted_relative_return for row in source)
    actuals = tuple(row.actual_relative_return for row in source)
    prediction_mean = fmean(predictions)
    actual_mean = fmean(actuals)
    prediction_variance = sum((value - prediction_mean) ** 2 for value in predictions)
    calibration_slope = (
        sum((prediction - prediction_mean) * (actual - actual_mean) for prediction, actual in zip(predictions, actuals))
        / prediction_variance
        if prediction_variance else 0.0
    )
    return {
        "example_count": len(source),
        "mean_prediction": prediction_mean,
        "mean_actual": actual_mean,
        "mean_error_bias": fmean(errors),
        "mae": fmean(abs(error) for error in errors),
        "rmse": math.sqrt(fmean(error * error for error in errors)),
        "directional_accuracy": directional_hits / len(source),
        "pearson_correlation": _pearson(predictions, actuals),
        "calibration_intercept": actual_mean - calibration_slope * prediction_mean,
        "calibration_slope": calibration_slope,
        "minimum_prediction": min(predictions),
        "maximum_prediction": max(predictions),
    }


def _by_score_date(rows: Iterable[PredictionObservation]) -> dict[date, tuple[PredictionObservation, ...]]:
    grouped: dict[date, list[PredictionObservation]] = {}
    for row in rows:
        grouped.setdefault(row.score_date, []).append(row)
    return {score_date: tuple(values) for score_date, values in grouped.items()}


def _decile_report(rows_by_date: dict[date, tuple[PredictionObservation, ...]]) -> list[dict[str, object]]:
    buckets: dict[int, list[PredictionObservation]] = {index: [] for index in range(1, 11)}
    for rows in rows_by_date.values():
        ordered = sorted(rows, key=lambda row: (row.predicted_relative_return, row.security_id))
        for index, row in enumerate(ordered):
            decile = min(10, index * 10 // len(ordered) + 1)
            buckets[decile].append(row)
    return [
        {
            "decile": decile,
            "label": "lowest predictions" if decile == 1 else "highest predictions" if decile == 10 else "",
            "example_count": len(bucket),
            "mean_prediction": fmean(row.predicted_relative_return for row in bucket),
            "mean_actual": fmean(row.actual_relative_return for row in bucket),
            "directional_accuracy": sum(
                (row.predicted_relative_return >= 0) == (row.actual_relative_return >= 0) for row in bucket
            ) / len(bucket),
        }
        for decile, bucket in buckets.items()
    ]


def _monthly_formation_report(rows_by_date: dict[date, tuple[PredictionObservation, ...]]) -> dict[str, object]:
    dates_by_month: dict[tuple[int, int], list[date]] = {}
    for score_date in rows_by_date:
        dates_by_month.setdefault((score_date.year, score_date.month), []).append(score_date)
    periods: list[dict[str, object]] = []
    for dates in dates_by_month.values():
        formation_date = max(dates)
        selected = sorted(
            rows_by_date[formation_date],
            key=lambda row: (-row.predicted_relative_return, row.security_id),
        )[:20]
        periods.append({
            "formation_date": formation_date.isoformat(),
            "position_count": len(selected),
            "mean_prediction": fmean(row.predicted_relative_return for row in selected),
            "mean_actual_relative_return": fmean(row.actual_relative_return for row in selected),
            "positive_relative_return": fmean(row.actual_relative_return for row in selected) > 0,
        })
    periods.sort(key=lambda item: str(item["formation_date"]))
    return {
        "formation_period_count": len(periods),
        "periods_beating_spy": sum(bool(period["positive_relative_return"]) for period in periods),
        "mean_predicted_relative_return": fmean(float(period["mean_prediction"]) for period in periods),
        "mean_actual_relative_return": fmean(float(period["mean_actual_relative_return"]) for period in periods),
        "periods": periods,
    }


def build_prediction_diagnostics(rows: Iterable[PredictionObservation]) -> dict[str, object]:
    source = tuple(rows)
    rows_by_date = _by_score_date(source)
    daily_ics = tuple(_spearman(values) for values in rows_by_date.values())
    top_decile = []
    bottom_decile = []
    for values in rows_by_date.values():
        ordered = sorted(values, key=lambda row: (row.predicted_relative_return, row.security_id))
        size = max(1, len(ordered) // 10)
        bottom_decile.extend(ordered[:size])
        top_decile.extend(ordered[-size:])
    return {
        "status": "consumed_holdout_reporting_complete",
        "reporting_only_no_model_selection": True,
        "holdout": {"start_date": HOLDOUT_START.isoformat(), "end_date": HOLDOUT_END.isoformat()},
        "target": "20-session split-adjusted stock return minus matching SPY return",
        "all_completed_examples": _metrics(source),
        "cross_sectional_rank_quality": {
            "score_date_count": len(rows_by_date),
            "mean_daily_spearman_ic": fmean(daily_ics),
            "median_daily_spearman_ic": median(daily_ics),
            "positive_ic_date_share": sum(value > 0 for value in daily_ics) / len(daily_ics),
            "top_decile_mean_actual_relative_return": fmean(row.actual_relative_return for row in top_decile),
            "bottom_decile_mean_actual_relative_return": fmean(row.actual_relative_return for row in bottom_decile),
            "top_minus_bottom_actual_spread": (
                fmean(row.actual_relative_return for row in top_decile)
                - fmean(row.actual_relative_return for row in bottom_decile)
            ),
        },
        "prediction_deciles": _decile_report(rows_by_date),
        "monthly_top_20": _monthly_formation_report(rows_by_date),
        "limitations": [
            "Tier B current-survivors cohort creates survivorship bias.",
            "Static current-sector groupings are not historical point-in-time classifications.",
            "The final holdout has already been observed and cannot be used for future model selection or tuning.",
            "Overlapping daily 20-session labels are not independent portfolio trials.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Report frozen-model predictions versus actual consumed-holdout outcomes")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--model-artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm-consumed-holdout", action="store_true")
    arguments = parser.parse_args()
    _require_reporting_confirmation(arguments.confirm_consumed_holdout)
    if arguments.output.exists():
        raise DataQualityError(f"refusing to overwrite immutable holdout diagnostics: {arguments.output}")
    dataset_manifest = _validate_dataset_manifest(arguments.input, arguments.dataset_manifest)
    model = load_frozen_model(arguments.model_artifact)
    observations = load_holdout_observations(arguments.input, model)
    report = build_prediction_diagnostics(observations)
    report["provenance"] = {
        "dataset_key": dataset_manifest["dataset_key"],
        "dataset_version": dataset_manifest["dataset_version"],
        "dataset_content_sha256": dataset_manifest["content_sha256"],
        "model_artifact_sha256": sha256(arguments.model_artifact.read_bytes()).hexdigest(),
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    metrics = report["all_completed_examples"]
    rank = report["cross_sectional_rank_quality"]
    print(
        f"holdout_examples={metrics['example_count']}; mae={metrics['mae']:.6f}; "
        f"rmse={metrics['rmse']:.6f}; mean_daily_ic={rank['mean_daily_spearman_ic']:.6f}"
    )


if __name__ == "__main__":
    main()
