"""Attribute Phase 9C model and portfolio-rule effects at true month ends."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from statistics import fmean
from typing import Mapping, Sequence

from .phase_9c_feature_panel import (
    _accounting_snapshot,
    _decision_at,
    _fact_eligibility,
    _fact_selection_key,
    _formation_digest,
    _formation_rows,
    _load_context,
    _load_sec_facts,
)
from .phase_9c_features import FAMILY_KEYS
from .phase_9c_model_comparison import (
    ACTIVE_MODEL_COLUMNS,
    COMPARISON_KEY,
    COMPARISON_VERSION,
    Example,
    LinearFit,
    _attach_active_features,
    _load_static_sectors_and_liquidity,
)
from .phase_9c_model_dataset import (
    HOLDOUT_START,
    _label_outcome,
    _load_label_inputs,
)
from .quality import DataQualityError
from .score_run import _dotenv_values


ATTRIBUTION_KEY = "phase_9c_monthly_portfolio_attribution"
ATTRIBUTION_VERSION = "v1"
PORTFOLIO_SIZE = 20
RETENTION_RANK = 30
COST_CASES_BPS = (5, 10, 25, 50)
MODEL_KEYS = (
    "deployed_active_exact",
    "active_family_refit",
    "phase9c_family_ridge",
    "phase9c_pairwise_linear",
)
RULE_KEYS = ("exact_top20", "top20_entry_top30_retention")


@dataclass(frozen=True, slots=True)
class MonthlyScore:
    formation_date: date
    security_id: str
    model_key: str
    prediction: float


@dataclass(frozen=True, slots=True)
class PortfolioPeriod:
    model_key: str
    rule_key: str
    formation_date: date
    entry_date: date | None
    outcome_date: date | None
    security_ids: tuple[str, ...]
    ranking_sha256: str
    retained_count: int
    additions: int
    removals: int
    one_way_turnover: float
    portfolio_return: float | None
    benchmark_return: float | None
    gross_relative_return: float | None
    selected_label_sha256: tuple[str, ...]
    unavailable_reason: str | None


def _canonical_hash(document: object) -> str:
    return sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validated_json(path: Path, *, hash_key: str) -> dict[str, object]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DataQualityError(f"invalid Phase 9C artifact: {path}") from error
    payload = dict(document)
    recorded = payload.pop(hash_key, None)
    if _canonical_hash(payload) != recorded:
        raise DataQualityError(f"Phase 9C artifact hash is invalid: {path}")
    return document


def _load_comparison(
    comparison_manifest_path: Path, fits_path: Path, predictions_path: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    manifest = _validated_json(comparison_manifest_path, hash_key="report_hash")
    fits = _validated_json(fits_path, hash_key="fits_sha256")
    if manifest.get("comparison_key") != COMPARISON_KEY or manifest.get("comparison_version") != COMPARISON_VERSION:
        raise DataQualityError("unexpected Phase 9C model-comparison version")
    if fits.get("comparison_key") != COMPARISON_KEY or fits.get("comparison_version") != COMPARISON_VERSION:
        raise DataQualityError("unexpected Phase 9C fit artifact version")
    if manifest.get("holdout_used") is not False or manifest.get("outer_results_used_for_selection") is not False:
        raise DataQualityError("Phase 9C model comparison is not safe for attribution")
    if _sha256_file(fits_path) != manifest.get("fits_file_sha256"):
        raise DataQualityError("Phase 9C fits do not match the comparison manifest")
    if _sha256_file(predictions_path) != manifest.get("prediction_file_sha256"):
        raise DataQualityError("Phase 9C weekly predictions do not match the comparison manifest")
    return manifest, fits


def _load_fold_blocks(path: Path, expected_hash: str) -> dict[int, tuple[date, date]]:
    folds = _validated_json(path, hash_key="fold_sha256")
    if folds.get("fold_sha256") != expected_hash or folds.get("holdout_start") != HOLDOUT_START.isoformat():
        raise DataQualityError("Phase 9C portfolio attribution received unexpected folds")
    if folds.get("label_overlap_violations") != 0:
        raise DataQualityError("Phase 9C fold artifact has label-overlap violations")
    return {
        int(item["outer_fold"]): (
            date.fromisoformat(str(item["registered_block"][0])),
            date.fromisoformat(str(item["registered_block"][1])),
        )
        for item in folds["outer_folds"]
    }


def _linear_fit(document: Mapping[str, object]) -> LinearFit:
    try:
        fit = LinearFit(
            tuple(float(item) for item in document["feature_means"]),
            tuple(float(item) for item in document["feature_scales"]),
            float(document["target_mean"]),
            tuple(float(item) for item in document["coefficients"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise DataQualityError("invalid Phase 9C fitted model") from error
    if not fit.means or not (len(fit.means) == len(fit.scales) == len(fit.coefficients)):
        raise DataQualityError("Phase 9C fitted model has inconsistent vectors")
    return fit


def _fit_index(fits: Mapping[str, object]) -> dict[tuple[int, str], LinearFit]:
    result: dict[tuple[int, str], LinearFit] = {}
    for fold in fits["fits"]:  # type: ignore[index]
        fold_number = int(fold["outer_fold"])
        for model_key in MODEL_KEYS:
            result[fold_number, model_key] = _linear_fit(fold[model_key])
    expected = {(fold, model) for fold in range(1, 5) for model in MODEL_KEYS}
    if set(result) != expected:
        raise DataQualityError("Phase 9C fit artifact is incomplete")
    return result


def _month_end_feature_examples(
    database_url: str, *, start: date, end: date,
) -> tuple[
    list[Example], tuple[str, ...], tuple[date, ...], str, dict[date, int],
    frozenset[tuple[date, str]],
]:
    security_ids, formations, prices, benchmark, actions = _load_context(
        database_url, start=start, end=end, formation_rule="month_end",
    )
    facts = _load_sec_facts(database_url, security_ids, formations)
    fact_positions = {security_id: 0 for security_id in security_ids}
    fact_state: dict[str, dict[str, object]] = {security_id: {} for security_id in security_ids}
    accounting_cache = {}
    accounting_catalog: dict[str, dict[str, object]] = {}
    rows: list[Example] = []
    active_raw: dict[tuple[date, str], list[float | None]] = {}
    formation_hashes: list[str] = []
    eligible_counts: dict[date, int] = {}
    phase9c_eligible: set[tuple[date, str]] = set()
    for formation in formations:
        decision = _decision_at(formation)
        for security_id in security_ids:
            events = facts.get(security_id, ())
            position = fact_positions[security_id]
            state = fact_state[security_id]
            changed = security_id not in accounting_cache
            while position < len(events) and _fact_eligibility(events[position]) <= decision:
                fact = events[position]
                current = state.get(fact.filing_fact_key)
                if current is None or _fact_selection_key(fact) > _fact_selection_key(current):
                    state[fact.filing_fact_key] = fact
                    changed = True
                position += 1
            fact_positions[security_id] = position
            if changed:
                resolved = tuple(sorted(
                    state.values(), key=lambda item: (item.concept, item.period_end, item.lineage_key),
                ))
                accounting_cache[security_id] = _accounting_snapshot(resolved, formation)
        raw, ranked, families = _formation_rows(
            formation=formation, security_ids=security_ids, prices=prices, benchmark=benchmark,
            accounting=accounting_cache, actions=actions, catalog=accounting_catalog,
        )
        formation_hashes.append(f"{formation.isoformat()}|{_formation_digest(security_ids, raw, ranked, families)}")
        eligible_count = 0
        for security_id in security_ids:
            informative = sum(cell.informative for cell in families[security_id].values())
            eligible = informative >= 3
            eligible_count += eligible
            if eligible:
                phase9c_eligible.add((formation, security_id))
            values = tuple(float(families[security_id][key].value) for key in FAMILY_KEYS)
            rows.append(Example(
                formation, formation.strftime("%Y-%m"), security_id, 0.0, 0.0,
                1.0, values, _formation_digest(
                    (security_id,),
                    {security_id: raw[security_id]},
                    {security_id: ranked[security_id]},
                    {security_id: families[security_id]},
                ),
            ))
            active_raw[formation, security_id] = [
                float(raw[security_id]["momentum_12_1"].value) if raw[security_id]["momentum_12_1"].value is not None else None,
                float(raw[security_id]["relative_strength_6m"].value) if raw[security_id]["relative_strength_6m"].value is not None else None,
                float(raw[security_id]["realized_volatility_60d"].value) if raw[security_id]["realized_volatility_60d"].value is not None else None,
                None, None, None,
            ]
        eligible_counts[formation] = eligible_count
    sectors, active_values, active_source_hash = _load_static_sectors_and_liquidity(
        database_url, security_ids=security_ids, formations=formations,
    )
    rows = _attach_active_features(rows, active_raw, sectors, active_values)
    source_hash = _canonical_hash({
        "formation_hashes": formation_hashes,
        "active_reference_source_sha256": active_source_hash,
        "formation_rule": "final regular market session of each calendar month",
    })
    return rows, security_ids, formations, source_hash, eligible_counts, frozenset(phase9c_eligible)


def _fold_for(formation: date, blocks: Mapping[int, tuple[date, date]]) -> int:
    matches = [fold for fold, (start, end) in blocks.items() if start <= formation <= end]
    if len(matches) != 1:
        raise DataQualityError(f"month-end formation does not map to exactly one outer fold: {formation}")
    return matches[0]


def _score_month_ends(
    rows: Sequence[Example], fits: Mapping[tuple[int, str], LinearFit],
    blocks: Mapping[int, tuple[date, date]], phase9c_eligible: frozenset[tuple[date, str]],
) -> dict[tuple[str, date], list[MonthlyScore]]:
    output: dict[tuple[str, date], list[MonthlyScore]] = defaultdict(list)
    for row in rows:
        fold = _fold_for(row.formation_date, blocks)
        for model_key in MODEL_KEYS:
            if model_key in {"deployed_active_exact", "active_family_refit"}:
                features = row.active_features
            else:
                features = (
                    row.family_features
                    if (row.formation_date, row.security_id) in phase9c_eligible else None
                )
            if features is not None:
                output[model_key, row.formation_date].append(MonthlyScore(
                    row.formation_date, row.security_id, model_key,
                    fits[fold, model_key].predict(features),
                ))
    for (model_key, formation), scores in output.items():
        if len(scores) < PORTFOLIO_SIZE:
            raise DataQualityError(f"{model_key} has fewer than 20 eligible month-end scores on {formation}")
    return output


def _ranked_ids(scores: Sequence[MonthlyScore]) -> tuple[str, ...]:
    return tuple(item.security_id for item in sorted(scores, key=lambda item: (-item.prediction, item.security_id)))


def select_portfolio(
    ranked_ids: Sequence[str], *, rule_key: str, prior: Sequence[str] | None,
) -> tuple[str, ...]:
    if len(ranked_ids) < RETENTION_RANK or len(set(ranked_ids)) != len(ranked_ids):
        raise DataQualityError("portfolio selection requires at least 30 unique ranked securities")
    if rule_key == "exact_top20" or prior is None:
        return tuple(ranked_ids[:PORTFOLIO_SIZE])
    if rule_key != "top20_entry_top30_retention":
        raise DataQualityError(f"unknown Phase 9C portfolio rule: {rule_key}")
    top30 = set(ranked_ids[:RETENTION_RANK])
    retained = {security_id for security_id in prior if security_id in top30}
    selected = [security_id for security_id in ranked_ids if security_id in retained]
    selected.extend(
        security_id for security_id in ranked_ids
        if security_id not in retained and len(selected) < PORTFOLIO_SIZE
    )
    return tuple(selected[:PORTFOLIO_SIZE])


def _load_month_end_labels(database_url: str, security_ids: Sequence[str], formations: Sequence[date]):
    windows, prices, benchmark, actions, benchmark_actions = _load_label_inputs(
        database_url, security_ids=security_ids, formations=formations,
    )
    outcomes = {}
    exclusions = {}
    for formation, window in sorted(windows.items()):
        for security_id in security_ids:
            outcome, reason = _label_outcome(
                security_id=security_id, window=window,
                security_prices=prices.get(security_id, {}), benchmark_prices=benchmark,
                security_actions=actions.get(security_id, ()), benchmark_actions=benchmark_actions,
            )
            if outcome is None:
                exclusions[formation, security_id] = reason or "unknown_label_exclusion"
            else:
                outcomes[formation, security_id] = outcome
    return windows, outcomes, exclusions


def _period(
    *, model_key: str, rule_key: str, formation: date, selected: tuple[str, ...],
    ranking_sha256: str, prior: tuple[str, ...] | None, windows, outcomes, exclusions,
) -> PortfolioPeriod:
    retained = len(set(selected) & set(prior or ()))
    additions = PORTFOLIO_SIZE - retained
    removals = 0 if prior is None else PORTFOLIO_SIZE - retained
    turnover = 1.0 if prior is None else 1.0 - retained / PORTFOLIO_SIZE
    window = windows.get(formation)
    if window is None:
        return PortfolioPeriod(
            model_key, rule_key, formation, None, None, selected, ranking_sha256, retained, additions,
            removals, turnover, None, None, None, (), "label_window_crosses_holdout_or_is_incomplete",
        )
    missing = [security_id for security_id in selected if (formation, security_id) not in outcomes]
    if missing:
        reasons = sorted({exclusions.get((formation, security_id), "missing_label") for security_id in missing})
        return PortfolioPeriod(
            model_key, rule_key, formation, window.entry_date, window.outcome_date, selected, ranking_sha256,
            retained, additions, removals, turnover, None, None, None, (),
            "selected_outcome_unavailable:" + ",".join(reasons),
        )
    selected_outcomes = [outcomes[formation, security_id] for security_id in selected]
    benchmark_values = {item.benchmark_return for item in selected_outcomes}
    if len(benchmark_values) != 1:
        raise DataQualityError("selected outcomes disagree on the matching SPY return")
    portfolio_return = fmean(float(item.security_return) for item in selected_outcomes)
    benchmark_return = float(next(iter(benchmark_values)))
    return PortfolioPeriod(
        model_key, rule_key, formation, window.entry_date, window.outcome_date, selected, ranking_sha256,
        retained, additions, removals, turnover, portfolio_return, benchmark_return,
        portfolio_return - benchmark_return,
        tuple(item.label_sha256 for item in selected_outcomes), None,
    )


def build_periods(scores, formations, windows, outcomes, exclusions) -> list[PortfolioPeriod]:
    periods: list[PortfolioPeriod] = []
    for model_key in MODEL_KEYS:
        for rule_key in RULE_KEYS:
            prior: tuple[str, ...] | None = None
            for formation in formations:
                month_scores = scores[model_key, formation]
                ranked = _ranked_ids(month_scores)
                ranking_sha256 = _canonical_hash([
                    [item.security_id, format(item.prediction, ".17g")]
                    for item in sorted(month_scores, key=lambda item: (-item.prediction, item.security_id))
                ])
                selected = select_portfolio(ranked, rule_key=rule_key, prior=prior)
                periods.append(_period(
                    model_key=model_key, rule_key=rule_key, formation=formation,
                    selected=selected, ranking_sha256=ranking_sha256, prior=prior,
                    windows=windows, outcomes=outcomes,
                    exclusions=exclusions,
                ))
                prior = selected
    return periods


def _cumulative(values: Sequence[float]) -> float:
    nav = 1.0
    for value in values:
        nav *= 1.0 + value
    return nav - 1.0


def summarize_periods(periods: Sequence[PortfolioPeriod], included_formations: set[date]) -> dict[str, object]:
    selected = [item for item in periods if item.formation_date in included_formations]
    if not selected or any(item.gross_relative_return is None for item in selected):
        raise DataQualityError("portfolio summary requires completed common periods")
    gross = [float(item.gross_relative_return) for item in selected if item.gross_relative_return is not None]
    portfolio = [float(item.portfolio_return) for item in selected if item.portfolio_return is not None]
    benchmark = [float(item.benchmark_return) for item in selected if item.benchmark_return is not None]
    recurring_turnover = [item.one_way_turnover for item in selected[1:]]
    mean_turnover = fmean(recurring_turnover) if recurring_turnover else 0.0
    cumulative_portfolio, cumulative_benchmark = _cumulative(portfolio), _cumulative(benchmark)
    return {
        "formation_count": len(selected),
        "mean_monthly_gross_relative_return": fmean(gross),
        "cumulative_portfolio_return": cumulative_portfolio,
        "cumulative_benchmark_return": cumulative_benchmark,
        "cumulative_relative_return": cumulative_portfolio - cumulative_benchmark,
        "mean_recurring_one_way_turnover": mean_turnover,
        "mean_retained_count": fmean(item.retained_count for item in selected[1:]) if len(selected) > 1 else 0.0,
        "mean_additions": fmean(item.additions for item in selected[1:]) if len(selected) > 1 else 0.0,
        "mean_removals": fmean(item.removals for item in selected[1:]) if len(selected) > 1 else 0.0,
        "mean_monthly_net_relative_return_by_one_way_cost_bps": {
            str(cost): fmean(
                float(item.gross_relative_return) - item.one_way_turnover * cost / 10000.0
                for item in selected if item.gross_relative_return is not None
            )
            for cost in COST_CASES_BPS
        },
        "break_even_one_way_cost_bps": (
            fmean(gross) / fmean(item.one_way_turnover for item in selected) * 10000.0
            if any(item.one_way_turnover > 0 for item in selected) else None
        ),
    }


def run_attribution(
    *, database_url: str, comparison_manifest_path: Path, fits_path: Path,
    predictions_path: Path, folds_path: Path, destination: Path,
) -> dict[str, object]:
    if destination.exists():
        raise DataQualityError(f"refusing to overwrite immutable Phase 9C attribution: {destination}")
    comparison, fits_document = _load_comparison(comparison_manifest_path, fits_path, predictions_path)
    blocks = _load_fold_blocks(folds_path, str(comparison["fold_sha256"]))
    fits = _fit_index(fits_document)
    start = min(value[0] for value in blocks.values())
    end = max(value[1] for value in blocks.values())
    (
        feature_rows, security_ids, formations, feature_source_hash,
        eligible_counts, phase9c_eligible,
    ) = _month_end_feature_examples(database_url, start=start, end=end)
    if any(formation >= HOLDOUT_START for formation in formations):
        raise DataQualityError("month-end feature inference crossed into the consumed holdout")
    scores = _score_month_ends(feature_rows, fits, blocks, phase9c_eligible)
    windows, outcomes, exclusions = _load_month_end_labels(database_url, security_ids, formations)
    periods = build_periods(scores, formations, windows, outcomes, exclusions)
    completed_by_path = {
        (model, rule): {
            item.formation_date for item in periods
            if item.model_key == model and item.rule_key == rule and item.unavailable_reason is None
        }
        for model in MODEL_KEYS for rule in RULE_KEYS
    }
    global_common_formations = set.intersection(*completed_by_path.values())
    summaries = {
        model: {
            rule: summarize_periods(
                [item for item in periods if item.model_key == model and item.rule_key == rule],
                completed_by_path[model, rule],
            )
            for rule in RULE_KEYS
        }
        for model in MODEL_KEYS
    }
    attribution = {}
    for model in MODEL_KEYS:
        model_effect_dates = (
            completed_by_path[model, "exact_top20"]
            & completed_by_path["deployed_active_exact", "exact_top20"]
        )
        buffer_effect_dates = (
            completed_by_path[model, "exact_top20"]
            & completed_by_path[model, "top20_entry_top30_retention"]
        )
        if not model_effect_dates or not buffer_effect_dates:
            raise DataQualityError(f"insufficient paired periods for portfolio attribution: {model}")
        model_exact = summarize_periods(
            [item for item in periods if item.model_key == model and item.rule_key == "exact_top20"],
            model_effect_dates,
        )
        deployed_exact = summarize_periods(
            [item for item in periods if item.model_key == "deployed_active_exact" and item.rule_key == "exact_top20"],
            model_effect_dates,
        )
        buffer_exact = summarize_periods(
            [item for item in periods if item.model_key == model and item.rule_key == "exact_top20"],
            buffer_effect_dates,
        )
        buffer_retained = summarize_periods(
            [item for item in periods if item.model_key == model and item.rule_key == "top20_entry_top30_retention"],
            buffer_effect_dates,
        )
        attribution[model] = {
            "model_effect_paired_formation_count": len(model_effect_dates),
            "model_effect_paired_formations": [item.isoformat() for item in sorted(model_effect_dates)],
            "model_effect_under_exact_rule_mean_gross_relative_return": (
                model_exact["mean_monthly_gross_relative_return"]
                - deployed_exact["mean_monthly_gross_relative_return"]
            ),
            "model_effect_under_exact_rule_mean_25bp_net_relative_return": (
                model_exact["mean_monthly_net_relative_return_by_one_way_cost_bps"]["25"]
                - deployed_exact["mean_monthly_net_relative_return_by_one_way_cost_bps"]["25"]
            ),
            "model_effect_under_exact_rule_mean_recurring_turnover": (
                model_exact["mean_recurring_one_way_turnover"]
                - deployed_exact["mean_recurring_one_way_turnover"]
            ),
            "buffer_effect_paired_formation_count": len(buffer_effect_dates),
            "buffer_effect_paired_formations": [item.isoformat() for item in sorted(buffer_effect_dates)],
            "buffer_effect_mean_gross_relative_return": (
                buffer_retained["mean_monthly_gross_relative_return"]
                - buffer_exact["mean_monthly_gross_relative_return"]
            ),
            "buffer_effect_mean_25bp_net_relative_return": (
                buffer_retained["mean_monthly_net_relative_return_by_one_way_cost_bps"]["25"]
                - buffer_exact["mean_monthly_net_relative_return_by_one_way_cost_bps"]["25"]
            ),
            "buffer_effect_mean_recurring_turnover": (
                buffer_retained["mean_recurring_one_way_turnover"]
                - buffer_exact["mean_recurring_one_way_turnover"]
            ),
        }
    period_documents = []
    for item in sorted(periods, key=lambda row: (row.model_key, row.rule_key, row.formation_date)):
        document = asdict(item)
        document["formation_date"] = item.formation_date.isoformat()
        document["entry_date"] = item.entry_date.isoformat() if item.entry_date else None
        document["outcome_date"] = item.outcome_date.isoformat() if item.outcome_date else None
        document["included_in_all_path_common_diagnostic"] = item.formation_date in global_common_formations
        document["period_sha256"] = _canonical_hash(document)
        period_documents.append(document)
    report: dict[str, object] = {
        "attribution_key": ATTRIBUTION_KEY,
        "attribution_version": ATTRIBUTION_VERSION,
        "source_comparison_key": COMPARISON_KEY,
        "source_comparison_version": COMPARISON_VERSION,
        "source_comparison_report_sha256": comparison["report_hash"],
        "source_prediction_file_sha256": comparison["prediction_file_sha256"],
        "source_fits_file_sha256": comparison["fits_file_sha256"],
        "source_fold_sha256": comparison["fold_sha256"],
        "month_end_feature_source_sha256": feature_source_hash,
        "portfolio_size": PORTFOLIO_SIZE,
        "retention_rank": RETENTION_RANK,
        "cost_cases_one_way_bps": COST_CASES_BPS,
        "formation_rule": "final regular market session of each calendar month",
        "execution_rule": "enter next regular-session open; measure through 20 completed sessions",
        "portfolio_weighting": "equal weight after each formation",
        "turnover_rule": "one minus retained names divided by 20; initial cash deployment recorded as 1",
        "net_return_rule": "gross benchmark-relative return minus one-way turnover times one-way cost",
        "model_refit": False,
        "model_selection_performed": False,
        "holdout_used": False,
        "outer_results_used_for_tuning": False,
        "monthly_feature_eligible_counts": {
            formation.isoformat(): eligible_counts[formation] for formation in formations
        },
        "all_path_common_completed_formations_diagnostic": [
            item.isoformat() for item in sorted(global_common_formations)
        ],
        "all_path_common_formation_count_diagnostic": len(global_common_formations),
        "excluded_from_common_comparison": {
            f"{model}|{rule}": sorted(
                formation.isoformat() for formation in set(formations) - completed_by_path[model, rule]
            )
            for model in MODEL_KEYS for rule in RULE_KEYS
        },
        "summaries": summaries,
        "attribution": attribution,
        "periods": period_documents,
        "limitations": [
            "Tier-B current-survivors cohort is survivorship biased",
            "deployed reference uses current sectors as static non-point-in-time groupings",
            "outer development outcomes are attribution evidence and cannot tune or select a model",
            "portfolio results are private research, not an outperformance guarantee",
        ],
        "status": "ready_for_frozen_gate_evaluation",
    }
    report["report_sha256"] = _canonical_hash(report)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Attribute Phase 9C model and monthly portfolio effects")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--comparison-manifest", type=Path, default=Path("data/derived/phase_9c_nested_weekly_rank_predictions_v1.json"))
    parser.add_argument("--fits", type=Path, default=Path("data/derived/phase_9c_nested_weekly_rank_predictions_v1.fits.json"))
    parser.add_argument("--predictions", type=Path, default=Path("data/derived/phase_9c_nested_weekly_rank_predictions_v1.csv.gz"))
    parser.add_argument("--folds", type=Path, default=Path("data/derived/phase_9c_weekly_rank_development_v1.folds.json"))
    parser.add_argument("--output", type=Path, default=Path("data/derived/phase_9c_monthly_portfolio_attribution_v1.json"))
    arguments = parser.parse_args()
    database_url = _dotenv_values(arguments.env_file).get("DATABASE_URL")
    if not database_url:
        raise DataQualityError("DATABASE_URL is required")
    report = run_attribution(
        database_url=database_url, comparison_manifest_path=arguments.comparison_manifest,
        fits_path=arguments.fits, predictions_path=arguments.predictions,
        folds_path=arguments.folds, destination=arguments.output,
    )
    print(
        f"attribution={report['attribution_key']}@{report['attribution_version']}; "
        f"all_path_common_months={report['all_path_common_formation_count_diagnostic']}; "
        f"holdout_used={report['holdout_used']}"
    )


if __name__ == "__main__":
    main()
