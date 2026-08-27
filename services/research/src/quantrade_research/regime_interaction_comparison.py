"""Evaluate the single pre-registered SPY regime-interaction challenger."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
import math
import os
from pathlib import Path
from statistics import fmean
from typing import Sequence

from .challenger_model_comparison import (
    ComparisonExample,
    Prediction,
    _predictions_for_folds,
    _spearman,
    build_metrics,
)
from .config import Settings
from .historical_training_export import HOLDOUT_START
from .next_generation_evaluation import evaluate_challenger
from .quality import DataQualityError
from .regime_interaction_features import (
    DATASET_KEY,
    DATASET_VERSION,
    FEATURE_DEFINITION_SHA256,
    INTERACTION_COLUMNS,
    MarketTrendSignal,
    benchmark_lineage_sha256,
    calculate_market_trend_signal,
    load_benchmark_bars,
)
from .regularized_training import FEATURE_COLUMNS, LinearModel, TrainingExample, fit_regularized_model
from .score_run import _dotenv_values


EXPERIMENT_KEY = "tier_b_regime_interaction_comparison_v1"
CHALLENGER_MODEL_VERSION = "active_linear_spy_regime_interactions_v1"
CHALLENGER_FEATURE_COLUMNS = (*FEATURE_COLUMNS, *INTERACTION_COLUMNS)
L1_PENALTY = 0.001
L2_PENALTY = 0.01
MINIMUM_RANGE_BOUND_IC = Decimal("0.005")
MINIMUM_RANGE_BOUND_IC_IMPROVEMENT = Decimal("0.005")


def _validate_manifest(dataset: Path, manifest: Path) -> dict[str, object]:
    try:
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
        expected_hash = str(metadata["content_sha256"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid regime-interaction dataset manifest") from error
    if sha256(dataset.read_bytes()).hexdigest() != expected_hash:
        raise DataQualityError("regime-interaction dataset does not match its immutable manifest")
    expected = {
        "dataset_key": DATASET_KEY,
        "dataset_version": DATASET_VERSION,
        "development_only": True,
        "holdout_used": False,
        "model_fitted": False,
        "interaction_definition_sha256": FEATURE_DEFINITION_SHA256,
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise DataQualityError(f"regime-interaction manifest has invalid {key}")
    if tuple(metadata.get("interaction_columns", ())) != INTERACTION_COLUMNS:
        raise DataQualityError("regime-interaction manifest has unexpected feature columns")
    if int(metadata.get("point_in_time_violations", -1)) != 0:
        raise DataQualityError("regime-interaction manifest reports a point-in-time violation")
    return metadata


def load_examples(
    dataset: Path, manifest: Path,
) -> tuple[tuple[ComparisonExample, ...], dict[date, datetime], dict[str, object]]:
    metadata = _validate_manifest(dataset, manifest)
    examples: list[ComparisonExample] = []
    decisions: dict[date, datetime] = {}
    seen: set[tuple[date, str]] = set()
    with dataset.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "partition", "score_date", "security_id", "decision_at",
            "benchmark_relative_return", "security_return", "benchmark_return",
            *CHALLENGER_FEATURE_COLUMNS,
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise DataQualityError("regime-interaction dataset lacks comparison columns")
        for line_number, row in enumerate(reader, start=2):
            try:
                score_date = date.fromisoformat(row["score_date"])
                decision_at = datetime.fromisoformat(row["decision_at"])
                base = tuple(float(row[column]) for column in FEATURE_COLUMNS)
                challenger = tuple(float(row[column]) for column in CHALLENGER_FEATURE_COLUMNS)
                target = float(row["benchmark_relative_return"])
                security_return = float(row["security_return"])
                benchmark_return = float(row["benchmark_return"])
            except (KeyError, TypeError, ValueError) as error:
                raise DataQualityError(f"invalid regime-interaction row {line_number}") from error
            if row.get("partition") != "development" or score_date >= HOLDOUT_START:
                raise DataQualityError("regime-interaction dataset contains a non-development row")
            if decision_at.tzinfo is None or decision_at.utcoffset() is None:
                raise DataQualityError("regime-interaction decision timestamp lacks a UTC offset")
            prior_decision = decisions.setdefault(score_date, decision_at)
            if prior_decision != decision_at:
                raise DataQualityError(f"inconsistent decision timestamp for {score_date}")
            identity = (score_date, row["security_id"])
            if identity in seen:
                raise DataQualityError(f"duplicate regime-interaction example: {identity}")
            values = (*base, *challenger, target, security_return, benchmark_return)
            if not all(math.isfinite(value) for value in values):
                raise DataQualityError(f"non-finite regime-interaction value at line {line_number}")
            seen.add(identity)
            examples.append(ComparisonExample(
                score_date, row["security_id"], base, challenger,
                target, security_return, benchmark_return,
            ))
    if not examples:
        raise DataQualityError("regime-interaction dataset contains no examples")
    if len(examples) != int(metadata["materialized_rows"]):
        raise DataQualityError("regime-interaction row count differs from its manifest")
    return tuple(examples), decisions, metadata


def fit_regime_interaction_elastic_net(rows: Sequence[ComparisonExample]) -> LinearModel:
    """Fit the one frozen eight-input elastic-net specification."""
    if not rows:
        raise DataQualityError("cannot fit the regime challenger without examples")
    examples = tuple(
        TrainingExample(item.score_date, item.challenger_features, item.target)
        for item in rows
    )
    width = len(CHALLENGER_FEATURE_COLUMNS)
    if any(len(item.features) != width for item in examples):
        raise DataQualityError("regime challenger has an inconsistent feature width")
    means = tuple(fmean(item.features[index] for item in examples) for index in range(width))
    scales = tuple(
        math.sqrt(fmean((item.features[index] - means[index]) ** 2 for item in examples))
        for index in range(width)
    )
    scales = tuple(value if value > 1e-12 else 1.0 for value in scales)
    target_mean = fmean(item.target for item in examples)
    gram = [[0.0] * width for _ in range(width)]
    covariance = [0.0] * width
    for item in examples:
        standardized = tuple(
            (value - means[index]) / scales[index]
            for index, value in enumerate(item.features)
        )
        centered_target = item.target - target_mean
        for left in range(width):
            covariance[left] += standardized[left] * centered_target
            for right in range(width):
                gram[left][right] += standardized[left] * standardized[right]
    count = float(len(examples))
    gram = [[value / count for value in row] for row in gram]
    covariance = [value / count for value in covariance]
    coefficients = [0.0] * width
    for _ in range(20_000):
        largest_change = 0.0
        for index in range(width):
            partial = covariance[index] - sum(
                gram[index][other] * coefficients[other]
                for other in range(width) if other != index
            )
            if partial > L1_PENALTY:
                numerator = partial - L1_PENALTY
            elif partial < -L1_PENALTY:
                numerator = partial + L1_PENALTY
            else:
                numerator = 0.0
            updated = numerator / (gram[index][index] + L2_PENALTY)
            largest_change = max(largest_change, abs(updated - coefficients[index]))
            coefficients[index] = updated
        if largest_change < 1e-10:
            break
    else:
        raise DataQualityError("regime-interaction elastic-net did not converge")
    return LinearModel(
        "elastic_net", L1_PENALTY, L2_PENALTY, means, scales,
        target_mean, tuple(coefficients),
    )


def build_market_signals(
    decisions: dict[date, datetime], database_url: str, expected_lineage_sha256: str,
) -> dict[date, MarketTrendSignal]:
    bars = load_benchmark_bars(database_url, max(decisions))
    signals = {
        score_date: calculate_market_trend_signal(
            score_date=score_date, decision_at=decision_at, bars=bars,
        )
        for score_date, decision_at in sorted(decisions.items())
    }
    actual_lineage = benchmark_lineage_sha256(tuple(signals.values()))
    if actual_lineage != expected_lineage_sha256:
        raise DataQualityError("SPY point-in-time lineage differs from the materialized dataset")
    return signals


def range_bound_metrics(
    predictions: Sequence[Prediction], signals: dict[date, MarketTrendSignal],
) -> dict[str, object]:
    by_date: dict[date, list[Prediction]] = defaultdict(list)
    for item in predictions:
        signal = signals.get(item.score_date)
        if signal is None:
            raise DataQualityError(f"missing market signal for {item.score_date}")
        if Decimal("-0.05") < signal.raw_return < Decimal("0.05"):
            by_date[item.score_date].append(item)
    if not by_date:
        raise DataQualityError("comparison contains no range-bound validation dates")
    daily_ics = [_spearman(rows) for rows in by_date.values() if len(rows) >= 2]
    if len(daily_ics) != len(by_date):
        raise DataQualityError("range-bound comparison date has fewer than two observations")
    return {
        "observation_count": sum(len(rows) for rows in by_date.values()),
        "score_date_count": len(by_date),
        "mean_daily_spearman_ic": Decimal(str(fmean(daily_ics))),
    }


def _json_ready(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_ready(item) for item in value]
    return value


def run_comparison(
    examples: Sequence[ComparisonExample],
    signals: dict[date, MarketTrendSignal],
    *, feature_coverage: Decimal,
) -> dict[str, object]:
    active_predictions = _predictions_for_folds(
        examples,
        fit=lambda rows: fit_regularized_model(
            [TrainingExample(item.score_date, item.base_features, item.target) for item in rows],
            family="elastic_net", l1_penalty=L1_PENALTY, l2_penalty=L2_PENALTY,
        ),
        use_base_features=True,
    )
    challenger_predictions = _predictions_for_folds(
        examples, fit=fit_regime_interaction_elastic_net, use_base_features=False,
    )
    active_identities = [(item.fold, item.score_date, item.security_id) for item in active_predictions]
    challenger_identities = [(item.fold, item.score_date, item.security_id) for item in challenger_predictions]
    if active_identities != challenger_identities:
        raise DataQualityError("active and challenger predictions do not share one sample")

    active = build_metrics("active_elastic_net_refit_v1", active_predictions, feature_coverage=Decimal("1"))
    challenger = build_metrics(
        CHALLENGER_MODEL_VERSION, challenger_predictions, feature_coverage=feature_coverage,
    )
    base_decision = evaluate_challenger(active, challenger)
    active_range = range_bound_metrics(active_predictions, signals)
    challenger_range = range_bound_metrics(challenger_predictions, signals)
    if (
        active_range["observation_count"] != challenger_range["observation_count"]
        or active_range["score_date_count"] != challenger_range["score_date_count"]
    ):
        raise DataQualityError("range-bound active and challenger samples differ")
    active_range_ic = Decimal(str(active_range["mean_daily_spearman_ic"]))
    challenger_range_ic = Decimal(str(challenger_range["mean_daily_spearman_ic"]))
    range_gates = (
        {
            "gate": "range_bound_rank_ic_absolute",
            "passed": challenger_range_ic >= MINIMUM_RANGE_BOUND_IC,
            "detail": f"challenger={challenger_range_ic}; minimum={MINIMUM_RANGE_BOUND_IC}",
        },
        {
            "gate": "range_bound_rank_ic_improvement",
            "passed": challenger_range_ic - active_range_ic >= MINIMUM_RANGE_BOUND_IC_IMPROVEMENT,
            "detail": (
                f"delta={challenger_range_ic - active_range_ic}; "
                f"minimum={MINIMUM_RANGE_BOUND_IC_IMPROVEMENT}"
            ),
        },
    )
    all_gates = [asdict(item) for item in base_decision.results] + list(range_gates)
    eligible = base_decision.freeze_eligible and all(item["passed"] for item in range_gates)
    return {
        "experiment_key": EXPERIMENT_KEY,
        "status": "development_comparison_complete",
        "development_only": True,
        "holdout_used": False,
        "active_model_changed": False,
        "data_capability_tier": "B",
        "common_sample": True,
        "feature_columns": list(CHALLENGER_FEATURE_COLUMNS),
        "penalties": {"l1": str(L1_PENALTY), "l2": str(L2_PENALTY)},
        "active_reference": _json_ready(asdict(active)),
        "challenger": {
            "model_version": CHALLENGER_MODEL_VERSION,
            "metrics": _json_ready(asdict(challenger)),
            "range_bound_metrics": _json_ready(challenger_range),
            "freeze_gate_eligible": eligible,
            "gates": _json_ready(all_gates),
        },
        "active_range_bound_metrics": _json_ready(active_range),
        "next_step": (
            "Record the formal P9A.5 freeze decision without changing the active model."
            if eligible
            else "Record the formal P9A.5 rejection; do not freeze or deploy this challenger."
        ),
        "limitations": [
            "Tier B fixed current-survivors cohort; not unbiased historical-index evidence.",
            "Overlapping 20-session labels are not independent trials.",
            "Development gates do not guarantee future or live outperformance.",
        ],
    }


def render_report(result: dict[str, object]) -> str:
    active = result["active_reference"]
    challenger = result["challenger"]
    assert isinstance(active, dict) and isinstance(challenger, dict)
    candidate_metrics = challenger["metrics"]
    active_range = result["active_range_bound_metrics"]
    candidate_range = challenger["range_bound_metrics"]
    gates = challenger["gates"]
    assert isinstance(candidate_metrics, dict)
    assert isinstance(active_range, dict) and isinstance(candidate_range, dict)
    assert isinstance(gates, list)

    def value(item: object, digits: int = 4) -> str:
        return f"{Decimal(str(item)):.{digits}f}"

    def percent(item: object) -> str:
        return f"{Decimal(str(item)):.2%}"

    failed = [item for item in gates if isinstance(item, dict) and not item["passed"]]
    decision = "passed every frozen gate" if not failed else f"failed {len(failed)} frozen gate(s)"
    lines = [
        "# Regime-Interaction Challenger Comparison",
        "",
        "## Result",
        "",
        f"The single pre-registered challenger {decision}. This is a development-only",
        "comparison. The locked holdout was not used and the active model was not changed.",
        "",
        "## Common-sample metrics",
        "",
        "| Measure | Active elastic-net | Regime challenger |",
        "| --- | ---: | ---: |",
        f"| Mean daily rank IC | {value(active['mean_daily_spearman_ic'])} | {value(candidate_metrics['mean_daily_spearman_ic'])} |",
        f"| Range-bound rank IC | {value(active_range['mean_daily_spearman_ic'])} | {value(candidate_range['mean_daily_spearman_ic'])} |",
        f"| Top-minus-bottom spread | {percent(active['top_minus_bottom_spread'])} | {percent(candidate_metrics['top_minus_bottom_spread'])} |",
        f"| Return after 20 bps | {percent(active['relative_return_after_20bps'])} | {percent(candidate_metrics['relative_return_after_20bps'])} |",
        f"| Positive months | {percent(active['positive_month_share'])} | {percent(candidate_metrics['positive_month_share'])} |",
        f"| Rank stability | {value(active['consecutive_rank_correlation'])} | {value(candidate_metrics['consecutive_rank_correlation'])} |",
        f"| Monthly turnover | {percent(active['mean_monthly_turnover'])} | {percent(candidate_metrics['mean_monthly_turnover'])} |",
        f"| MAE | {percent(active['mae'])} | {percent(candidate_metrics['mae'])} |",
        f"| RMSE | {percent(active['rmse'])} | {percent(candidate_metrics['rmse'])} |",
        "",
        "## Gate result",
        "",
    ]
    if failed:
        for item in failed:
            lines.append(f"- Failed `{item['gate']}`: {item['detail']}")
    else:
        lines.append("- Every pre-registered common and range-bound gate passed.")
    lines.extend([
        "",
        "## Provenance",
        "",
        f"- Dataset SHA-256: `{result['dataset_content_sha256']}`",
        f"- Combined feature-registry SHA-256: `{result['dataset_registry_hash']}`",
        f"- SPY lineage SHA-256: `{result['benchmark_lineage_sha256']}`",
        f"- Result SHA-256: `{result['result_sha256']}`",
        "",
        "P9A.5 must record the formal freeze or rejection decision. This comparison",
        "alone cannot alter the live model or user-visible rankings.",
        "",
    ])
    return "\n".join(lines)


def _settings(env_file: Path) -> Settings:
    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare the pre-registered regime-interaction challenger")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    for path in (arguments.output, arguments.report):
        if path.exists():
            raise DataQualityError(f"refusing to overwrite immutable comparison output: {path}")
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    examples, decisions, metadata = load_examples(arguments.input, arguments.manifest)
    signals = build_market_signals(
        decisions, settings.database_url, str(metadata["benchmark_lineage_sha256"]),
    )
    result = run_comparison(
        examples, signals, feature_coverage=Decimal(str(metadata["coverage"])),
    )
    result["dataset_content_sha256"] = metadata["content_sha256"]
    result["dataset_registry_hash"] = metadata["combined_feature_registry_hash"]
    result["benchmark_lineage_sha256"] = metadata["benchmark_lineage_sha256"]
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"))
    result["result_sha256"] = sha256(canonical.encode("utf-8")).hexdigest()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    arguments.report.write_text(render_report(result), encoding="utf-8")
    print(
        f"freeze_gate_eligible={str(result['challenger']['freeze_gate_eligible']).lower()}; "
        f"result_sha256={result['result_sha256']}; holdout_used=false; active_model_changed=false"
    )


if __name__ == "__main__":
    main()
