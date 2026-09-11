"""Evaluate every frozen Phase 9D gate and issue the immutable readiness decision."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from dataclasses import asdict
from datetime import date
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
from statistics import fmean
from typing import Mapping, Sequence

from .clean_monthly_model_dataset import load_clean_examples
from .model_eligibility import evaluate_model_inputs
from .model_evaluation_repair import fit_reference, reference_training
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
from .phase_9c_gate_evaluation import (
    PredictionRow,
    _load_spy_bars,
    _monthly_values,
    _regime_diagnostics,
    _regimes,
    _weekly_values,
    consecutive_rank_stability,
    moving_block_bootstrap,
)
from .phase_9c_model_comparison import (
    _canonical_hash,
    _fit_document,
    _load_static_sectors_and_liquidity,
    _sha256_file,
)
from .phase_9c_portfolio_attribution import (
    COST_CASES_BPS,
    MonthlyScore,
    PortfolioPeriod,
    _load_month_end_labels,
    _period,
    select_portfolio,
    summarize_periods,
)
from .phase_9d_eligibility_audit import _load_registration, _rank_active_inputs
from .phase_9d_residual_dataset import (
    _centered_ranks,
    _fit_as_artifact,
    load_residual_dataset,
)
from .phase_9d_residual_training import MODEL_KEY, ResidualRidgeFit
from .quality import DataQualityError
from .score_run import _dotenv_values


EVALUATION_KEY = "phase_9d_anchored_residual_frozen_gate_evaluation"
EVALUATION_VERSION = "v1"
REFERENCE_MODEL = "chronological_fold_local_elastic_net_anchor"
CANDIDATE_MODEL = MODEL_KEY
RULES = ("exact_top20", "top20_entry_top30_retention")
BOOTSTRAP_SEED = 20260830
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_BLOCK_MONTHS = 3
PRIMARY_COST_BPS = 25
HOLDOUT_START = date(2025, 7, 1)
RAW_CORRECTION_FEATURES = (
    "return_on_assets_ttm",
    "operating_cash_flow_profitability_ttm",
    "accrual_quality_ttm",
    "asset_growth_yoy",
    "net_share_issuance_yoy",
)
DEFAULT_RUN = Path("data/derived/phase_9d-residual-training/20260910-v1")
DEFAULT_DATASET = Path("data/derived/phase_9d_anchored_residual_development_v1.csv.gz")
DEFAULT_FOLDS = Path("data/derived/phase_9c_weekly_rank_development_v1.folds.json")
DEFAULT_PANEL_REPORT = Path("data/derived/phase_9c_weekly_feature_panel_v1.json")
DEFAULT_AUDIT = Path("data/derived/phase_9d_exact_zero_eligibility_audit_v1.json")
DEFAULT_MONTHLY = Path("data/derived/training/tier_b_clean_monthly_model_development_v1.csv")
DEFAULT_REGISTRATION = Path("research/registrations/phase_9d_anchored_stability_v1.json")
DEFAULT_PROTOCOL = Path("PHASE_9D_STABILITY_PROTOCOL.md")
DEFAULT_AMENDMENT = Path("MODEL_EVALUATION_REPAIR_PROTOCOL.md")


def _validated_json(path: Path, hash_key: str) -> dict[str, object]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DataQualityError(f"invalid Phase 9D artifact: {path}") from error
    payload = dict(document)
    recorded = payload.pop(hash_key, None)
    if not isinstance(recorded, str) or _canonical_hash(payload) != recorded:
        raise DataQualityError(f"Phase 9D artifact hash is invalid: {path}")
    return document


def _load_folds(path: Path, expected_hash: str) -> dict[str, object]:
    folds = _validated_json(path, "fold_sha256")
    if (
        folds.get("fold_sha256") != expected_hash
        or folds.get("holdout_start") != HOLDOUT_START.isoformat()
        or folds.get("label_overlap_violations") != 0
        or len(folds.get("outer_folds", ())) != 4
    ):
        raise DataQualityError("Phase 9D evaluation received invalid frozen folds")
    return folds


def _load_training(run: Path) -> tuple[dict[str, object], dict[str, object], list[PredictionRow]]:
    report = _validated_json(run / "report.json", "report_sha256")
    fits = _validated_json(run / "fits.json", "fit_manifest_sha256")
    prediction_path = run / "outer-predictions.csv.gz"
    if (
        report.get("training_key") != CANDIDATE_MODEL
        or report.get("passed") is not True
        or report.get("holdout_used") is not False
        or report.get("outer_performance_evaluated") is not False
        or report.get("live_model_changed") is not False
        or report.get("fit_manifest_sha256") != fits.get("fit_manifest_sha256")
        or _sha256_file(prediction_path) != report.get("prediction_file_sha256")
    ):
        raise DataQualityError("Phase 9D training artifacts are unsafe for evaluation")
    fold_fits = {
        int(item["outer_fold"]): item
        for item in fits.get("outer_folds", ())
    }
    if set(fold_fits) != {1, 2, 3, 4}:
        raise DataQualityError("Phase 9D fit manifest does not contain four outer fits")
    rows: list[PredictionRow] = []
    hashes: list[str] = []
    seen: set[tuple[date, str]] = set()
    with gzip.open(prediction_path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "model_key", "outer_fold", "formation_date", "calendar_month", "security_id",
            "anchor_centered_rank", "predicted_residual", "candidate_raw_score",
            "label_centered_rank", "benchmark_relative_return", "selected_penalty",
            "fit_sha256", "source_dataset_row_sha256", "prediction_row_sha256",
        }
        if not reader.fieldnames or not required <= set(reader.fieldnames):
            raise DataQualityError("Phase 9D outer-prediction schema is invalid")
        for line, raw in enumerate(reader, start=2):
            recorded = raw.pop("prediction_row_sha256")
            if _canonical_hash(raw) != recorded:
                raise DataQualityError(f"invalid Phase 9D prediction hash at line {line}")
            formation = date.fromisoformat(raw["formation_date"])
            fold = int(raw["outer_fold"])
            identity = formation, raw["security_id"]
            numeric = tuple(float(raw[key]) for key in (
                "anchor_centered_rank", "predicted_residual", "candidate_raw_score",
                "label_centered_rank", "benchmark_relative_return", "selected_penalty",
            ))
            if (
                identity in seen
                or formation >= HOLDOUT_START
                or raw["model_key"] != CANDIDATE_MODEL
                or fold not in fold_fits
                or not all(math.isfinite(value) for value in numeric)
                or not math.isclose(numeric[0] + numeric[1], numeric[2], rel_tol=0.0, abs_tol=1e-14)
                or numeric[5] != float(fold_fits[fold]["selected_penalty"])
                or raw["fit_sha256"] != fold_fits[fold]["fit"]["fit_sha256"]
            ):
                raise DataQualityError(f"invalid or duplicate Phase 9D prediction at line {line}")
            seen.add(identity)
            hashes.append(recorded)
            rows.append(PredictionRow(
                CANDIDATE_MODEL, fold, formation, raw["calendar_month"], raw["security_id"],
                numeric[2], numeric[3], numeric[4], raw["source_dataset_row_sha256"],
            ))
            rows.append(PredictionRow(
                REFERENCE_MODEL, fold, formation, raw["calendar_month"], raw["security_id"],
                numeric[0], numeric[3], numeric[4], raw["source_dataset_row_sha256"],
            ))
    if (
        len(seen) != report.get("outer_prediction_rows")
        or not hashes
        or sha256("\n".join(hashes).encode()).hexdigest()
        != report.get("prediction_logical_sha256")
    ):
        raise DataQualityError("Phase 9D prediction count or logical hash is invalid")
    return report, fits, rows


def _residual_fit(document: Mapping[str, object]) -> ResidualRidgeFit:
    try:
        fit = ResidualRidgeFit(
            float(document["penalty"]),
            tuple(float(value) for value in document["feature_means"]),
            tuple(float(value) for value in document["feature_scales"]),
            tuple(float(value) for value in document["coefficients"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise DataQualityError("invalid Phase 9D residual fit") from error
    if not (len(fit.means) == len(fit.scales) == len(fit.coefficients) == 2):
        raise DataQualityError("Phase 9D residual fit has an unexpected width")
    return fit


def coefficient_stability(fits: Mapping[str, object], gates: Mapping[str, object]) -> dict[str, object]:
    names = ("investment_issuance", "profitability_quality")
    threshold = float(gates["minimum_coefficient_absolute_value"])
    required = int(gates["minimum_coefficient_positive_outer_fits"])
    values = {name: [] for name in names}
    for outer in fits["outer_folds"]:
        coefficients = outer["fit"]["coefficients"]
        if len(coefficients) != 2:
            raise DataQualityError("Phase 9D coefficient vector has an unexpected width")
        for name, raw in zip(names, coefficients, strict=True):
            values[name].append(float(raw))
    families = {}
    for name in names:
        qualifying = sum(value > 0 and abs(value) > threshold for value in values[name])
        families[name] = {
            "outer_coefficients": values[name],
            "positive_material_fit_count": qualifying,
            "required_fit_count": required,
            "passed": qualifying >= required,
        }
    return {"families": families, "passed": all(item["passed"] for item in families.values())}


def _month_end_inputs(
    database_url: str, *, start: date, end: date,
) -> tuple[
    tuple[str, ...], tuple[date, ...],
    dict[tuple[date, str], Mapping[str, float | None]],
    dict[tuple[date, str], tuple[float, float]], str,
]:
    security_ids, formations, prices, benchmark, actions = _load_context(
        database_url, start=start, end=end, formation_rule="month_end",
    )
    facts = _load_sec_facts(database_url, security_ids, formations)
    fact_positions = {security_id: 0 for security_id in security_ids}
    fact_state: dict[str, dict[str, object]] = {security_id: {} for security_id in security_ids}
    accounting_cache = {}
    accounting_catalog: dict[str, dict[str, object]] = {}
    active_raw: dict[tuple[date, str], list[float | None]] = {}
    correction: dict[tuple[date, str], tuple[float, float]] = {}
    formation_hashes = []
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
        formation_hashes.append(
            f"{formation.isoformat()}|{_formation_digest(security_ids, raw, ranked, families)}"
        )
        for security_id in security_ids:
            active_raw[formation, security_id] = [
                float(raw[security_id]["momentum_12_1"].value)
                if raw[security_id]["momentum_12_1"].value is not None else None,
                float(raw[security_id]["relative_strength_6m"].value)
                if raw[security_id]["relative_strength_6m"].value is not None else None,
                float(raw[security_id]["realized_volatility_60d"].value)
                if raw[security_id]["realized_volatility_60d"].value is not None else None,
                None, None, None,
            ]
            correction[formation, security_id] = (
                float(families[security_id]["investment_issuance"].value),
                float(families[security_id]["profitability_quality"].value),
            )
    sectors, active_values, active_source = _load_static_sectors_and_liquidity(
        database_url, security_ids=security_ids, formations=formations, conservative_asof=True,
    )
    ranked_inputs = _rank_active_inputs(
        raw=active_raw,
        by_formation={formation: security_ids for formation in formations},
        sectors=sectors,
        active_values=active_values,
    )
    source_hash = _canonical_hash({
        "formation_hashes": formation_hashes,
        "active_reference_source_sha256": active_source,
        "formation_rule": "final regular market session of each calendar month",
    })
    return security_ids, formations, ranked_inputs, correction, source_hash


def _fold_blocks(folds: Mapping[str, object]) -> dict[int, tuple[date, date]]:
    return {
        int(outer["outer_fold"]): (
            date.fromisoformat(outer["registered_block"][0]),
            date.fromisoformat(outer["registered_block"][1]),
        )
        for outer in folds["outer_folds"]
    }


def _fold_for(formation: date, blocks: Mapping[int, tuple[date, date]]) -> int:
    matches = [number for number, (start, end) in blocks.items() if start <= formation <= end]
    if len(matches) != 1:
        raise DataQualityError(f"month-end formation is outside one frozen outer block: {formation}")
    return matches[0]


def _month_end_scores(
    *, database_url: str, folds: Mapping[str, object], anchor_manifest: Mapping[str, object],
    fits: Mapping[str, object], monthly_dataset: Path,
) -> tuple[dict[tuple[str, date], list[MonthlyScore]], tuple[str, ...], tuple[date, ...], str]:
    blocks = _fold_blocks(folds)
    start = min(value[0] for value in blocks.values())
    end = max(value[1] for value in blocks.values())
    security_ids, formations, ranked_inputs, correction, source_hash = _month_end_inputs(
        database_url, start=start, end=end,
    )
    monthly, _ = load_clean_examples(monthly_dataset, monthly_dataset.with_suffix(".json"))
    episodes = {
        int(item["episode"].split("_")[1]): item
        for item in anchor_manifest["episodes"]
        if item.get("purpose") == "outer_validation_anchor"
    }
    outer_by_number = {int(item["outer_fold"]): item for item in folds["outer_folds"]}
    residual_by_number = {
        int(item["outer_fold"]): _residual_fit(item["fit"])
        for item in fits["outer_folds"]
    }
    anchor_fits = {}
    for number in range(1, 5):
        configuration = tuple(float(value) for value in episodes[number]["selected_configuration"])
        anchor_fit = fit_reference(reference_training(monthly, outer_by_number[number]), configuration)
        if _canonical_hash(_fit_document(anchor_fit)) != episodes[number]["fit_sha256"]:
            raise DataQualityError("month-end anchor refit differs from the authenticated weekly anchor")
        anchor_fits[number] = anchor_fit
    output: dict[tuple[str, date], list[MonthlyScore]] = defaultdict(list)
    for formation in formations:
        fold = _fold_for(formation, blocks)
        artifact = _fit_as_artifact(anchor_fits[fold])
        raw_predictions = {}
        for security_id in security_ids:
            evaluation = evaluate_model_inputs(
                artifact, ranked_inputs[formation, security_id],
                ignore_exact_zero_coefficients=True,
            )
            if evaluation.prediction is not None:
                raw_predictions[formation, security_id] = evaluation.prediction
        centered = _centered_ranks(raw_predictions)
        if len(centered) < 30:
            raise DataQualityError("month-end anchor has fewer than 30 eligible names")
        residual_fit = residual_by_number[fold]
        for (_, security_id), anchor_rank in sorted(centered.items()):
            output[REFERENCE_MODEL, formation].append(MonthlyScore(
                formation, security_id, REFERENCE_MODEL, anchor_rank,
            ))
            output[CANDIDATE_MODEL, formation].append(MonthlyScore(
                formation, security_id, CANDIDATE_MODEL,
                anchor_rank + residual_fit.predict(correction[formation, security_id]),
            ))
    return output, security_ids, formations, source_hash


def _build_periods(
    scores: Mapping[tuple[str, date], Sequence[MonthlyScore]], formations: Sequence[date],
    windows: Mapping[date, object], outcomes: Mapping[tuple[date, str], object],
    exclusions: Mapping[tuple[date, str], str],
) -> list[PortfolioPeriod]:
    periods = []
    for model in (REFERENCE_MODEL, CANDIDATE_MODEL):
        for rule in RULES:
            prior = None
            for formation in formations:
                ranked = sorted(scores[model, formation], key=lambda item: (-item.prediction, item.security_id))
                ranking_hash = _canonical_hash([
                    [item.security_id, format(item.prediction, ".17g")] for item in ranked
                ])
                selected = select_portfolio(
                    [item.security_id for item in ranked], rule_key=rule, prior=prior,
                )
                periods.append(_period(
                    model_key=model, rule_key=rule, formation=formation, selected=selected,
                    ranking_sha256=ranking_hash, prior=prior, windows=windows,
                    outcomes=outcomes, exclusions=exclusions,
                ))
                prior = selected
    return periods


def _portfolio_report(
    periods: Sequence[PortfolioPeriod], blocks: Mapping[int, tuple[date, date]],
) -> dict[str, object]:
    completed = {
        (model, rule): {
            item.formation_date for item in periods
            if item.model_key == model and item.rule_key == rule and item.unavailable_reason is None
        }
        for model in (REFERENCE_MODEL, CANDIDATE_MODEL) for rule in RULES
    }
    summaries = {
        model: {
            rule: summarize_periods(
                [item for item in periods if item.model_key == model and item.rule_key == rule],
                completed[model, rule],
            )
            for rule in RULES
        }
        for model in (REFERENCE_MODEL, CANDIDATE_MODEL)
    }
    index = {
        (item.model_key, item.rule_key, item.formation_date): item for item in periods
    }
    paired = sorted(completed[REFERENCE_MODEL, "exact_top20"] & completed[CANDIDATE_MODEL, "exact_top20"])
    if not paired:
        raise DataQualityError("Phase 9D has no paired completed exact-Top-20 periods")

    def net(item: PortfolioPeriod) -> float:
        assert item.gross_relative_return is not None
        return float(item.gross_relative_return) - item.one_way_turnover * PRIMARY_COST_BPS / 10_000

    candidate_net = {
        formation: net(index[CANDIDATE_MODEL, "exact_top20", formation])
        for formation in completed[CANDIDATE_MODEL, "exact_top20"]
    }
    deltas = [
        net(index[CANDIDATE_MODEL, "exact_top20", formation])
        - net(index[REFERENCE_MODEL, "exact_top20", formation])
        for formation in paired
    ]
    block_values: dict[int, list[float]] = defaultdict(list)
    for formation, value in candidate_net.items():
        block_values[_fold_for(formation, blocks)].append(value)
    block_means = {
        str(number): fmean(block_values[number]) if block_values[number] else None
        for number in range(1, 5)
    }
    candidate_all = sorted(
        (item.formation_date, item) for item in periods
        if item.model_key == CANDIDATE_MODEL and item.rule_key == "exact_top20"
    )
    reference_all = sorted(
        (item.formation_date, item) for item in periods
        if item.model_key == REFERENCE_MODEL and item.rule_key == "exact_top20"
    )
    candidate_turnover = fmean(item.one_way_turnover for _, item in candidate_all[1:])
    reference_turnover = fmean(item.one_way_turnover for _, item in reference_all[1:])
    period_documents = []
    for item in sorted(periods, key=lambda row: (row.model_key, row.rule_key, row.formation_date)):
        document = asdict(item)
        document["formation_date"] = item.formation_date.isoformat()
        document["entry_date"] = item.entry_date.isoformat() if item.entry_date else None
        document["outcome_date"] = item.outcome_date.isoformat() if item.outcome_date else None
        document["period_sha256"] = _canonical_hash(document)
        period_documents.append(document)
    return {
        "formation_rule": "final regular market session of each calendar month",
        "primary_rule": "exact_top20",
        "secondary_diagnostic_rule": "top20_entry_top30_retention",
        "portfolio_size": 20,
        "weighting": "equal weight",
        "execution_rule": "next regular-session open through 20 completed sessions",
        "cost_cases_one_way_bps": COST_CASES_BPS,
        "primary_cost_one_way_bps": PRIMARY_COST_BPS,
        "summaries": summaries,
        "paired_completed_formations": [item.isoformat() for item in paired],
        "paired_completed_formation_count": len(paired),
        "candidate_mean_25bp_net_relative_return": fmean(candidate_net.values()),
        "paired_mean_25bp_net_relative_return_delta": fmean(deltas),
        "outer_block_mean_25bp_net_relative_return": block_means,
        "positive_outer_blocks": sum(value is not None and value > 0 for value in block_means.values()),
        "mean_recurring_one_way_turnover": candidate_turnover,
        "reference_mean_recurring_one_way_turnover": reference_turnover,
        "turnover_delta": candidate_turnover - reference_turnover,
        "periods": period_documents,
    }


def evaluate(
    *, database_url: str, training_run: Path, dataset: Path, folds_path: Path,
    panel_report_path: Path, audit_path: Path, monthly_dataset: Path,
    registration_path: Path, protocol_path: Path, amendment_path: Path,
    destination: Path,
) -> dict[str, object]:
    if destination.exists():
        raise DataQualityError("refusing to overwrite immutable Phase 9D evaluation")
    print("[phase-9d-evaluation] 1/6 Authenticating frozen artifacts and predictions", flush=True)
    training, fits, predictions = _load_training(training_run)
    _, dataset_report = load_residual_dataset(dataset)
    folds = _load_folds(folds_path, str(dataset_report["provenance"]["fold_sha256"]))
    panel = _validated_json(panel_report_path, "report_hash")
    audit = _validated_json(audit_path, "audit_sha256")
    registration = _load_registration(registration_path)
    if (
        dataset_report.get("passed") is not True
        or dataset_report.get("holdout_used") is not False
        or audit.get("passed") is not True
        or registration.get("protocol_key") != "tier_b_anchored_accounting_residual_rank_v1"
        or _sha256_file(protocol_path) != registration.get("protocol_document_canonical_sha256")
        or _sha256_file(amendment_path) != dataset_report["provenance"].get("amended_protocol_sha256")
        or training["provenance"].get("dataset_report_sha256") != dataset_report.get("report_sha256")
        or dataset_report["provenance"].get("p9d1_audit_sha256") != audit.get("audit_sha256")
        or dataset_report["provenance"].get("source_feature_panel_report_sha256") != panel.get("report_hash")
    ):
        raise DataQualityError("Phase 9D frozen source contract is invalid")

    print("[phase-9d-evaluation] 2/6 Calculating paired ranking and stability evidence", flush=True)
    candidate = [row for row in predictions if row.model_key == CANDIDATE_MODEL]
    reference = [row for row in predictions if row.model_key == REFERENCE_MODEL]
    candidate_ic = _weekly_values(candidate, metric="ic")
    reference_ic = _weekly_values(reference, metric="ic")
    candidate_monthly = _monthly_values(candidate_ic)
    reference_monthly = _monthly_values(reference_ic)
    common_months = sorted(set(candidate_monthly) & set(reference_monthly))
    if len(common_months) < 12:
        raise DataQualityError("Phase 9D evaluation has too few paired calendar months")
    deltas = [candidate_monthly[month] - reference_monthly[month] for month in common_months]
    fold_by_date = {row.formation_date: row.outer_fold for row in candidate}
    outer_values: dict[int, list[float]] = defaultdict(list)
    for formation, value in candidate_ic.items():
        outer_values[fold_by_date[formation]].append(value)
    outer_means = {str(number): fmean(outer_values[number]) for number in range(1, 5)}
    candidate_spread = _weekly_values(candidate, metric="spread")
    spread_monthly = _monthly_values(candidate_spread)
    bootstrap = moving_block_bootstrap(
        deltas, seed=BOOTSTRAP_SEED, resamples=BOOTSTRAP_RESAMPLES,
        block_length=BOOTSTRAP_BLOCK_MONTHS,
    )
    stability = consecutive_rank_stability(candidate)
    coefficient_diagnostic = coefficient_stability(fits, registration["frozen_gates"])

    print("[phase-9d-evaluation] 3/6 Reconstructing identical true-month-end portfolios", flush=True)
    anchors_path = dataset.with_name(dataset.name.replace(".csv.gz", ".anchors.json"))
    anchors = _validated_json(anchors_path, "anchor_manifest_sha256")
    if anchors["anchor_manifest_sha256"] != dataset_report["provenance"].get("anchor_manifest_sha256"):
        raise DataQualityError("Phase 9D anchor manifest differs from dataset provenance")
    scores, security_ids, formations, month_end_source_hash = _month_end_scores(
        database_url=database_url, folds=folds, anchor_manifest=anchors,
        fits=fits, monthly_dataset=monthly_dataset,
    )
    windows, outcomes, exclusions = _load_month_end_labels(database_url, security_ids, formations)
    periods = _build_periods(scores, formations, windows, outcomes, exclusions)
    portfolio = _portfolio_report(periods, _fold_blocks(folds))

    print("[phase-9d-evaluation] 4/6 Building point-in-time regime diagnostics", flush=True)
    regime_map, regime_lineage = _regimes(
        list(candidate_ic), _load_spy_bars(database_url, max(candidate_ic)),
    )
    regimes = _regime_diagnostics(candidate_ic, candidate_spread, regime_map)

    print("[phase-9d-evaluation] 5/6 Applying all ten preregistered gates", flush=True)
    gates = registration["frozen_gates"]
    raw_coverage = panel["raw_aggregate_coverage"]
    coverage = {
        "lineage_complete": dataset_report["gates"]["all_rows_have_complete_lineage"] is True,
        "aggregate_score_coverage": audit["metrics"]["corrected_coverage"],
        "minimum_weekly_score_coverage": audit["metrics"]["minimum_corrected_formation_coverage"],
        "correction_family_aggregate_coverage": dataset_report["aggregate_informative_coverage"],
        "correction_family_minimum_formation_coverage": dataset_report["minimum_formation_informative_coverage"],
        "modeled_raw_feature_aggregate_coverage": {
            key: raw_coverage[key] for key in RAW_CORRECTION_FEATURES
        },
    }
    integrity_checks = {
        "dataset_integrity": all(dataset_report["gates"].values()),
        "training_integrity": all(training["gates"].values()),
        "fold_label_overlap_zero": folds["label_overlap_violations"] == 0,
        "training_outcome_overlap_zero": training["training_outcome_overlap_violations"] == 0,
        "holdout_unused": all(item is False for item in (
            dataset_report["holdout_used"], training["holdout_used"],
        )),
        "source_artifacts_authenticated": True,
        "deterministic_artifact_contract": (
            panel["gates"]["deterministic_replay"] is True
            and bool(training["prediction_logical_sha256"])
            and bool(dataset_report["dataset_logical_sha256"])
        ),
    }
    gate_checks = {
        "1_integrity": all(integrity_checks.values()),
        "2_coverage": (
            coverage["lineage_complete"]
            and coverage["aggregate_score_coverage"] >= float(gates["minimum_aggregate_score_coverage"])
            and coverage["minimum_weekly_score_coverage"] >= float(gates["minimum_weekly_score_coverage"])
            and all(value >= float(gates["minimum_correction_family_aggregate_coverage"])
                    for value in coverage["correction_family_aggregate_coverage"].values())
            and all(value >= float(gates["minimum_correction_family_formation_coverage"])
                    for value in coverage["correction_family_minimum_formation_coverage"].values())
            and all(value >= float(gates["minimum_raw_feature_aggregate_coverage"])
                    for value in coverage["modeled_raw_feature_aggregate_coverage"].values())
        ),
        "3_mean_ic_and_delta": (
            fmean(candidate_monthly.values()) >= float(gates["minimum_mean_monthly_rank_ic"])
            and fmean(deltas) >= float(gates["minimum_mean_monthly_rank_ic_delta"])
        ),
        "4_outer_block_ic": (
            sum(value > 0 for value in outer_means.values()) >= int(gates["minimum_positive_outer_blocks"])
            and min(outer_means.values()) > float(gates["minimum_worst_outer_block_ic_exclusive"])
        ),
        "5_paired_bootstrap": (
            bootstrap["probability_effect_positive"] >= float(gates["minimum_bootstrap_probability_positive"])
        ),
        "6_top_minus_bottom": fmean(spread_monthly.values()) > 0,
        "7_net_portfolio": (
            portfolio["candidate_mean_25bp_net_relative_return"] > float(gates["minimum_25bp_net_relative_return"])
            and portfolio["paired_mean_25bp_net_relative_return_delta"] >= float(gates["minimum_25bp_net_relative_return_delta"])
            and portfolio["positive_outer_blocks"] >= int(gates["minimum_positive_outer_blocks"])
        ),
        "8_turnover": (
            portfolio["mean_recurring_one_way_turnover"] <= float(gates["maximum_absolute_one_way_turnover"])
            and portfolio["turnover_delta"] <= float(gates["maximum_turnover_above_reference"])
        ),
        "9_rank_stability": (
            stability["mean_spearman"] >= float(gates["minimum_consecutive_rank_stability"])
        ),
        "10_coefficient_signs": coefficient_diagnostic["passed"],
    }
    decision = "freeze_for_forward_shadow" if all(gate_checks.values()) else "no-freeze"

    print("[phase-9d-evaluation] 6/6 Writing immutable evidence and decision", flush=True)
    report: dict[str, object] = {
        "evaluation_key": EVALUATION_KEY,
        "evaluation_version": EVALUATION_VERSION,
        "protocol_key": registration["protocol_key"],
        "protocol_sha256": _sha256_file(protocol_path),
        "amended_protocol_sha256": _sha256_file(amendment_path),
        "registration_sha256": registration["registration_sha256"],
        "frozen_gates": gates,
        "paired_security_rows": len(candidate),
        "paired_formation_count": len(candidate_ic),
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
        "rank_stability": stability,
        "coefficient_stability": coefficient_diagnostic,
        "coverage": coverage,
        "integrity_checks": integrity_checks,
        "portfolio": portfolio,
        "regime_diagnostics": regimes,
        "spy_regime_lineage_sha256": regime_lineage,
        "month_end_feature_source_sha256": month_end_source_hash,
        "gate_checks": gate_checks,
        "failed_gates": [key for key, passed in gate_checks.items() if not passed],
        "decision": decision,
        "outer_results_used_for_tuning": False,
        "thresholds_changed_after_results": False,
        "holdout_used": False,
        "live_model_changed": False,
        "independent_confirmation": False,
        "source_hashes": {
            "training_report_sha256": training["report_sha256"],
            "prediction_file_sha256": training["prediction_file_sha256"],
            "fit_manifest_sha256": fits["fit_manifest_sha256"],
            "residual_dataset_sha256": dataset_report["dataset_file_sha256"],
            "residual_dataset_report_sha256": dataset_report["report_sha256"],
            "anchor_manifest_sha256": anchors["anchor_manifest_sha256"],
            "fold_sha256": folds["fold_sha256"],
            "fold_file_sha256": _sha256_file(folds_path),
            "panel_report_sha256": panel["report_hash"],
            "eligibility_audit_sha256": audit["audit_sha256"],
            "monthly_dataset_sha256": _sha256_file(monthly_dataset),
            "monthly_dataset_manifest_sha256": _sha256_file(monthly_dataset.with_suffix(".json")),
            "registration_file_sha256": _sha256_file(registration_path),
            "evaluation_code_sha256": _sha256_file(Path(__file__)),
        },
        "limitations": [
            "Tier-B current-survivors research is survivorship biased",
            "current sectors are static rather than historical point-in-time classifications",
            "reused development evidence cannot independently confirm or promote a model",
            "the consumed July 2025 through June 2026 holdout was not used",
            "private research does not guarantee future SPY outperformance",
        ],
        "status": "immutable_readiness_decision",
    }
    report["report_sha256"] = _canonical_hash(report)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8",
    )
    print(
        f"[phase-9d-evaluation] Complete: decision={decision}; "
        f"failed_gates={report['failed_gates']}; report_sha256={report['report_sha256']}",
        flush=True,
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--training-run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--folds", type=Path, default=DEFAULT_FOLDS)
    parser.add_argument("--panel-report", type=Path, default=DEFAULT_PANEL_REPORT)
    parser.add_argument("--eligibility-audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--monthly-dataset", type=Path, default=DEFAULT_MONTHLY)
    parser.add_argument("--registration", type=Path, default=DEFAULT_REGISTRATION)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--amendment", type=Path, default=DEFAULT_AMENDMENT)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    values = dict(__import__("os").environ)
    values.update(_dotenv_values(arguments.env_file))
    database_url = values.get("DATABASE_URL")
    if not database_url:
        raise DataQualityError("DATABASE_URL is required for Phase 9D portfolio and regime evidence")
    evaluate(
        database_url=database_url, training_run=arguments.training_run,
        dataset=arguments.dataset, folds_path=arguments.folds,
        panel_report_path=arguments.panel_report, audit_path=arguments.eligibility_audit,
        monthly_dataset=arguments.monthly_dataset,
        registration_path=arguments.registration, protocol_path=arguments.protocol,
        amendment_path=arguments.amendment,
        destination=arguments.output,
    )


if __name__ == "__main__":
    main()
