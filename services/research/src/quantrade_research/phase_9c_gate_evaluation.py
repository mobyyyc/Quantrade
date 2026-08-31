"""Evaluate every frozen Phase 9C gate without tuning or threshold changes."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from dataclasses import dataclass
from datetime import date, datetime, time
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
import random
from statistics import fmean, pstdev
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

from .phase_9c_model_comparison import (
    COMPARISON_KEY,
    COMPARISON_VERSION,
    _canonical_hash,
    _sha256_file,
    spearman,
)
from .phase_9c_model_dataset import HOLDOUT_START
from .phase_9c_portfolio_attribution import ATTRIBUTION_KEY, ATTRIBUTION_VERSION
from .quality import DataQualityError
from .score_run import _dotenv_values


EVALUATION_KEY = "phase_9c_frozen_gate_evaluation"
EVALUATION_VERSION = "v1"
REFERENCE_MODEL = "deployed_active_exact"
CANDIDATES = ("phase9c_family_ridge", "phase9c_pairwise_linear")
BOOTSTRAP_SEED = 20260828
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_BLOCK_MONTHS = 3
# The frozen protocol required a seed to be persisted before fitting but did
# not actually record its numeric value.  The seed above makes this evaluation
# replayable; it cannot retroactively cure that registration violation.
PRE_FIT_BOOTSTRAP_SEED_REGISTERED = False
PORTFOLIO_COST_BPS = 25
FAMILY_KEYS = (
    "momentum_trend", "reversal", "value", "profitability_quality",
    "investment_issuance", "risk",
)
GATES = {
    "minimum_mean_monthly_ic": 0.012,
    "minimum_mean_monthly_ic_delta": 0.004,
    "minimum_positive_outer_blocks": 3,
    "minimum_worst_outer_block_ic": -0.020,
    "minimum_bootstrap_probability_positive": 0.90,
    "minimum_top_minus_bottom_spread": 0.0,
    "minimum_25bp_net_relative_return": 0.0,
    "minimum_25bp_net_relative_return_delta": 0.001,
    "minimum_positive_portfolio_blocks": 3,
    "maximum_one_way_turnover": 0.42,
    "maximum_turnover_above_reference": 0.03,
    "minimum_rank_stability": 0.80,
    "minimum_consistent_sign_fits": 3,
}


@dataclass(frozen=True, slots=True)
class PredictionRow:
    model_key: str
    outer_fold: int
    formation_date: date
    calendar_month: str
    security_id: str
    prediction: float
    target_rank: float
    relative_return: float
    row_hash: str


def _validated_json(path: Path, hash_key: str) -> dict[str, object]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DataQualityError(f"invalid Phase 9C artifact: {path}") from error
    payload = dict(document)
    recorded = payload.pop(hash_key, None)
    if not isinstance(recorded, str) or _canonical_hash(payload) != recorded:
        raise DataQualityError(f"Phase 9C artifact hash is invalid: {path}")
    return document


def _percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise DataQualityError("cannot calculate a percentile of an empty sample")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def moving_block_bootstrap(
    monthly_deltas: Sequence[float], *, seed: int = BOOTSTRAP_SEED,
    resamples: int = BOOTSTRAP_RESAMPLES, block_length: int = BOOTSTRAP_BLOCK_MONTHS,
) -> dict[str, object]:
    """Circular paired moving-block bootstrap over chronological month deltas."""
    if not monthly_deltas or resamples <= 0 or block_length <= 0:
        raise DataQualityError("invalid moving-block bootstrap inputs")
    rng = random.Random(seed)
    count = len(monthly_deltas)
    means: list[float] = []
    for _ in range(resamples):
        sample: list[float] = []
        while len(sample) < count:
            start = rng.randrange(count)
            sample.extend(monthly_deltas[(start + offset) % count] for offset in range(block_length))
        means.append(fmean(sample[:count]))
    return {
        "seed": seed,
        "resamples": resamples,
        "block_length_months": block_length,
        "observed_effect": fmean(monthly_deltas),
        "bootstrap_mean_effect": fmean(means),
        "probability_effect_positive": sum(value > 0 for value in means) / resamples,
        "percentile_interval_95": [_percentile(means, 0.025), _percentile(means, 0.975)],
    }


def _load_predictions(path: Path, expected_hash: str) -> list[PredictionRow]:
    if _sha256_file(path) != expected_hash:
        raise DataQualityError("Phase 9C predictions do not match the comparison manifest")
    rows: list[PredictionRow] = []
    seen: set[tuple[str, date, str]] = set()
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "model_key", "outer_fold", "formation_date", "calendar_month", "security_id",
            "prediction", "label_centered_rank", "benchmark_relative_return", "dataset_row_sha256",
        }
        if not reader.fieldnames or not required <= set(reader.fieldnames):
            raise DataQualityError("Phase 9C prediction schema is invalid")
        for raw in reader:
            formation = date.fromisoformat(raw["formation_date"])
            if formation >= HOLDOUT_START:
                raise DataQualityError("Phase 9C gate evaluation encountered the consumed holdout")
            row = PredictionRow(
                raw["model_key"], int(raw["outer_fold"]), formation, raw["calendar_month"],
                raw["security_id"], float(raw["prediction"]), float(raw["label_centered_rank"]),
                float(raw["benchmark_relative_return"]), raw["dataset_row_sha256"],
            )
            identity = row.model_key, row.formation_date, row.security_id
            if identity in seen or not all(math.isfinite(value) for value in (
                row.prediction, row.target_rank, row.relative_return,
            )):
                raise DataQualityError("duplicate or non-finite Phase 9C prediction")
            seen.add(identity)
            rows.append(row)
    if not rows or not {REFERENCE_MODEL, *CANDIDATES} <= {row.model_key for row in rows}:
        raise DataQualityError("Phase 9C predictions are incomplete")
    return rows


def _weekly_values(rows: Sequence[PredictionRow], *, metric: str) -> dict[date, float]:
    grouped: dict[date, list[PredictionRow]] = defaultdict(list)
    for row in rows:
        grouped[row.formation_date].append(row)
    output: dict[date, float] = {}
    for formation, items in grouped.items():
        if len(items) < 20:
            raise DataQualityError(f"insufficient paired securities on {formation}")
        if metric == "ic":
            output[formation] = spearman([
                (item.security_id, item.prediction, item.target_rank) for item in items
            ])
        elif metric == "spread":
            ranked = sorted(items, key=lambda item: (-item.prediction, item.security_id))
            count = max(1, len(ranked) // 10)
            output[formation] = (
                fmean(item.relative_return for item in ranked[:count])
                - fmean(item.relative_return for item in ranked[-count:])
            )
        else:
            raise DataQualityError(f"unknown weekly metric: {metric}")
    return output


def _monthly_values(weekly: Mapping[date, float]) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for formation, value in weekly.items():
        grouped[formation.strftime("%Y-%m")].append(value)
    return {month: fmean(values) for month, values in sorted(grouped.items())}


def _paired_rows(
    rows: Sequence[PredictionRow], candidate: str,
) -> tuple[list[PredictionRow], list[PredictionRow]]:
    candidate_index = {
        (row.formation_date, row.security_id): row for row in rows if row.model_key == candidate
    }
    reference_index = {
        (row.formation_date, row.security_id): row for row in rows if row.model_key == REFERENCE_MODEL
    }
    common = sorted(set(candidate_index) & set(reference_index))
    if not common:
        raise DataQualityError(f"no paired prediction sample for {candidate}")
    candidate_rows, reference_rows = [], []
    for key in common:
        candidate_row, reference_row = candidate_index[key], reference_index[key]
        if (
            candidate_row.row_hash != reference_row.row_hash
            or candidate_row.target_rank != reference_row.target_rank
            or candidate_row.relative_return != reference_row.relative_return
            or candidate_row.outer_fold != reference_row.outer_fold
        ):
            raise DataQualityError("paired Phase 9C predictions disagree on source evidence")
        candidate_rows.append(candidate_row)
        reference_rows.append(reference_row)
    return candidate_rows, reference_rows


def consecutive_rank_stability(rows: Sequence[PredictionRow]) -> dict[str, object]:
    grouped: dict[date, dict[str, float]] = defaultdict(dict)
    for row in rows:
        grouped[row.formation_date][row.security_id] = row.prediction
    formations = sorted(grouped)
    values: list[float] = []
    for prior, current in zip(formations, formations[1:]):
        common = sorted(set(grouped[prior]) & set(grouped[current]))
        if len(common) < 20:
            continue
        values.append(spearman([
            (security_id, grouped[prior][security_id], grouped[current][security_id])
            for security_id in common
        ]))
    if not values:
        raise DataQualityError("rank stability has no consecutive comparisons")
    return {
        "comparison_count": len(values),
        "mean_spearman": fmean(values),
        "minimum_spearman": min(values),
    }


def coefficient_sign_stability(
    fits: Mapping[str, object], candidate: str,
) -> dict[str, object]:
    signs: dict[str, list[int]] = {family: [] for family in FAMILY_KEYS}
    magnitudes: dict[str, list[float]] = {family: [] for family in FAMILY_KEYS}
    for fold in fits["fits"]:  # type: ignore[index]
        coefficients = fold[candidate]["coefficients"]
        if len(coefficients) != len(FAMILY_KEYS):
            raise DataQualityError("candidate coefficient vector has an unexpected width")
        for family, raw in zip(FAMILY_KEYS, coefficients, strict=True):
            value = float(raw)
            signs[family].append(1 if value > 0 else -1 if value < 0 else 0)
            magnitudes[family].append(abs(value))
    diagnostics = {}
    all_pass = True
    for family in FAMILY_KEYS:
        positive = signs[family].count(1)
        negative = signs[family].count(-1)
        consistent = max(positive, negative)
        passed = consistent >= GATES["minimum_consistent_sign_fits"]
        all_pass &= passed
        diagnostics[family] = {
            "fold_signs": signs[family],
            "consistent_nonzero_fit_count": consistent,
            "mean_absolute_coefficient": fmean(magnitudes[family]),
            "passed": passed,
        }
    return {
        "definition": "all six pre-registered family coefficients are material; zero is not a supporting sign",
        "families": diagnostics,
        "passed": all_pass,
    }


def _period_index(attribution: Mapping[str, object]) -> dict[tuple[str, str, date], dict[str, object]]:
    index = {}
    for period in attribution["periods"]:  # type: ignore[index]
        formation = date.fromisoformat(period["formation_date"])
        identity = period["model_key"], period["rule_key"], formation
        payload = dict(period)
        recorded = payload.pop("period_sha256", None)
        if identity in index or _canonical_hash(payload) != recorded:
            raise DataQualityError("invalid or duplicate Phase 9C portfolio period")
        index[identity] = period
    return index


def _portfolio_metrics(
    attribution: Mapping[str, object], candidate: str,
) -> dict[str, object]:
    periods = _period_index(attribution)
    candidate_all = sorted(
        (formation, period) for (model, rule, formation), period in periods.items()
        if model == candidate and rule == "exact_top20"
    )
    reference_all = sorted(
        (formation, period) for (model, rule, formation), period in periods.items()
        if model == REFERENCE_MODEL and rule == "exact_top20"
    )
    candidate_completed = {formation: period for formation, period in candidate_all if period["unavailable_reason"] is None}
    reference_completed = {formation: period for formation, period in reference_all if period["unavailable_reason"] is None}
    paired_dates = sorted(set(candidate_completed) & set(reference_completed))
    if not paired_dates:
        raise DataQualityError(f"no completed paired portfolio periods for {candidate}")

    def net(period: Mapping[str, object]) -> float:
        return float(period["gross_relative_return"]) - float(period["one_way_turnover"]) * PORTFOLIO_COST_BPS / 10_000

    own_net = {formation: net(period) for formation, period in candidate_completed.items()}
    paired_delta = [net(candidate_completed[item]) - net(reference_completed[item]) for item in paired_dates]
    block_values: dict[int, list[float]] = defaultdict(list)
    fold_by_month = {
        202307: 1, 202308: 1, 202309: 1, 202310: 1, 202311: 1, 202312: 1,
        202401: 2, 202402: 2, 202403: 2, 202404: 2, 202405: 2, 202406: 2,
        202407: 3, 202408: 3, 202409: 3, 202410: 3, 202411: 3, 202412: 3,
    }
    for formation, value in own_net.items():
        block = fold_by_month.get(formation.year * 100 + formation.month, 4)
        block_values[block].append(value)
    block_means = {str(block): (fmean(block_values[block]) if block_values[block] else None) for block in range(1, 5)}
    positive_blocks = sum(value is not None and value > 0 for value in block_means.values())

    candidate_turnovers = [float(period["one_way_turnover"]) for _, period in candidate_all[1:]]
    reference_turnovers = [float(period["one_way_turnover"]) for _, period in reference_all[1:]]
    if not candidate_turnovers or not reference_turnovers:
        raise DataQualityError("portfolio turnover has no recurring formations")
    candidate_turnover = fmean(candidate_turnovers)
    reference_turnover = fmean(reference_turnovers)
    return {
        "completed_candidate_periods": len(own_net),
        "paired_completed_periods": len(paired_dates),
        "paired_formations": [item.isoformat() for item in paired_dates],
        "candidate_mean_25bp_net_relative_return": fmean(own_net.values()),
        "paired_mean_25bp_net_relative_return_delta": fmean(paired_delta),
        "outer_block_mean_25bp_net_relative_return": block_means,
        "positive_outer_blocks": positive_blocks,
        "mean_recurring_one_way_turnover": candidate_turnover,
        "reference_mean_recurring_one_way_turnover": reference_turnover,
        "turnover_delta": candidate_turnover - reference_turnover,
    }


def _load_spy_bars(database_url: str, through: date) -> list[tuple[date, float, datetime]]:
    import psycopg
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute(
            """SELECT session_date,close_price,available_at
                 FROM quantrade.benchmark_daily_price_bars
                WHERE benchmark_ticker='SPY' AND session='regular'
                  AND adjustment_basis='split_adjusted' AND session_date <= %s
                ORDER BY session_date""",
            (through,),
        )
        rows = [(item[0], float(item[1]), item[2]) for item in cursor.fetchall()]
    if not rows or len({item[0] for item in rows}) != len(rows):
        raise DataQualityError("SPY regime history is empty or duplicated")
    return rows


def _regimes(
    formations: Sequence[date], bars: Sequence[tuple[date, float, datetime]],
) -> tuple[dict[date, str], str]:
    output = {}
    used = set()
    toronto = ZoneInfo("America/Toronto")
    for formation in sorted(set(formations)):
        decision = datetime.combine(formation, time(20, 0), toronto)
        eligible = [item for item in bars if item[0] <= formation and item[2] <= decision]
        if len(eligible) < 61 or eligible[-1][0] != formation:
            output[formation] = "unavailable"
            continue
        window = eligible[-61:]
        used.update(window)
        trend = window[-1][1] / window[0][1] - 1
        returns = [window[index][1] / window[index - 1][1] - 1 for index in range(1, len(window))]
        volatility = pstdev(returns) * math.sqrt(252)
        trend_key = "bullish" if trend >= 0.05 else "bearish" if trend <= -0.05 else "range_bound"
        volatility_key = "low_vol" if volatility < 0.15 else "high_vol" if volatility >= 0.25 else "normal_vol"
        output[formation] = f"{trend_key}|{volatility_key}"
    canonical = "\n".join(
        f"{item[0].isoformat()}|{item[1]:.17g}|{item[2].isoformat()}" for item in sorted(used)
    )
    return output, sha256(canonical.encode()).hexdigest()


def _regime_diagnostics(
    weekly_ic: Mapping[date, float], weekly_spread: Mapping[date, float], regimes: Mapping[date, str],
) -> dict[str, object]:
    grouped_ic: dict[str, list[float]] = defaultdict(list)
    grouped_spread: dict[str, list[float]] = defaultdict(list)
    for formation, value in weekly_ic.items():
        grouped_ic[regimes.get(formation, "unavailable")].append(value)
        grouped_spread[regimes.get(formation, "unavailable")].append(weekly_spread[formation])
    return {
        key: {
            "formation_count": len(grouped_ic[key]),
            "mean_weekly_rank_ic": fmean(grouped_ic[key]),
            "mean_top_minus_bottom_spread": fmean(grouped_spread[key]),
        }
        for key in sorted(grouped_ic)
    }


def _coverage_gate(panel: Mapping[str, object]) -> dict[str, object]:
    checks = panel.get("gates")
    if not isinstance(checks, dict):
        raise DataQualityError("Phase 9C panel lacks frozen coverage gates")
    required = {
        "point_in_time_lineage", "score_aggregate_coverage", "score_minimum_coverage",
        "market_family_minimum_coverage", "accounting_family_aggregate_coverage",
        "accounting_family_minimum_coverage", "minimum_three_informative_families",
        "raw_feature_aggregate_coverage", "deterministic_replay",
    }
    return {
        "passed": panel.get("passed") is True and panel.get("lineage_violations") == 0
        and required <= set(checks) and all(checks[item] is True for item in required),
        "checks": {item: checks.get(item) for item in sorted(required)},
        "score_aggregate_coverage": panel.get("score_aggregate_coverage"),
        "score_minimum_coverage": panel.get("score_minimum_coverage"),
        "family_aggregate_informative_coverage": panel.get("family_aggregate_informative_coverage"),
        "family_minimum_informative_coverage": panel.get("family_minimum_informative_coverage"),
        "raw_aggregate_coverage": panel.get("raw_aggregate_coverage"),
    }


def evaluate(
    *, database_url: str, comparison_path: Path, predictions_path: Path, fits_path: Path,
    folds_path: Path, panel_path: Path, attribution_path: Path, protocol_path: Path,
    destination: Path,
) -> dict[str, object]:
    if destination.exists():
        raise DataQualityError(f"refusing to overwrite immutable gate evaluation: {destination}")
    comparison = _validated_json(comparison_path, "report_hash")
    fits = _validated_json(fits_path, "fits_sha256")
    folds = _validated_json(folds_path, "fold_sha256")
    panel = _validated_json(panel_path, "report_hash")
    attribution = _validated_json(attribution_path, "report_sha256")
    if comparison.get("comparison_key") != COMPARISON_KEY or comparison.get("comparison_version") != COMPARISON_VERSION:
        raise DataQualityError("unexpected Phase 9C comparison artifact")
    if attribution.get("attribution_key") != ATTRIBUTION_KEY or attribution.get("attribution_version") != ATTRIBUTION_VERSION:
        raise DataQualityError("unexpected Phase 9C attribution artifact")
    if _sha256_file(fits_path) != comparison.get("fits_file_sha256"):
        raise DataQualityError("fits file does not match Phase 9C comparison")
    if folds.get("fold_sha256") != comparison.get("fold_sha256") or folds.get("label_overlap_violations") != 0:
        raise DataQualityError("Phase 9C folds fail their frozen overlap audit")
    if any(document.get("holdout_used") is not False for document in (comparison, panel, attribution)):
        raise DataQualityError("a Phase 9C source artifact used the consumed holdout")
    predictions = _load_predictions(predictions_path, str(comparison["prediction_file_sha256"]))
    regime_map, regime_lineage = _regimes(
        [row.formation_date for row in predictions],
        _load_spy_bars(database_url, max(row.formation_date for row in predictions)),
    )
    coverage = _coverage_gate(panel)
    protocol_sha256 = _sha256_file(protocol_path)
    evaluations = {}
    for candidate in CANDIDATES:
        candidate_rows, reference_rows = _paired_rows(predictions, candidate)
        candidate_ic_weekly = _weekly_values(candidate_rows, metric="ic")
        reference_ic_weekly = _weekly_values(reference_rows, metric="ic")
        candidate_monthly = _monthly_values(candidate_ic_weekly)
        reference_monthly = _monthly_values(reference_ic_weekly)
        common_months = sorted(set(candidate_monthly) & set(reference_monthly))
        if len(common_months) < 12:
            raise DataQualityError(f"too few paired calendar months for {candidate}")
        deltas = [candidate_monthly[item] - reference_monthly[item] for item in common_months]
        bootstrap = moving_block_bootstrap(deltas)
        fold_by_date = {row.formation_date: row.outer_fold for row in candidate_rows}
        outer_values: dict[int, list[float]] = defaultdict(list)
        for formation, value in candidate_ic_weekly.items():
            outer_values[fold_by_date[formation]].append(value)
        outer_means = {str(fold): fmean(outer_values[fold]) for fold in range(1, 5)}
        candidate_spread_weekly = _weekly_values(candidate_rows, metric="spread")
        spread_monthly = _monthly_values(candidate_spread_weekly)
        portfolio = _portfolio_metrics(attribution, candidate)
        stability = consecutive_rank_stability(candidate_rows)
        signs = coefficient_sign_stability(fits, candidate)
        gate_checks = {
            "1_integrity": (
                panel.get("lineage_violations") == 0
                and folds.get("label_overlap_violations") == 0
                and panel.get("gates", {}).get("deterministic_replay") is True
                and PRE_FIT_BOOTSTRAP_SEED_REGISTERED
            ),
            "2_coverage": coverage["passed"],
            "3_mean_ic_and_delta": (
                fmean(candidate_monthly.values()) >= GATES["minimum_mean_monthly_ic"]
                and fmean(deltas) >= GATES["minimum_mean_monthly_ic_delta"]
            ),
            "4_outer_block_ic": (
                sum(value > 0 for value in outer_means.values()) >= GATES["minimum_positive_outer_blocks"]
                and min(outer_means.values()) > GATES["minimum_worst_outer_block_ic"]
            ),
            "5_paired_bootstrap": (
                bootstrap["probability_effect_positive"] >= GATES["minimum_bootstrap_probability_positive"]
            ),
            "6_top_minus_bottom": fmean(spread_monthly.values()) > GATES["minimum_top_minus_bottom_spread"],
            "7_net_portfolio": (
                portfolio["candidate_mean_25bp_net_relative_return"] > GATES["minimum_25bp_net_relative_return"]
                and portfolio["paired_mean_25bp_net_relative_return_delta"] >= GATES["minimum_25bp_net_relative_return_delta"]
                and portfolio["positive_outer_blocks"] >= GATES["minimum_positive_portfolio_blocks"]
            ),
            "8_turnover": (
                portfolio["mean_recurring_one_way_turnover"] <= GATES["maximum_one_way_turnover"]
                and portfolio["turnover_delta"] <= GATES["maximum_turnover_above_reference"]
            ),
            "9_rank_stability": stability["mean_spearman"] >= GATES["minimum_rank_stability"],
            "10_coefficient_signs": signs["passed"],
        }
        evaluations[candidate] = {
            "decision": "freeze" if all(gate_checks.values()) else "no-freeze",
            "paired_security_rows": len(candidate_rows),
            "paired_formation_count": len(candidate_ic_weekly),
            "paired_calendar_month_count": len(common_months),
            "paired_calendar_months": common_months,
            "mean_monthly_rank_ic": fmean(candidate_monthly.values()),
            "reference_mean_monthly_rank_ic": fmean(reference_monthly.values()),
            "paired_mean_monthly_rank_ic_delta": fmean(deltas),
            "monthly_rank_ic": candidate_monthly,
            "reference_monthly_rank_ic": reference_monthly,
            "monthly_rank_ic_delta": dict(zip(common_months, deltas, strict=True)),
            "outer_block_mean_rank_ic": outer_means,
            "positive_outer_blocks": sum(value > 0 for value in outer_means.values()),
            "worst_outer_block_rank_ic": min(outer_means.values()),
            "paired_moving_block_bootstrap": bootstrap,
            "mean_monthly_top_minus_bottom_spread": fmean(spread_monthly.values()),
            "portfolio": portfolio,
            "rank_stability": stability,
            "coefficient_sign_stability": signs,
            "regime_diagnostics": _regime_diagnostics(candidate_ic_weekly, candidate_spread_weekly, regime_map),
            "gate_checks": gate_checks,
            "failed_gates": [key for key, passed in gate_checks.items() if not passed],
        }
    decision = "freeze" if any(item["decision"] == "freeze" for item in evaluations.values()) else "no-freeze"
    report: dict[str, object] = {
        "evaluation_key": EVALUATION_KEY,
        "evaluation_version": EVALUATION_VERSION,
        "protocol_key": "tier_b_weekly_family_rank_v1",
        "protocol_sha256": protocol_sha256,
        "bootstrap_registration": {
            "seed": BOOTSTRAP_SEED,
            "resamples": BOOTSTRAP_RESAMPLES,
            "moving_block_months": BOOTSTRAP_BLOCK_MONTHS,
            "pre_fit_numeric_seed_registered": PRE_FIT_BOOTSTRAP_SEED_REGISTERED,
            "limitation": (
                "the frozen protocol required a seed before fitting but omitted its numeric value; "
                "this deterministic evaluation seed does not retroactively satisfy that contract"
            ),
        },
        "frozen_gates": GATES,
        "holdout_start": HOLDOUT_START.isoformat(),
        "holdout_used": False,
        "model_refit": False,
        "thresholds_changed_after_results": False,
        "source_comparison_report_sha256": comparison["report_hash"],
        "source_prediction_file_sha256": comparison["prediction_file_sha256"],
        "source_fits_file_sha256": comparison["fits_file_sha256"],
        "source_fold_sha256": comparison["fold_sha256"],
        "source_feature_panel_report_sha256": panel["report_hash"],
        "source_attribution_report_sha256": attribution["report_sha256"],
        "coverage": coverage,
        "spy_regime_definition": {
            "lookback_sessions": 60,
            "trend": "bullish >= +5%; bearish <= -5%; otherwise range-bound",
            "annualized_volatility": "low < 15%; normal 15% to <25%; high >=25%",
            "usage": "diagnostic only; never used for model selection or gates",
            "lineage_sha256": regime_lineage,
        },
        "candidate_evaluations": evaluations,
        "decision": decision,
        "selected_candidate": next((key for key in CANDIDATES if evaluations[key]["decision"] == "freeze"), None),
        "limitations": [
            "Tier-B current-survivors research is survivorship biased",
            "current sectors are static and not historical point-in-time classifications",
            "the July 2025 through June 2026 consumed holdout was not used",
            "a no-freeze decision cannot be reversed by relaxing this protocol's gates",
            "private research does not guarantee future SPY outperformance",
        ],
        "status": "immutable_gate_decision",
    }
    report["report_sha256"] = _canonical_hash(report)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the frozen Phase 9C gates")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--comparison", type=Path, default=Path("data/derived/phase_9c_nested_weekly_rank_predictions_v1.json"))
    parser.add_argument("--predictions", type=Path, default=Path("data/derived/phase_9c_nested_weekly_rank_predictions_v1.csv.gz"))
    parser.add_argument("--fits", type=Path, default=Path("data/derived/phase_9c_nested_weekly_rank_predictions_v1.fits.json"))
    parser.add_argument("--folds", type=Path, default=Path("data/derived/phase_9c_weekly_rank_development_v1.folds.json"))
    parser.add_argument("--panel", type=Path, default=Path("data/derived/phase_9c_weekly_feature_panel_v1.json"))
    parser.add_argument("--attribution", type=Path, default=Path("data/derived/phase_9c_monthly_portfolio_attribution_v1.json"))
    parser.add_argument("--protocol", type=Path, default=Path("PHASE_9C_RESEARCH_PROTOCOL.md"))
    parser.add_argument("--output", type=Path, default=Path("data/derived/phase_9c_frozen_gate_evaluation_v1.json"))
    arguments = parser.parse_args()
    database_url = _dotenv_values(arguments.env_file).get("DATABASE_URL")
    if not database_url:
        raise DataQualityError("DATABASE_URL is required for point-in-time SPY regime diagnostics")
    report = evaluate(
        database_url=database_url, comparison_path=arguments.comparison,
        predictions_path=arguments.predictions, fits_path=arguments.fits,
        folds_path=arguments.folds, panel_path=arguments.panel,
        attribution_path=arguments.attribution, protocol_path=arguments.protocol,
        destination=arguments.output,
    )
    failures = {
        key: value["failed_gates"] for key, value in report["candidate_evaluations"].items()
    }
    print(f"decision={report['decision']}; selected={report['selected_candidate']}; failures={failures}")


if __name__ == "__main__":
    main()
