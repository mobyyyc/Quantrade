"""Nested chronological Phase 9B model comparison on monthly cross-sections."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
import math
from pathlib import Path
from statistics import fmean, median
from typing import Callable, Sequence

from .monthly_model_dataset import (
    BASE_FEATURES, DATASET_KEY, DATASET_VERSION, MARKET_FEATURES, SECTOR_FEATURES,
)
from .quality import DataQualityError


EXPERIMENT_KEY = "tier_b_monthly_feature_family_comparison"
EXPERIMENT_VERSION = "v1"
COST_CASES = (0.0005, 0.0010, 0.0025, 0.0050)
OUTER_BLOCKS = (
    (date(2023, 7, 1), date(2023, 12, 31)),
    (date(2024, 1, 1), date(2024, 6, 30)),
    (date(2024, 7, 1), date(2024, 12, 31)),
    (date(2025, 1, 1), date(2025, 6, 30)),
)
MODEL_KEYS = ("active_elastic_net", "signed_family_composite", "ridge", "low_l1_elastic_net", "robust_ridge")


@dataclass(frozen=True, slots=True)
class Example:
    formation_date: date
    outcome_date: date
    security_id: str
    base: tuple[float, ...]
    market: tuple[float, ...]
    sector: tuple[float, ...]
    target: float
    security_return: float
    benchmark_return: float
    weight: float
    spy_trend: float
    spy_volatility: float


@dataclass(frozen=True, slots=True)
class Prediction:
    model_key: str
    transform: str
    fold: int
    formation_date: date
    security_id: str
    predicted: float
    target: float
    security_return: float
    benchmark_return: float
    regime: str


@dataclass(frozen=True, slots=True)
class LinearModel:
    means: tuple[float, ...]
    scales: tuple[float, ...]
    intercept: float
    coefficients: tuple[float, ...]

    def predict(self, values: Sequence[float]) -> float:
        return self.intercept + sum(
            coefficient * ((value - mean) / scale)
            for coefficient, value, mean, scale in zip(self.coefficients, values, self.means, self.scales)
        )


def _validate_dataset(dataset: Path, manifest: Path) -> dict[str, object]:
    try:
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid monthly model dataset manifest") from error
    if metadata.get("dataset_key") != DATASET_KEY or metadata.get("dataset_version") != DATASET_VERSION:
        raise DataQualityError("unexpected monthly model dataset version")
    if metadata.get("development_only") is not True or metadata.get("holdout_used") is not False:
        raise DataQualityError("comparison dataset is not development-only")
    if sha256(dataset.read_bytes()).hexdigest() != metadata.get("content_sha256"):
        raise DataQualityError("monthly model dataset does not match its manifest")
    return metadata


def load_examples(dataset: Path, manifest: Path) -> tuple[tuple[Example, ...], dict[str, object]]:
    metadata = _validate_dataset(dataset, manifest)
    examples: list[Example] = []
    seen: set[tuple[date, str]] = set()
    with dataset.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "formation_date", "outcome_date", "security_id", "benchmark_relative_return",
            "security_return", "benchmark_return", "formation_weight", "spy_trend_60d",
            "spy_volatility_60d", *BASE_FEATURES, *MARKET_FEATURES, *SECTOR_FEATURES,
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise DataQualityError("monthly model dataset lacks comparison columns")
        for line, row in enumerate(reader, start=2):
            try:
                formation = date.fromisoformat(row["formation_date"])
                outcome = date.fromisoformat(row["outcome_date"])
                identity = formation, row["security_id"]
                values = (
                    *[float(row[item]) for item in BASE_FEATURES],
                    *[float(row[item]) for item in MARKET_FEATURES],
                    *[float(row[item]) for item in SECTOR_FEATURES],
                    float(row["benchmark_relative_return"]), float(row["security_return"]),
                    float(row["benchmark_return"]), float(row["formation_weight"]),
                    float(row["spy_trend_60d"]), float(row["spy_volatility_60d"]),
                )
            except (KeyError, TypeError, ValueError) as error:
                raise DataQualityError(f"invalid monthly model row {line}") from error
            if identity in seen or not all(math.isfinite(item) for item in values):
                raise DataQualityError(f"duplicate or non-finite monthly model row {line}")
            seen.add(identity)
            width_base, width_new = len(BASE_FEATURES), len(MARKET_FEATURES)
            examples.append(Example(
                formation, outcome, row["security_id"], tuple(values[:width_base]),
                tuple(values[width_base:width_base + width_new]),
                tuple(values[width_base + width_new:width_base + 2 * width_new]),
                values[-6], values[-5], values[-4], values[-3], values[-2], values[-1],
            ))
    if not examples:
        raise DataQualityError("monthly model dataset has no examples")
    return tuple(sorted(examples, key=lambda item: (item.formation_date, item.security_id))), metadata


def _solve(matrix: list[list[float]], values: list[float]) -> tuple[float, ...]:
    augmented = [row[:] + [values[index]] for index, row in enumerate(matrix)]
    for column in range(len(values)):
        pivot = max(range(column, len(values)), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) <= 1e-12:
            raise DataQualityError("regularized monthly linear system is singular")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [item / divisor for item in augmented[column]]
        for row in range(len(values)):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [item - factor * pivot_item for item, pivot_item in zip(augmented[row], augmented[column])]
    return tuple(augmented[index][-1] for index in range(len(values)))


def fit_linear_model(
    examples: Sequence[Example], features: Callable[[Example], tuple[float, ...]], *,
    family: str, l1: float, l2: float, huber_delta: float = 1.5,
) -> LinearModel:
    if not examples or l1 < 0 or l2 <= 0:
        raise DataQualityError("invalid monthly linear fit")
    matrix = [features(item) for item in examples]
    width = len(matrix[0])
    weights = [item.weight for item in examples]
    means = tuple(
        sum(weight * row[index] for weight, row in zip(weights, matrix)) / sum(weights)
        for index in range(width)
    )
    scales = tuple(
        math.sqrt(sum(weight * (row[index] - means[index]) ** 2 for weight, row in zip(weights, matrix)) / sum(weights))
        for index in range(width)
    )
    scales = tuple(item if item > 1e-12 else 1.0 for item in scales)
    standardized = [tuple((value - means[index]) / scales[index] for index, value in enumerate(row)) for row in matrix]
    targets = [item.target for item in examples]
    robust_weights = [1.0] * len(examples)
    coefficients: tuple[float, ...] = tuple(0.0 for _ in range(width))
    intercept = 0.0
    iterations = 10 if family == "robust" else 1
    for _ in range(iterations):
        effective = [base * robust for base, robust in zip(weights, robust_weights)]
        total = sum(effective)
        intercept = sum(weight * target for weight, target in zip(effective, targets)) / total
        gram = [[0.0] * width for _ in range(width)]
        covariance = [0.0] * width
        for weight, row, target in zip(effective, standardized, targets):
            centered = target - intercept
            for left in range(width):
                covariance[left] += weight * row[left] * centered / total
                for right in range(width):
                    gram[left][right] += weight * row[left] * row[right] / total
        if family in {"ridge", "robust"}:
            for index in range(width):
                gram[index][index] += l2
            coefficients = _solve(gram, covariance)
        elif family == "elastic_net":
            working = list(coefficients)
            for _iteration in range(20_000):
                largest = 0.0
                for index in range(width):
                    partial = covariance[index] - sum(gram[index][other] * working[other] for other in range(width) if other != index)
                    threshold = math.copysign(max(abs(partial) - l1, 0.0), partial)
                    updated = threshold / (gram[index][index] + l2)
                    largest = max(largest, abs(updated - working[index]))
                    working[index] = updated
                if largest < 1e-10:
                    break
            coefficients = tuple(working)
        else:
            raise DataQualityError("unsupported monthly model family")
        if family == "robust":
            residuals = [
                target - (intercept + sum(coefficient * value for coefficient, value in zip(coefficients, row)))
                for target, row in zip(targets, standardized)
            ]
            scale = median(abs(item) for item in residuals) * 1.4826
            if scale <= 1e-12:
                break
            robust_weights = [min(1.0, huber_delta * scale / abs(item)) if item else 1.0 for item in residuals]
    return LinearModel(means, scales, intercept, coefficients)


def _rank(values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(values.items(), key=lambda item: (item[1], item[0]))
    ranks: dict[str, float] = {}
    index = 0
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[index][1]:
            end += 1
        rank = (index + end) / 2.0
        for key, _ in ordered[index:end + 1]:
            ranks[key] = rank
        index = end + 1
    return ranks


def spearman(pairs: Sequence[tuple[str, float, float]]) -> float:
    if len(pairs) < 2:
        return 0.0
    predicted = _rank({key: prediction for key, prediction, _ in pairs})
    actual = _rank({key: target for key, _, target in pairs})
    left = [predicted[key] for key, _, _ in pairs]
    right = [actual[key] for key, _, _ in pairs]
    lm, rm = fmean(left), fmean(right)
    numerator = sum((x - lm) * (y - rm) for x, y in zip(left, right))
    denominator = math.sqrt(sum((x - lm) ** 2 for x in left) * sum((y - rm) ** 2 for y in right))
    return numerator / denominator if denominator else 0.0


def _feature_selector(model_key: str, transform: str):
    def selected(item: Example) -> tuple[float, ...]:
        additions = item.market if transform == "market" else item.sector
        return item.base if model_key == "active_elastic_net" else (*item.base, *additions)
    return selected


def _grid(model_key: str):
    if model_key == "active_elastic_net":
        return tuple(("elastic_net", l1, l2) for l1 in (0.0001, 0.001) for l2 in (0.001, 0.01, 0.1))
    if model_key == "ridge":
        return tuple(("ridge", 0.0, l2) for l2 in (0.001, 0.01, 0.1, 1.0))
    if model_key == "low_l1_elastic_net":
        return tuple(("elastic_net", l1, l2) for l1 in (0.0001, 0.0005) for l2 in (0.001, 0.01, 0.1))
    if model_key == "robust_ridge":
        return tuple(("robust", 0.0, l2) for l2 in (0.001, 0.01, 0.1))
    return ()


def _inner_select(model_key: str, transform: str, training: Sequence[Example]):
    dates = sorted({item.formation_date for item in training})
    if len(dates) < 8:
        raise DataQualityError("nested monthly tuning requires eight prior formations")
    validation_dates = set(dates[-3:])
    validation_start = min(validation_dates)
    inner_train = [item for item in training if item.outcome_date < validation_start]
    inner_validation = [item for item in training if item.formation_date in validation_dates]
    if not inner_train or not inner_validation:
        raise DataQualityError("inner chronological split is empty after label-overlap purge")
    selector = _feature_selector(model_key, transform)
    candidates = []
    for family, l1, l2 in _grid(model_key):
        model = fit_linear_model(inner_train, selector, family=family, l1=l1, l2=l2)
        grouped: dict[date, list[tuple[str, float, float]]] = defaultdict(list)
        for item in inner_validation:
            grouped[item.formation_date].append((item.security_id, model.predict(selector(item)), item.target))
        score = fmean(spearman(values) for values in grouped.values())
        candidates.append((score, -l1, -l2, family, l1, l2))
    _, _, _, family, l1, l2 = max(candidates)
    return family, l1, l2


def build_oof_predictions(examples: Sequence[Example], *, transform: str):
    predictions: list[Prediction] = []
    fit_records: list[dict[str, object]] = []
    for fold, (start, end) in enumerate(OUTER_BLOCKS, start=1):
        validation = [item for item in examples if start <= item.formation_date <= end]
        if not validation:
            raise DataQualityError(f"outer fold {fold} has no validation examples")
        validation_start = min(item.formation_date for item in validation)
        training = [item for item in examples if item.outcome_date < validation_start]
        if not training:
            raise DataQualityError(f"outer fold {fold} has no purged training examples")
        volatility_threshold = median(item.spy_volatility for item in training)
        for model_key in MODEL_KEYS:
            selector = _feature_selector(model_key, transform)
            coefficients: tuple[float, ...] = ()
            tuning: dict[str, object] = {}
            if model_key == "signed_family_composite":
                predictor = lambda item: fmean(item.market if transform == "market" else item.sector)
            else:
                family, l1, l2 = _inner_select(model_key, transform, training)
                model = fit_linear_model(training, selector, family=family, l1=l1, l2=l2)
                coefficients = model.coefficients
                tuning = {"family": family, "l1": l1, "l2": l2}
                predictor = lambda item, fitted=model, choose=selector: fitted.predict(choose(item))
            fit_records.append({
                "fold": fold, "model_key": model_key, "transform": transform,
                "training_end": max(item.formation_date for item in training).isoformat(),
                "validation_start": validation_start.isoformat(), "validation_end": max(item.formation_date for item in validation).isoformat(),
                "training_rows": len(training), "validation_rows": len(validation),
                "tuning": tuning, "coefficients": list(coefficients),
            })
            for item in validation:
                regime = f"{'up' if item.spy_trend >= 0 else 'down'}_{'high_vol' if item.spy_volatility >= volatility_threshold else 'low_vol'}"
                predictions.append(Prediction(
                    model_key, transform, fold, item.formation_date, item.security_id,
                    predictor(item), item.target, item.security_return, item.benchmark_return, regime,
                ))
    return tuple(predictions), tuple(fit_records)


def metrics(predictions: Sequence[Prediction]) -> dict[str, object]:
    grouped: dict[date, list[Prediction]] = defaultdict(list)
    for item in predictions:
        grouped[item.formation_date].append(item)
    dates = sorted(grouped)
    monthly_ic: list[float] = []
    top_returns: list[float] = []
    spreads: list[float] = []
    turnovers: list[float] = []
    rank_stability: list[float] = []
    prior_top: set[str] | None = None
    prior_ranks: dict[str, float] | None = None
    regime_returns: dict[str, list[float]] = defaultdict(list)
    for formation in dates:
        rows = grouped[formation]
        monthly_ic.append(spearman([(item.security_id, item.predicted, item.target) for item in rows]))
        ordered = sorted(rows, key=lambda item: (-item.predicted, item.security_id))
        top, bottom = ordered[:20], ordered[-20:]
        top_return = fmean(item.target for item in top)
        top_returns.append(top_return)
        spreads.append(top_return - fmean(item.target for item in bottom))
        regime_returns[top[0].regime].append(top_return)
        current_top = {item.security_id for item in top}
        current_ranks = _rank({item.security_id: item.predicted for item in rows})
        if prior_top is not None:
            turnovers.append(1.0 - len(prior_top & current_top) / 20.0)
        if prior_ranks is not None:
            shared = sorted(prior_ranks.keys() & current_ranks.keys())
            if len(shared) > 1:
                rank_stability.append(spearman([(key, prior_ranks[key], current_ranks[key]) for key in shared]))
        prior_top, prior_ranks = current_top, current_ranks
    mean_turnover = fmean(turnovers) if turnovers else 1.0
    errors = [item.predicted - item.target for item in predictions]
    fold_ics = []
    for fold in sorted({item.fold for item in predictions}):
        fold_rows = [item for item in predictions if item.fold == fold]
        fold_dates: dict[date, list[Prediction]] = defaultdict(list)
        for item in fold_rows:
            fold_dates[item.formation_date].append(item)
        fold_ics.append(fmean(spearman([(item.security_id, item.predicted, item.target) for item in rows]) for rows in fold_dates.values()))
    return {
        "observation_count": len(predictions), "formation_count": len(dates),
        "mean_monthly_rank_ic": fmean(monthly_ic), "positive_ic_share": sum(item > 0 for item in monthly_ic) / len(monthly_ic),
        "fold_mean_rank_ics": fold_ics, "top_minus_bottom_spread": fmean(spreads),
        "top20_relative_return_gross": fmean(top_returns), "mean_one_way_turnover": mean_turnover,
        "top20_relative_return_after_cost": {
            str(int(cost * 10000)): fmean(top_returns) - mean_turnover * cost for cost in COST_CASES
        },
        "mean_consecutive_rank_correlation": fmean(rank_stability) if rank_stability else 0.0,
        "mae": fmean(abs(item) for item in errors), "rmse": math.sqrt(fmean(item * item for item in errors)),
        "regime_top20_relative_return": {key: fmean(values) for key, values in sorted(regime_returns.items())},
    }


def compare_models(*, dataset: Path, manifest: Path, output: Path, predictions_output: Path) -> dict[str, object]:
    if output.exists() or predictions_output.exists():
        raise DataQualityError("refusing to overwrite immutable monthly comparison output")
    examples, metadata = load_examples(dataset, manifest)
    primary_predictions, primary_fits = build_oof_predictions(examples, transform="market")
    sector_predictions, sector_fits = build_oof_predictions(examples, transform="static_sector")
    results: dict[str, dict[str, object]] = {"market": {}, "static_sector": {}}
    for transform, values in (("market", primary_predictions), ("static_sector", sector_predictions)):
        for model_key in MODEL_KEYS:
            results[transform][model_key] = metrics([item for item in values if item.model_key == model_key])
    output.parent.mkdir(parents=True, exist_ok=True)
    predictions_output.parent.mkdir(parents=True, exist_ok=True)
    with predictions_output.open("w", encoding="utf-8", newline="") as handle:
        fields = ["model_key", "transform", "fold", "formation_date", "security_id", "predicted", "target", "security_return", "benchmark_return", "regime"]
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for item in sorted((*primary_predictions, *sector_predictions), key=lambda row: (row.transform, row.model_key, row.fold, row.formation_date, row.security_id)):
            writer.writerow({
                "model_key": item.model_key, "transform": item.transform, "fold": item.fold,
                "formation_date": item.formation_date.isoformat(), "security_id": item.security_id,
                "predicted": format(item.predicted, ".17g"), "target": format(item.target, ".17g"),
                "security_return": format(item.security_return, ".17g"),
                "benchmark_return": format(item.benchmark_return, ".17g"), "regime": item.regime,
            })
    payload: dict[str, object] = {
        "experiment_key": EXPERIMENT_KEY, "experiment_version": EXPERIMENT_VERSION,
        "source_dataset_sha256": metadata["content_sha256"], "oof_predictions_sha256": sha256(predictions_output.read_bytes()).hexdigest(),
        "development_only": True, "holdout_used": False, "outer_blocks": [[a.isoformat(), b.isoformat()] for a, b in OUTER_BLOCKS],
        "label_overlap_purge": True, "inner_chronological_tuning": True,
        "models": list(MODEL_KEYS), "results": results,
        "fits": [*primary_fits, *sector_fits], "dataset_coverage": metadata["common_sample_coverage"],
        "limitations": metadata["limitations"],
    }
    provisional = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["result_sha256"] = sha256(provisional.encode()).hexdigest()
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the nested Phase 9B monthly model comparison")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    arguments = parser.parse_args()
    result = compare_models(
        dataset=arguments.input, manifest=arguments.manifest,
        output=arguments.output, predictions_output=arguments.predictions,
    )
    print(f"monthly_models={len(MODEL_KEYS)}; result_sha256={result['result_sha256']}; holdout_used=false")


if __name__ == "__main__":
    main()
