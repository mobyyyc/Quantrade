"""Purged development-only comparison of the pre-registered Phase 9 model families."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
import math
from pathlib import Path
from statistics import fmean, median
from typing import Callable, Iterable, Protocol, Sequence

from .challenger_dataset import CANDIDATE_COLUMNS
from .historical_training_export import HOLDOUT_START
from .next_generation_evaluation import (
    ChallengerMetrics,
    challenger_selection_key,
    evaluate_challenger,
)
from .quality import DataQualityError
from .regularized_training import (
    FEATURE_COLUMNS,
    TrainingExample,
    build_time_ordered_folds,
    fit_regularized_model,
)


EXPERIMENT_KEY = "tier_b_next_generation_comparison_v1"
CHALLENGER_FEATURE_COLUMNS = (*FEATURE_COLUMNS, *CANDIDATE_COLUMNS)
ONE_WAY_COST = 0.002


@dataclass(frozen=True, slots=True)
class ComparisonExample:
    score_date: date
    security_id: str
    base_features: tuple[float, ...]
    challenger_features: tuple[float, ...]
    target: float
    security_return: float
    benchmark_return: float


@dataclass(frozen=True, slots=True)
class Prediction:
    fold: int
    score_date: date
    security_id: str
    predicted: float
    target: float
    security_return: float
    benchmark_return: float


class PredictionModel(Protocol):
    def predict(self, features: Sequence[float]) -> float: ...


@dataclass(frozen=True, slots=True)
class GenericLinearModel:
    means: tuple[float, ...]
    scales: tuple[float, ...]
    intercept: float
    coefficients: tuple[float, ...]

    def predict(self, features: Sequence[float]) -> float:
        return self.intercept + sum(
            coefficient * ((value - mean) / scale)
            for coefficient, value, mean, scale in zip(
                self.coefficients, features, self.means, self.scales
            )
        )


@dataclass(frozen=True, slots=True)
class BoostedStump:
    feature_index: int
    split_bin: int
    left_value: float
    right_value: float


@dataclass(frozen=True, slots=True)
class BoostedStumpModel:
    base_value: float
    stumps: tuple[BoostedStump, ...]

    def predict(self, features: Sequence[float]) -> float:
        result = self.base_value
        for stump in self.stumps:
            value_bin = min(9, max(0, int(features[stump.feature_index] * 10)))
            result += stump.left_value if value_bin <= stump.split_bin else stump.right_value
        return result


def _validate_manifest(dataset: Path, manifest: Path) -> dict[str, object]:
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
        expected_hash = str(document["content_sha256"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid challenger dataset manifest") from error
    if sha256(dataset.read_bytes()).hexdigest() != expected_hash:
        raise DataQualityError("challenger dataset does not match its immutable manifest")
    if document.get("development_only") is not True or document.get("holdout_used") is not False:
        raise DataQualityError("challenger comparison requires a development-only dataset")
    return document


def load_examples(dataset: Path, manifest: Path) -> tuple[tuple[ComparisonExample, ...], dict[str, object]]:
    metadata = _validate_manifest(dataset, manifest)
    examples: list[ComparisonExample] = []
    seen: set[tuple[date, str]] = set()
    with dataset.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "partition", "score_date", "security_id", "benchmark_relative_return",
            "security_return", "benchmark_return", *CHALLENGER_FEATURE_COLUMNS,
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise DataQualityError("challenger dataset lacks the required comparison columns")
        for line_number, row in enumerate(reader, start=2):
            try:
                score_date = date.fromisoformat(row["score_date"])
                base = tuple(float(row[column]) for column in FEATURE_COLUMNS)
                challenger = tuple(float(row[column]) for column in CHALLENGER_FEATURE_COLUMNS)
                target = float(row["benchmark_relative_return"])
                security_return = float(row["security_return"])
                benchmark_return = float(row["benchmark_return"])
            except (KeyError, TypeError, ValueError) as error:
                raise DataQualityError(f"invalid challenger dataset line {line_number}") from error
            if row.get("partition") != "development" or score_date >= HOLDOUT_START:
                raise DataQualityError("challenger dataset contains a non-development row")
            identity = (score_date, row["security_id"])
            if identity in seen:
                raise DataQualityError(f"duplicate challenger example: {identity}")
            if not all(math.isfinite(value) for value in (*base, *challenger, target, security_return, benchmark_return)):
                raise DataQualityError(f"non-finite challenger value at line {line_number}")
            seen.add(identity)
            examples.append(ComparisonExample(
                score_date,
                row["security_id"],
                base,
                challenger,
                target,
                security_return,
                benchmark_return,
            ))
    if not examples:
        raise DataQualityError("challenger dataset contains no examples")
    return tuple(sorted(examples, key=lambda item: (item.score_date, item.security_id))), metadata


def _solve(matrix: list[list[float]], values: list[float]) -> tuple[float, ...]:
    size = len(values)
    augmented = [row[:] + [values[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) <= 1e-12:
            raise DataQualityError("challenger linear system is singular")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(augmented[row], augmented[column])
            ]
    return tuple(augmented[index][-1] for index in range(size))


def _standardization(examples: Sequence[ComparisonExample]) -> tuple[tuple[float, ...], tuple[float, ...]]:
    width = len(CHALLENGER_FEATURE_COLUMNS)
    means = tuple(fmean(item.challenger_features[index] for item in examples) for index in range(width))
    scales = tuple(
        math.sqrt(fmean((item.challenger_features[index] - means[index]) ** 2 for item in examples))
        for index in range(width)
    )
    return means, tuple(scale if scale > 1e-12 else 1.0 for scale in scales)


def fit_robust_linear(
    examples: Sequence[ComparisonExample], *, l2_penalty: float, huber_delta: float,
) -> GenericLinearModel:
    if l2_penalty <= 0 or huber_delta <= 0 or not examples:
        raise DataQualityError("invalid robust-linear configuration")
    means, scales = _standardization(examples)
    standardized = [
        tuple((value - means[index]) / scales[index] for index, value in enumerate(item.challenger_features))
        for item in examples
    ]
    targets = [item.target for item in examples]
    weights = [1.0] * len(examples)
    coefficients = (0.0,) * len(means)
    intercept = fmean(targets)
    for _ in range(10):
        weight_sum = sum(weights)
        intercept = sum(weight * target for weight, target in zip(weights, targets)) / weight_sum
        width = len(means)
        gram = [[0.0] * width for _ in range(width)]
        covariance = [0.0] * width
        for weight, features, target in zip(weights, standardized, targets):
            centered = target - intercept
            for left in range(width):
                covariance[left] += weight * features[left] * centered
                for right in range(width):
                    gram[left][right] += weight * features[left] * features[right]
        for index in range(width):
            gram[index][index] += l2_penalty * weight_sum
        coefficients = _solve(gram, covariance)
        residuals = [
            target - (intercept + sum(coefficient * value for coefficient, value in zip(coefficients, features)))
            for target, features in zip(targets, standardized)
        ]
        scale = max(1e-8, 1.4826 * median(abs(value) for value in residuals))
        cutoff = huber_delta * scale
        updated = [1.0 if abs(value) <= cutoff else cutoff / abs(value) for value in residuals]
        if max(abs(left - right) for left, right in zip(weights, updated)) < 1e-6:
            break
        weights = updated
    return GenericLinearModel(means, scales, intercept, coefficients)


def fit_gradient_boosted_stumps(
    examples: Sequence[ComparisonExample], *, estimators: int, learning_rate: float,
) -> BoostedStumpModel:
    if not examples or estimators < 1 or not 0 < learning_rate <= 1:
        raise DataQualityError("invalid gradient-boosted configuration")
    stride = max(1, math.ceil(len(examples) / 100_000))
    sample = list(examples[::stride])
    features = [item.challenger_features for item in sample]
    targets = [item.target for item in sample]
    predictions = [fmean(targets)] * len(sample)
    stumps: list[BoostedStump] = []
    width = len(CHALLENGER_FEATURE_COLUMNS)
    for _ in range(estimators):
        residuals = [target - prediction for target, prediction in zip(targets, predictions)]
        total_sum = sum(residuals)
        best: tuple[float, int, int, float, float] | None = None
        for feature_index in range(width):
            sums = [0.0] * 10
            counts = [0] * 10
            for values, residual in zip(features, residuals):
                value_bin = min(9, max(0, int(values[feature_index] * 10)))
                sums[value_bin] += residual
                counts[value_bin] += 1
            left_sum = 0.0
            left_count = 0
            for split_bin in range(9):
                left_sum += sums[split_bin]
                left_count += counts[split_bin]
                right_count = len(sample) - left_count
                if left_count == 0 or right_count == 0:
                    continue
                right_sum = total_sum - left_sum
                gain = left_sum * left_sum / left_count + right_sum * right_sum / right_count
                candidate = (gain, -feature_index, -split_bin, left_sum / left_count, right_sum / right_count)
                if best is None or candidate[:3] > best[:3]:
                    best = candidate
        if best is None:
            break
        _, negative_feature, negative_split, left_mean, right_mean = best
        stump = BoostedStump(
            -negative_feature,
            -negative_split,
            learning_rate * left_mean,
            learning_rate * right_mean,
        )
        stumps.append(stump)
        for index, values in enumerate(features):
            value_bin = min(9, max(0, int(values[stump.feature_index] * 10)))
            predictions[index] += stump.left_value if value_bin <= stump.split_bin else stump.right_value
    return BoostedStumpModel(fmean(targets), tuple(stumps))


def fit_pairwise_ranker(
    examples: Sequence[ComparisonExample], *, l2_penalty: float, learning_rate: float = 0.03,
    epochs: int = 20,
) -> GenericLinearModel:
    if not examples or l2_penalty <= 0 or learning_rate <= 0 or epochs < 1:
        raise DataQualityError("invalid pairwise-ranker configuration")
    means, scales = _standardization(examples)
    by_date: dict[date, list[ComparisonExample]] = defaultdict(list)
    for item in examples:
        by_date[item.score_date].append(item)
    pairs: list[tuple[tuple[float, ...], tuple[float, ...]]] = []
    for score_date in sorted(by_date):
        ordered = sorted(by_date[score_date], key=lambda item: (item.target, item.security_id))
        count = min(10, len(ordered) // 2)
        for low, high in zip(ordered[:count], reversed(ordered[-count:])):
            pairs.append((high.challenger_features, low.challenger_features))
    if not pairs:
        raise DataQualityError("pairwise ranker has no training pairs")
    coefficients = [0.0] * len(means)
    step = 0
    for _ in range(epochs):
        for high, low in pairs:
            difference = tuple(
                ((high[index] - means[index]) / scales[index])
                - ((low[index] - means[index]) / scales[index])
                for index in range(len(means))
            )
            margin = sum(weight * value for weight, value in zip(coefficients, difference))
            logistic_gradient = -1.0 / (1.0 + math.exp(min(40.0, margin)))
            rate = learning_rate / math.sqrt(1.0 + step / 10_000)
            for index in range(len(coefficients)):
                coefficients[index] -= rate * (
                    logistic_gradient * difference[index] + l2_penalty * coefficients[index]
                )
            step += 1
    raw_scores = [
        sum(
            coefficient * ((value - means[index]) / scales[index])
            for index, (coefficient, value) in enumerate(zip(coefficients, item.challenger_features))
        )
        for item in examples
    ]
    score_mean = fmean(raw_scores)
    target_mean = fmean(item.target for item in examples)
    variance = sum((value - score_mean) ** 2 for value in raw_scores)
    slope = (
        sum((score - score_mean) * (item.target - target_mean) for score, item in zip(raw_scores, examples))
        / variance
        if variance else 0.0
    )
    return GenericLinearModel(
        means,
        scales,
        target_mean - slope * score_mean,
        tuple(slope * value for value in coefficients),
    )


def _pearson(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        return 0.0
    left_mean, right_mean = fmean(left), fmean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    denominator = math.sqrt(
        sum((x - left_mean) ** 2 for x in left) * sum((y - right_mean) ** 2 for y in right)
    )
    return numerator / denominator if denominator else 0.0


def _ranks(values: Sequence[float]) -> tuple[float, ...]:
    ordered = sorted(range(len(values)), key=lambda index: (values[index], index))
    result = [0.0] * len(values)
    position = 0
    while position < len(ordered):
        end = position
        while end + 1 < len(ordered) and values[ordered[end + 1]] == values[ordered[position]]:
            end += 1
        rank = (position + end) / 2 + 1
        for index in ordered[position:end + 1]:
            result[index] = rank
        position = end + 1
    return tuple(result)


def _spearman(rows: Sequence[Prediction]) -> float:
    return _pearson(
        _ranks([item.predicted for item in rows]),
        _ranks([item.target for item in rows]),
    )


def _predictions_for_folds(
    examples: Sequence[ComparisonExample],
    *,
    fit: Callable[[Sequence[ComparisonExample]], PredictionModel],
    use_base_features: bool,
) -> tuple[Prediction, ...]:
    date_examples = [TrainingExample(item.score_date, item.base_features, item.target) for item in examples]
    folds = build_time_ordered_folds(date_examples)
    predictions: list[Prediction] = []
    for fold in folds:
        training = [item for item in examples if item.score_date <= fold.training_end_date]
        validation = [
            item for item in examples
            if fold.validation_start_date <= item.score_date <= fold.validation_end_date
        ]
        model = fit(training)
        for item in validation:
            features = item.base_features if use_base_features else item.challenger_features
            predictions.append(Prediction(
                fold.fold_number,
                item.score_date,
                item.security_id,
                model.predict(features),
                item.target,
                item.security_return,
                item.benchmark_return,
            ))
    return tuple(predictions)


def build_metrics(
    model_version: str,
    predictions: Sequence[Prediction],
    *,
    feature_coverage: Decimal,
) -> ChallengerMetrics:
    if not predictions:
        raise DataQualityError("model comparison produced no predictions")
    by_date: dict[date, list[Prediction]] = defaultdict(list)
    by_fold: dict[int, list[Prediction]] = defaultdict(list)
    for item in predictions:
        by_date[item.score_date].append(item)
        by_fold[item.fold].append(item)
    daily_ics = {score_date: _spearman(rows) for score_date, rows in by_date.items()}
    daily_spreads: list[float] = []
    for rows in by_date.values():
        ordered = sorted(rows, key=lambda item: (item.predicted, item.security_id))
        bucket = max(1, len(ordered) // 10)
        daily_spreads.append(
            fmean(item.target for item in ordered[-bucket:])
            - fmean(item.target for item in ordered[:bucket])
        )
    stability: list[float] = []
    ordered_dates = sorted(by_date)
    for prior_date, current_date in zip(ordered_dates, ordered_dates[1:]):
        prior = {item.security_id: item.predicted for item in by_date[prior_date]}
        current = {item.security_id: item.predicted for item in by_date[current_date]}
        shared = sorted(prior.keys() & current.keys())
        stability.append(_pearson(
            _ranks([prior[security] for security in shared]),
            _ranks([current[security] for security in shared]),
        ))
    dates_by_month: dict[tuple[int, int], list[date]] = defaultdict(list)
    for score_date in ordered_dates:
        dates_by_month[(score_date.year, score_date.month)].append(score_date)
    selected_sets: list[set[str]] = []
    period_portfolio_returns: list[float] = []
    period_benchmark_returns: list[float] = []
    for month in sorted(dates_by_month):
        formation_date = max(dates_by_month[month])
        selected = sorted(
            by_date[formation_date], key=lambda item: (-item.predicted, item.security_id)
        )[:20]
        selected_sets.append({item.security_id for item in selected})
        period_portfolio_returns.append(fmean(item.security_return for item in selected) - 2 * ONE_WAY_COST)
        period_benchmark_returns.append(fmean(item.benchmark_return for item in selected))
    turnovers = [
        1.0 - len(prior & current) / max(len(prior), len(current))
        for prior, current in zip(selected_sets, selected_sets[1:])
    ]
    portfolio_nav = benchmark_nav = 1.0
    positive_months = 0
    for portfolio_return, benchmark_return in zip(period_portfolio_returns, period_benchmark_returns):
        portfolio_nav *= 1.0 + portfolio_return
        benchmark_nav *= 1.0 + benchmark_return
        positive_months += portfolio_return > benchmark_return
    errors = [item.predicted - item.target for item in predictions]
    fold_ics = tuple(
        fmean(_spearman(rows) for rows in _group_by_date(by_fold[fold]).values())
        for fold in sorted(by_fold)
    )
    return ChallengerMetrics(
        model_version=model_version,
        observation_count=len(predictions),
        score_date_count=len(by_date),
        fold_count=len(by_fold),
        monthly_formation_count=len(selected_sets),
        feature_coverage=feature_coverage,
        mean_daily_spearman_ic=Decimal(str(fmean(daily_ics.values()))),
        top_minus_bottom_spread=Decimal(str(fmean(daily_spreads))),
        positive_ic_share=Decimal(str(sum(value > 0 for value in daily_ics.values()) / len(daily_ics))),
        fold_mean_ics=tuple(Decimal(str(value)) for value in fold_ics),
        consecutive_rank_correlation=Decimal(str(fmean(stability))),
        mean_monthly_turnover=Decimal(str(fmean(turnovers) if turnovers else 0.0)),
        relative_return_after_20bps=Decimal(str((portfolio_nav - 1.0) - (benchmark_nav - 1.0))),
        positive_month_share=Decimal(str(positive_months / len(selected_sets))),
        mae=Decimal(str(fmean(abs(error) for error in errors))),
        rmse=Decimal(str(math.sqrt(fmean(error * error for error in errors)))),
    )


def _group_by_date(rows: Iterable[Prediction]) -> dict[date, list[Prediction]]:
    result: dict[date, list[Prediction]] = defaultdict(list)
    for row in rows:
        result[row.score_date].append(row)
    return result


def _json_ready(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_ready(item) for item in value]
    return value


def run_comparison(
    examples: Sequence[ComparisonExample], *, feature_coverage: Decimal,
) -> dict[str, object]:
    active_predictions = _predictions_for_folds(
        examples,
        fit=lambda rows: fit_regularized_model(
            [TrainingExample(item.score_date, item.base_features, item.target) for item in rows],
            family="elastic_net",
            l1_penalty=0.001,
            l2_penalty=0.01,
        ),
        use_base_features=True,
    )
    active = build_metrics(
        "active_elastic_net_refit_v1", active_predictions, feature_coverage=Decimal("1"),
    )
    configurations: tuple[tuple[str, Callable[[Sequence[ComparisonExample]], PredictionModel]], ...] = (
        *(
            (
                f"robust_huber_delta_{delta}_l2_{l2}",
                lambda rows, delta=delta, l2=l2: fit_robust_linear(rows, l2_penalty=l2, huber_delta=delta),
            )
            for delta in (1.0, 1.5) for l2 in (0.01, 0.1)
        ),
        (
            "gradient_boosted_stumps_24_lr_0.05",
            lambda rows: fit_gradient_boosted_stumps(rows, estimators=24, learning_rate=0.05),
        ),
        (
            "gradient_boosted_stumps_36_lr_0.03",
            lambda rows: fit_gradient_boosted_stumps(rows, estimators=36, learning_rate=0.03),
        ),
        *(
            (
                f"pairwise_ranker_l2_{l2}",
                lambda rows, l2=l2: fit_pairwise_ranker(rows, l2_penalty=l2),
            )
            for l2 in (0.001, 0.01)
        ),
    )
    candidates: list[dict[str, object]] = []
    passing: list[ChallengerMetrics] = []
    for model_version, fit in configurations:
        print(f"comparison_model={model_version}", flush=True)
        predictions = _predictions_for_folds(examples, fit=fit, use_base_features=False)
        metrics = build_metrics(model_version, predictions, feature_coverage=feature_coverage)
        decision = evaluate_challenger(active, metrics)
        if decision.freeze_eligible:
            passing.append(metrics)
        candidates.append({
            "model_version": model_version,
            "metrics": _json_ready(asdict(metrics)),
            "freeze_eligible": decision.freeze_eligible,
            "gates": _json_ready([asdict(result) for result in decision.results]),
        })
    selected = min(passing, key=challenger_selection_key) if passing else None
    payload: dict[str, object] = {
        "experiment_key": EXPERIMENT_KEY,
        "status": "development_comparison_complete",
        "data_capability_tier": "B",
        "development_only": True,
        "holdout_used": False,
        "common_sample": True,
        "feature_columns": list(CHALLENGER_FEATURE_COLUMNS),
        "active_reference": _json_ready(asdict(active)),
        "candidates": candidates,
        "passing_candidate_count": len(passing),
        "selected_challenger": selected.model_version if selected else None,
        "next_step": (
            "Freeze the selected challenger in P9.5."
            if selected else "No candidate passed every frozen gate; record the negative result without freezing a challenger."
        ),
        "limitations": [
            "Tier B fixed current-survivors cohort; not unbiased historical-index evidence.",
            "Static current sectors are not historical point-in-time classifications.",
            "Overlapping 20-session labels are not independent trials.",
            "Passing development gates does not guarantee future outperformance.",
        ],
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare pre-registered Phase 9 model families on purged development folds")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.output.exists():
        raise DataQualityError(f"refusing to overwrite immutable challenger comparison: {arguments.output}")
    examples, metadata = load_examples(arguments.input, arguments.manifest)
    result = run_comparison(
        examples,
        feature_coverage=Decimal(str(metadata["common_sample_coverage"])),
    )
    result["dataset_content_sha256"] = metadata["content_sha256"]
    result["dataset_registry_hash"] = metadata["combined_feature_registry_hash"]
    canonical = json.dumps(result, separators=(",", ":"), sort_keys=True).encode("utf-8")
    result["result_sha256"] = sha256(canonical).hexdigest()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"passing_candidates={result['passing_candidate_count']}; "
        f"selected={result['selected_challenger']}; result_sha256={result['result_sha256']}"
    )


if __name__ == "__main__":
    main()
