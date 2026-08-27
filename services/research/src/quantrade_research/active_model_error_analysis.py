"""Development-only segment diagnostics for the active elastic-net model."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import json
import math
from pathlib import Path
from statistics import fmean
from typing import Iterable, Sequence

import psycopg

from .challenger_model_comparison import (
    ComparisonExample,
    Prediction,
    _predictions_for_folds,
    _spearman,
    load_examples,
)
from .config import Settings
from .historical_training_export import HOLDOUT_START
from .quality import DataQualityError
from .regularized_training import FEATURE_COLUMNS, TrainingExample, fit_regularized_model
from .score_run import _dotenv_values


ANALYSIS_KEY = "active_model_development_error_segments_v1"
VOLATILITY_FEATURE_INDEX = FEATURE_COLUMNS.index("trailing_volatility_60d_percentile")
MARKET_LOOKBACK_SESSIONS = 60
MARKET_TREND_THRESHOLD = 0.05
MIN_RANK_OBSERVATIONS = 5


@dataclass(frozen=True, slots=True)
class SegmentContext:
    sector: str
    stock_volatility_regime: str
    decision_at: datetime


@dataclass(frozen=True, slots=True)
class BenchmarkBar:
    session_date: date
    close_price: float
    available_at: datetime


def stock_volatility_regime(percentile: float) -> str:
    if not math.isfinite(percentile) or percentile < 0 or percentile > 1:
        raise DataQualityError("stock-volatility percentile must be finite and between zero and one")
    if percentile < 1 / 3:
        return "low"
    if percentile <= 2 / 3:
        return "middle"
    return "high"


def market_trend_regime(trailing_return: float) -> str:
    if not math.isfinite(trailing_return):
        raise DataQualityError("market trailing return must be finite")
    if trailing_return <= -MARKET_TREND_THRESHOLD:
        return "bearish"
    if trailing_return >= MARKET_TREND_THRESHOLD:
        return "bullish"
    return "range_bound"


def load_segment_contexts(dataset: Path) -> dict[tuple[date, str], SegmentContext]:
    result: dict[tuple[date, str], SegmentContext] = {}
    with dataset.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "partition", "score_date", "security_id", "sector_code", "decision_at",
            "trailing_volatility_60d_percentile",
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise DataQualityError("error-analysis dataset lacks required segment columns")
        for line_number, row in enumerate(reader, start=2):
            if row.get("partition") != "development":
                raise DataQualityError(f"error-analysis line {line_number} is not development data")
            try:
                score_date = date.fromisoformat(row["score_date"])
                decision_at = datetime.fromisoformat(row["decision_at"])
                volatility = float(row["trailing_volatility_60d_percentile"])
            except (KeyError, TypeError, ValueError) as error:
                raise DataQualityError(f"invalid error-analysis line {line_number}") from error
            if score_date >= HOLDOUT_START:
                raise DataQualityError("error-analysis input reaches the locked holdout")
            identity = (score_date, row["security_id"])
            if identity in result:
                raise DataQualityError(f"duplicate error-analysis context: {identity}")
            result[identity] = SegmentContext(
                sector=(row.get("sector_code") or "Unavailable").strip() or "Unavailable",
                stock_volatility_regime=stock_volatility_regime(volatility),
                decision_at=decision_at,
            )
    if not result:
        raise DataQualityError("error-analysis dataset contains no contexts")
    return result


def load_benchmark_bars(database_url: str, through_date: date) -> tuple[BenchmarkBar, ...]:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT session_date, close_price, available_at
               FROM quantrade.benchmark_daily_price_bars
               WHERE benchmark_ticker = 'SPY'
                 AND session = 'regular'
                 AND adjustment_basis = 'split_adjusted'
                 AND session_date <= %s
               ORDER BY session_date ASC""",
            (through_date,),
        )
        rows = tuple(
            BenchmarkBar(item[0], float(item[1]), item[2])
            for item in cursor.fetchall()
        )
    if not rows:
        raise DataQualityError("SPY history is unavailable for error analysis")
    if any(item.close_price <= 0 for item in rows):
        raise DataQualityError("SPY history contains a non-positive close")
    return rows


def build_market_regimes(
    decisions: dict[date, datetime], bars: Sequence[BenchmarkBar],
) -> tuple[dict[date, str], str]:
    regimes: dict[date, str] = {}
    used: set[BenchmarkBar] = set()
    for score_date in sorted(decisions):
        decision_at = decisions[score_date]
        eligible = [
            item for item in bars
            if item.session_date <= score_date and item.available_at <= decision_at
        ]
        if len(eligible) < MARKET_LOOKBACK_SESSIONS + 1:
            regimes[score_date] = "unavailable"
            continue
        window = eligible[-(MARKET_LOOKBACK_SESSIONS + 1):]
        used.update(window)
        trailing_return = window[-1].close_price / window[0].close_price - 1
        regimes[score_date] = market_trend_regime(trailing_return)
    canonical = "\n".join(
        f"{item.session_date.isoformat()}|{item.close_price:.12g}|{item.available_at.isoformat()}"
        for item in sorted(used, key=lambda value: (value.session_date, value.available_at))
    )
    return regimes, sha256(canonical.encode("utf-8")).hexdigest()


def _segment_metrics(rows: Sequence[Prediction]) -> dict[str, object]:
    if not rows:
        raise DataQualityError("cannot summarize an empty error-analysis segment")
    errors = [item.predicted - item.target for item in rows]
    by_date: dict[date, list[Prediction]] = defaultdict(list)
    for item in rows:
        by_date[item.score_date].append(item)
    daily_ics = [
        _spearman(items)
        for items in by_date.values()
        if len(items) >= MIN_RANK_OBSERVATIONS
    ]
    return {
        "observation_count": len(rows),
        "score_date_count": len(by_date),
        "mean_prediction": fmean(item.predicted for item in rows),
        "mean_realized_relative_return": fmean(item.target for item in rows),
        "mean_error": fmean(errors),
        "mae": fmean(abs(error) for error in errors),
        "rmse": math.sqrt(fmean(error * error for error in errors)),
        "mean_daily_rank_ic": fmean(daily_ics) if daily_ics else None,
        "rank_ic_date_count": len(daily_ics),
        "directional_accuracy": sum(
            (item.predicted >= 0) == (item.target >= 0) for item in rows
        ) / len(rows),
    }


def _rounded(value: object) -> object:
    if isinstance(value, float):
        return round(value, 12)
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_rounded(item) for item in value]
    return value


def analyze_predictions(
    predictions: Sequence[Prediction],
    contexts: dict[tuple[date, str], SegmentContext],
    market_regimes: dict[date, str],
) -> dict[str, object]:
    if not predictions:
        raise DataQualityError("error analysis requires out-of-fold predictions")
    missing = [
        (item.score_date, item.security_id)
        for item in predictions
        if (item.score_date, item.security_id) not in contexts
    ]
    if missing:
        raise DataQualityError(f"error analysis lacks {len(missing)} prediction contexts")
    if any(item.score_date not in market_regimes for item in predictions):
        raise DataQualityError("error analysis lacks a market regime for a validation date")

    grouped: dict[str, dict[str, list[Prediction]]] = {
        "sector": defaultdict(list),
        "stock_volatility": defaultdict(list),
        "market_regime": defaultdict(list),
    }
    for item in predictions:
        context = contexts[(item.score_date, item.security_id)]
        grouped["sector"][context.sector].append(item)
        grouped["stock_volatility"][context.stock_volatility_regime].append(item)
        grouped["market_regime"][market_regimes[item.score_date]].append(item)

    overall = _segment_metrics(predictions)
    dimensions: dict[str, list[dict[str, object]]] = {}
    for dimension, segments in grouped.items():
        rows: list[dict[str, object]] = []
        for name, segment_predictions in segments.items():
            metrics = _segment_metrics(segment_predictions)
            rank_ic = metrics["mean_daily_rank_ic"]
            overall_rank_ic = overall["mean_daily_rank_ic"]
            rows.append({
                "segment": name,
                **metrics,
                "mae_delta_vs_overall": float(metrics["mae"]) - float(overall["mae"]),
                "rank_ic_delta_vs_overall": (
                    None if rank_ic is None or overall_rank_ic is None
                    else float(rank_ic) - float(overall_rank_ic)
                ),
            })
        rows.sort(key=lambda item: (
            item["mean_daily_rank_ic"] is None,
            float(item["mean_daily_rank_ic"] or 0),
            -float(item["mae"]),
            str(item["segment"]),
        ))
        dimensions[dimension] = rows
    return _rounded({"overall": overall, "dimensions": dimensions})


def run_analysis(
    examples: Sequence[ComparisonExample],
    contexts: dict[tuple[date, str], SegmentContext],
    market_regimes: dict[date, str],
    *, dataset_sha256: str, registry_hash: str, benchmark_lineage_sha256: str,
) -> dict[str, object]:
    predictions = _predictions_for_folds(
        examples,
        fit=lambda rows: fit_regularized_model(
            [TrainingExample(item.score_date, item.base_features, item.target) for item in rows],
            family="elastic_net",
            l1_penalty=0.001,
            l2_penalty=0.01,
        ),
        use_base_features=True,
    )
    diagnostics = analyze_predictions(predictions, contexts, market_regimes)
    result: dict[str, object] = {
        "analysis_key": ANALYSIS_KEY,
        "status": "development_diagnostics_complete",
        "development_only": True,
        "holdout_used": False,
        "model_version": "active_elastic_net_refit_v1",
        "dataset_sha256": dataset_sha256,
        "feature_registry_hash": registry_hash,
        "benchmark_lineage_sha256": benchmark_lineage_sha256,
        "market_regime_definition": {
            "lookback_sessions": MARKET_LOOKBACK_SESSIONS,
            "bearish": "SPY trailing return <= -5%",
            "range_bound": "SPY trailing return between -5% and +5%",
            "bullish": "SPY trailing return >= +5%",
            "availability_rule": "Only split-adjusted SPY bars available by the dated 8 PM decision are used.",
        },
        "stock_volatility_definition": "Low, middle, and high thirds of the decision-time trailing-volatility percentile.",
        "sector_limitation": "Current static Tier-B sectors, not historical point-in-time classifications.",
        **diagnostics,
    }
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"))
    result["result_sha256"] = sha256(canonical.encode("utf-8")).hexdigest()
    return result


def render_markdown(report: dict[str, object]) -> str:
    overall = report["overall"]
    assert isinstance(overall, dict)
    dimensions = report["dimensions"]
    assert isinstance(dimensions, dict)

    def percent(value: object) -> str:
        return f"{float(value):.2%}"

    def number(value: object) -> str:
        return "Unavailable" if value is None else f"{float(value):.4f}"

    lines = [
        "# Active-Model Development Error Analysis",
        "",
        "## Scope",
        "",
        "This report diagnoses the active elastic-net model on purged, out-of-fold",
        "development predictions only. The locked July 2025 through June 2026 holdout",
        "was not opened, and no model or user-visible score changed.",
        "",
        "## Overall validation behavior",
        "",
        f"- Observations: {int(overall['observation_count']):,} across {int(overall['score_date_count']):,} dates",
        f"- Mean daily rank IC: {number(overall['mean_daily_rank_ic'])}",
        f"- MAE: {percent(overall['mae'])}",
        f"- RMSE: {percent(overall['rmse'])}",
        f"- Mean prediction error: {percent(overall['mean_error'])}",
        f"- Directional accuracy: {percent(overall['directional_accuracy'])}",
        "",
    ]
    labels = {
        "sector": "Sector",
        "stock_volatility": "Stock volatility",
        "market_regime": "Market regime",
    }
    for dimension in ("sector", "stock_volatility", "market_regime"):
        lines.extend([
            f"## {labels[dimension]}",
            "",
            "| Segment | Observations | Rank IC | IC delta | MAE | MAE delta | Mean error |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ])
        rows = dimensions[dimension]
        assert isinstance(rows, list)
        for row in rows:
            lines.append(
                f"| {row['segment']} | {int(row['observation_count']):,} | "
                f"{number(row['mean_daily_rank_ic'])} | {number(row['rank_ic_delta_vs_overall'])} | "
                f"{percent(row['mae'])} | {percent(row['mae_delta_vs_overall'])} | "
                f"{percent(row['mean_error'])} |"
            )
        lines.append("")

    priorities: list[tuple[str, dict[str, object], dict[str, object]]] = []
    for dimension in ("sector", "stock_volatility", "market_regime"):
        rows = dimensions[dimension]
        assert isinstance(rows, list)
        eligible = [row for row in rows if row["mean_daily_rank_ic"] is not None]
        if eligible:
            priorities.append((
                labels[dimension],
                min(
                    eligible,
                    key=lambda row: (float(row["mean_daily_rank_ic"]), -float(row["mae"])),
                ),
                max(eligible, key=lambda row: (float(row["mae"]), str(row["segment"]))),
            ))
    lines.extend(["## Diagnostic priorities", ""])
    for dimension, weakest_rank, largest_error in priorities:
        lines.append(
            f"- {dimension}: `{weakest_rank['segment']}` had the weakest descriptive rank IC "
            f"({number(weakest_rank['mean_daily_rank_ic'])}); `{largest_error['segment']}` had "
            f"the largest MAE ({percent(largest_error['mae'])})."
        )
    lines.extend([
        "",
        "These are hypothesis-discovery diagnostics, not independent statistical trials.",
        "They do not authorize a feature, model change, or performance claim. The next",
        "research cycle must pre-register one targeted hypothesis before fitting it.",
        "",
        "## Provenance",
        "",
        f"- Dataset SHA-256: `{report['dataset_sha256']}`",
        f"- Feature-registry hash: `{report['feature_registry_hash']}`",
        f"- SPY lineage SHA-256: `{report['benchmark_lineage_sha256']}`",
        f"- Result SHA-256: `{report['result_sha256']}`",
        "- Sector warning: current static Tier-B sectors are not historical point-in-time classifications.",
        "",
    ])
    return "\n".join(lines)


def _settings(env_file: Path) -> Settings:
    return Settings.from_environment(_dotenv_values(env_file))


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Diagnose active-model errors on purged development folds")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    settings = _settings(arguments.env_file)
    if settings.database_url is None:
        raise DataQualityError("DATABASE_URL is required for point-in-time SPY regimes")
    examples, manifest = load_examples(arguments.dataset, arguments.manifest)
    contexts = load_segment_contexts(arguments.dataset)
    prediction_dates = sorted({item.score_date for item in examples})
    decisions: dict[date, datetime] = {}
    for (context_date, _), context in contexts.items():
        existing = decisions.setdefault(context_date, context.decision_at)
        if existing != context.decision_at:
            raise DataQualityError(f"multiple decision timestamps for {context_date}")
    decisions = {score_date: decisions[score_date] for score_date in prediction_dates}
    bars = load_benchmark_bars(settings.database_url, max(prediction_dates))
    market_regimes, benchmark_hash = build_market_regimes(decisions, bars)
    report = run_analysis(
        examples,
        contexts,
        market_regimes,
        dataset_sha256=str(manifest["content_sha256"]),
        registry_hash=str(manifest["combined_feature_registry_hash"]),
        benchmark_lineage_sha256=benchmark_hash,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    arguments.report.write_text(render_markdown(report), encoding="utf-8")
    print(
        f"analysis={report['analysis_key']}; observations={report['overall']['observation_count']}; "
        f"holdout_used={report['holdout_used']}; result_sha256={report['result_sha256']}"
    )


if __name__ == "__main__":
    main()
