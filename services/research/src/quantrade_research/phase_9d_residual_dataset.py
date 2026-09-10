"""Materialize the authenticated Phase 9D cross-fitted residual dataset."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from datetime import date
import gzip
from hashlib import sha256
import io
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

from .active_model import ActiveModelArtifact
from .clean_monthly_model_dataset import load_clean_examples
from .model_eligibility import evaluate_model_inputs
from .model_evaluation_repair import (
    ELASTIC_GRID,
    HOLDOUT,
    fit_reference,
    reference_training,
    select_configuration,
    validate_rows,
)
from .monthly_model_comparison import Example as MonthlyExample
from .phase_9c_model_comparison import (
    ACTIVE_MODEL_COLUMNS,
    Example,
    LinearFit,
    Prediction,
    _canonical_hash,
    _fit_document,
    _load_active_raw_panel,
    _load_static_sectors_and_liquidity,
    _read_dataset,
    _sha256_file,
    _tie_percentiles,
    _validate_inputs,
    monthly_rank_ic,
)
from .phase_9d_eligibility_audit import (
    AUDIT_KEY,
    AUDIT_VERSION,
    _load_registration,
    _panel_index,
    _rank_active_inputs,
)
from .quality import DataQualityError
from .score_run import _dotenv_values


DATASET_KEY = "phase_9d_anchored_residual_development"
DATASET_VERSION = "v1"
PROTOCOL = Path("MODEL_EVALUATION_REPAIR_PROTOCOL.md")
REGISTRATION = Path("research/registrations/phase_9d_anchored_stability_v1.json")
CORRECTION_COLUMNS = ("investment_issuance_value", "profitability_quality_value")
EARLIEST_TUNING_EPISODE = "outer_1_inner_1"


@dataclass(frozen=True, slots=True)
class AnchorRow:
    formation_date: date
    security_id: str
    raw_prediction: float
    centered_rank: float
    episode: str
    configuration: tuple[float, float]
    fit_sha256: str


@dataclass(frozen=True, slots=True)
class ResidualExample:
    formation_date: date
    calendar_month: str
    security_id: str
    outer_validation_fold: int | None
    anchor_centered_rank: float
    label_centered_rank: float
    residual_target: float
    correction_features: tuple[float, float]
    sample_weight: float
    benchmark_relative_return: float
    outcome_date: date
    dataset_row_sha256: str


def _write_json(path: Path, document: object) -> None:
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _fit_as_artifact(fit: LinearFit) -> ActiveModelArtifact:
    return ActiveModelArtifact(
        "phase_9d_fold_local_anchor",
        "model_evaluation_repair_v1",
        "phase_9d_internal",
        ACTIVE_MODEL_COLUMNS,
        fit.means,
        fit.scales,
        fit.target_mean,
        fit.coefficients,
    )


def _predict_full_universe(
    *,
    fit: LinearFit,
    formations: Sequence[date],
    by_formation: Mapping[date, Sequence[str]],
    ranked_inputs: Mapping[tuple[date, str], Mapping[str, float | None]],
) -> dict[tuple[date, str], float]:
    artifact = _fit_as_artifact(fit)
    result: dict[tuple[date, str], float] = {}
    for formation in formations:
        for security_id in by_formation[formation]:
            evaluation = evaluate_model_inputs(
                artifact,
                ranked_inputs[formation, security_id],
                ignore_exact_zero_coefficients=True,
            )
            if evaluation.prediction is not None:
                result[formation, security_id] = evaluation.prediction
    return result


def _centered_ranks(
    predictions: Mapping[tuple[date, str], float],
) -> dict[tuple[date, str], float]:
    grouped: dict[date, list[tuple[str, float]]] = defaultdict(list)
    for (formation, security_id), value in predictions.items():
        grouped[formation].append((security_id, value))
    result: dict[tuple[date, str], float] = {}
    for formation, values in grouped.items():
        ranks = _tie_percentiles(values, 1)
        result.update(
            ((formation, security_id), 2.0 * percentile - 1.0)
            for security_id, percentile in ranks.items()
        )
    return result


def _paired_configuration_scores(
    *,
    configurations: Sequence[tuple[float, float]],
    predictions: Mapping[tuple[float, float], Mapping[tuple[date, str], float]],
    validation_rows: Sequence[Example],
    fold_label: str,
) -> list[dict[str, object]]:
    if not validation_rows:
        raise DataQualityError(f"{fold_label} has no label rows")
    common = {
        (row.formation_date, row.security_id)
        for row in validation_rows
        if all((row.formation_date, row.security_id) in predictions[configuration] for configuration in configurations)
    }
    if not common:
        raise DataQualityError(f"{fold_label} has no common eligible anchor rows")
    records: list[dict[str, object]] = []
    for configuration in configurations:
        scored = [
            Prediction(
                "fold_local_anchor", 0, row,
                predictions[configuration][row.formation_date, row.security_id],
            )
            for row in validation_rows
            if (row.formation_date, row.security_id) in common
        ]
        score, monthly = monthly_rank_ic(scored)
        records.append({
            "configuration": configuration,
            "mean_monthly_rank_ic": score,
            "monthly_rank_ic": monthly,
            "paired_row_count": len(scored),
        })
    return records


def _evaluate_split(
    *,
    split: Mapping[str, object],
    monthly: Sequence[MonthlyExample],
    label_index: Mapping[date, Sequence[Example]],
    by_formation: Mapping[date, Sequence[str]],
    ranked_inputs: Mapping[tuple[date, str], Mapping[str, float | None]],
    label: str,
    score_diagnostics: bool = True,
) -> tuple[dict[tuple[float, float], dict[tuple[date, str], float]], list[dict[str, object]], dict[tuple[float, float], LinearFit]]:
    formations = tuple(date.fromisoformat(value) for value in split["validation_formations"])
    validation_rows = [row for formation in formations for row in label_index.get(formation, ())]
    fits: dict[tuple[float, float], LinearFit] = {}
    predictions: dict[tuple[float, float], dict[tuple[date, str], float]] = {}
    training = reference_training(monthly, split)
    for configuration in ELASTIC_GRID:
        fit = fit_reference(training, configuration)
        fits[configuration] = fit
        predictions[configuration] = _predict_full_universe(
            fit=fit, formations=formations, by_formation=by_formation,
            ranked_inputs=ranked_inputs,
        )
    records = (
        _paired_configuration_scores(
            configurations=ELASTIC_GRID, predictions=predictions,
            validation_rows=validation_rows, fold_label=label,
        )
        if score_diagnostics else []
    )
    return predictions, records, fits


def _predict_selected_split(
    *,
    split: Mapping[str, object],
    selected: tuple[float, float],
    monthly: Sequence[MonthlyExample],
    by_formation: Mapping[date, Sequence[str]],
    ranked_inputs: Mapping[tuple[date, str], Mapping[str, float | None]],
) -> tuple[dict[tuple[date, str], float], LinearFit]:
    """Fit one earlier-selected anchor without reading validation outcomes."""
    fit = fit_reference(reference_training(monthly, split), selected)
    formations = tuple(date.fromisoformat(value) for value in split["validation_formations"])
    predictions = _predict_full_universe(
        fit=fit, formations=formations, by_formation=by_formation,
        ranked_inputs=ranked_inputs,
    )
    return predictions, fit


def _select_from_records(records: Sequence[Mapping[str, object]]) -> tuple[float, float]:
    selected = select_configuration(records)
    if not isinstance(selected, tuple) or len(selected) != 2:
        raise DataQualityError("anchor configuration selection is invalid")
    return float(selected[0]), float(selected[1])


def _aggregate_tuning_records(
    episodes: Sequence[tuple[Mapping[tuple[float, float], Mapping[tuple[date, str], float]], Sequence[Example]]],
    *,
    outcome_dates: Mapping[tuple[date, str], date],
    available_before: date,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for configuration in ELASTIC_GRID:
        predictions: list[Prediction] = []
        for episode_predictions, rows in episodes:
            available_rows = [
                row for row in rows
                if outcome_dates[row.formation_date, row.security_id] < available_before
            ]
            current = episode_predictions[configuration]
            common = {
                (row.formation_date, row.security_id)
                for row in available_rows
                if all(
                    (row.formation_date, row.security_id) in episode_predictions[candidate]
                    for candidate in ELASTIC_GRID
                )
            }
            predictions.extend(
                Prediction("fold_local_anchor", 0, row, current[row.formation_date, row.security_id])
                for row in available_rows if (row.formation_date, row.security_id) in common
            )
        if not predictions:
            raise DataQualityError("no earlier anchor tuning predictions are available")
        score, monthly = monthly_rank_ic(predictions)
        records.append({
            "configuration": configuration,
            "mean_monthly_rank_ic": score,
            "monthly_rank_ic": monthly,
            "paired_row_count": len(predictions),
            "selection_information_cutoff_exclusive": available_before.isoformat(),
            "latest_outcome_used": max(
                outcome_dates[row.example.formation_date, row.example.security_id]
                for row in predictions
            ).isoformat(),
        })
    return records


def _anchor_rows(
    *,
    selected: tuple[float, float],
    predictions: Mapping[tuple[float, float], Mapping[tuple[date, str], float]],
    fit: LinearFit,
    episode: str,
) -> dict[tuple[date, str], AnchorRow]:
    raw = predictions[selected]
    centered = _centered_ranks(raw)
    fit_sha256 = _canonical_hash(_fit_document(fit))
    return {
        key: AnchorRow(key[0], key[1], value, centered[key], episode, selected, fit_sha256)
        for key, value in raw.items()
    }


def build_cross_fitted_anchors(
    *,
    folds: Mapping[str, object],
    monthly: Sequence[MonthlyExample],
    examples: Sequence[Example],
    by_formation: Mapping[date, Sequence[str]],
    ranked_inputs: Mapping[tuple[date, str], Mapping[str, float | None]],
    outcome_dates: Mapping[tuple[date, str], date],
) -> tuple[dict[tuple[date, str], AnchorRow], list[dict[str, object]]]:
    label_index: dict[date, list[Example]] = defaultdict(list)
    for row in examples:
        label_index[row.formation_date].append(row)
    outer_folds = folds["outer_folds"]
    first_inner = outer_folds[0]["inner_folds"]
    anchors: dict[tuple[date, str], AnchorRow] = {}
    records: list[dict[str, object]] = []
    earlier_episodes: list[
        tuple[Mapping[tuple[float, float], Mapping[tuple[date, str], float]], Sequence[Example]]
    ] = []

    for position, inner in enumerate(first_inner):
        episode = f"outer_1_inner_{inner['inner_fold']}"
        predictions, diagnostic, fits = _evaluate_split(
            split=inner, monthly=monthly, label_index=label_index,
            by_formation=by_formation, ranked_inputs=ranked_inputs, label=episode,
            score_diagnostics=position == 0,
        )
        validation_rows = [
            row for value in inner["validation_formations"]
            for row in label_index.get(date.fromisoformat(value), ())
        ]
        if position == 0:
            records.append({
                "episode": episode,
                "purpose": "earliest_tuning_only_excluded_from_residual_targets",
                "selected_configuration": None,
                "configuration_diagnostics": diagnostic,
            })
        else:
            validation_start = min(date.fromisoformat(value) for value in inner["validation_formations"])
            tuning = _aggregate_tuning_records(
                earlier_episodes, outcome_dates=outcome_dates,
                available_before=validation_start,
            )
            selected = _select_from_records(tuning)
            current = _anchor_rows(
                selected=selected, predictions=predictions, fit=fits[selected], episode=episode,
            )
            overlap = set(anchors) & set(current)
            if overlap:
                raise DataQualityError("cross-fitted anchor episodes overlap")
            anchors.update(current)
            records.append({
                "episode": episode,
                "purpose": "chronological_cross_fitted_training_anchor",
                "selected_configuration": selected,
                "selection_used_episodes": [record["episode"] for record in records],
                "configuration_diagnostics": tuning,
                "fit_sha256": _canonical_hash(_fit_document(fits[selected])),
                "eligible_anchor_rows": len(current),
            })
        earlier_episodes.append((predictions, validation_rows))

    for outer in outer_folds:
        episode = f"outer_{outer['outer_fold']}_validation"
        inner_episodes = []
        for inner in outer["inner_folds"]:
            predictions, _, _ = _evaluate_split(
                split=inner, monthly=monthly, label_index=label_index,
                by_formation=by_formation, ranked_inputs=ranked_inputs,
                label=f"outer_{outer['outer_fold']}_inner_{inner['inner_fold']}",
                score_diagnostics=False,
            )
            validation_rows = [
                row for value in inner["validation_formations"]
                for row in label_index.get(date.fromisoformat(value), ())
            ]
            inner_episodes.append((predictions, validation_rows))
        validation_start = min(date.fromisoformat(value) for value in outer["validation_formations"])
        tuning = _aggregate_tuning_records(
            inner_episodes, outcome_dates=outcome_dates,
            available_before=validation_start,
        )
        selected = _select_from_records(tuning)
        selected_predictions, selected_fit = _predict_selected_split(
            split=outer, selected=selected, monthly=monthly,
            by_formation=by_formation, ranked_inputs=ranked_inputs,
        )
        current = _anchor_rows(
            selected=selected, predictions={selected: selected_predictions},
            fit=selected_fit, episode=episode,
        )
        overlap = set(anchors) & set(current)
        if overlap:
            raise DataQualityError("outer anchor episodes overlap earlier anchors")
        anchors.update(current)
        records.append({
            "episode": episode,
            "purpose": "outer_validation_anchor",
            "selected_configuration": selected,
            "selection_rule": "all three registered inner folds; equal-month rank IC; stronger within 0.002",
            "configuration_diagnostics": tuning,
            "fit_sha256": _canonical_hash(_fit_document(selected_fit)),
            "eligible_anchor_rows": len(current),
            "training_end": max(outer["training_formations"]),
            "validation_start": min(outer["validation_formations"]),
            "validation_end": max(outer["validation_formations"]),
        })
    return anchors, records


def _load_audit(path: Path) -> dict[str, object]:
    try:
        audit = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DataQualityError("P9D.1 eligibility audit is required") from error
    payload = dict(audit)
    recorded = payload.pop("audit_sha256", None)
    if audit.get("audit_key") != AUDIT_KEY or audit.get("audit_version") != AUDIT_VERSION:
        raise DataQualityError("unexpected P9D.1 eligibility audit")
    if _canonical_hash(payload) != recorded or audit.get("passed") is not True:
        raise DataQualityError("P9D.1 eligibility audit is unauthenticated or failed")
    if audit["decision_time_consistency"].get("live_rollout_performed") is not False:
        raise DataQualityError("P9D.1 audit unexpectedly changed live eligibility")
    return audit


def _source_lineage_paths(dataset: Path, panel: Path) -> tuple[Path, Path]:
    dataset_base = dataset.with_suffix("") if dataset.suffix == ".gz" else dataset
    panel_base = panel.with_suffix("") if panel.suffix == ".gz" else panel
    return dataset_base.with_suffix(".label_lineage.tsv.gz"), panel_base.with_suffix(".lineage.tsv.gz")


def _outer_validation_fold(folds: Mapping[str, object], formation: date) -> int | None:
    for outer in folds["outer_folds"]:
        if formation.isoformat() in outer["validation_formations"]:
            return int(outer["outer_fold"])
    return None


def _row_digest(row: Mapping[str, object]) -> str:
    return _canonical_hash(dict(row))


def load_residual_dataset(
    dataset: Path, manifest_path: Path | None = None,
) -> tuple[tuple[ResidualExample, ...], dict[str, object]]:
    """Authenticate and load the model-ready Phase 9D artifact."""
    manifest_path = manifest_path or dataset.with_suffix("").with_suffix(".json")
    anchors_path = dataset.with_name(dataset.name.replace(".csv.gz", ".anchors.json"))
    try:
        report = json.loads(manifest_path.read_text(encoding="utf-8"))
        anchors = json.loads(anchors_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid Phase 9D residual dataset manifests") from error
    report_payload = dict(report)
    recorded_report = report_payload.pop("report_sha256", None)
    anchor_payload = dict(anchors)
    recorded_anchor = anchor_payload.pop("anchor_manifest_sha256", None)
    if report.get("dataset_key") != DATASET_KEY or report.get("dataset_version") != DATASET_VERSION:
        raise DataQualityError("unexpected Phase 9D residual dataset")
    if report.get("passed") is not True or report.get("holdout_used") is not False:
        raise DataQualityError("Phase 9D residual dataset is not approved development data")
    if _canonical_hash(report_payload) != recorded_report:
        raise DataQualityError("Phase 9D residual dataset report hash is invalid")
    if _canonical_hash(anchor_payload) != recorded_anchor:
        raise DataQualityError("Phase 9D anchor manifest hash is invalid")
    if report["provenance"].get("anchor_manifest_sha256") != recorded_anchor:
        raise DataQualityError("Phase 9D anchor manifest differs from dataset provenance")
    if _sha256_file(dataset) != report.get("dataset_file_sha256"):
        raise DataQualityError("Phase 9D residual dataset file hash is invalid")

    required = {
        "partition", "formation_date", "calendar_month", "security_id",
        "outcome_date", "outer_validation_fold", "anchor_centered_rank",
        "label_centered_rank", "residual_target", *CORRECTION_COLUMNS,
        "residual_sample_weight", "benchmark_relative_return",
        "source_panel_row_sha256", "label_sha256", "source_dataset_row_sha256",
        "anchor_fit_sha256", "anchor_lineage_sha256", "dataset_row_sha256",
    }
    examples: list[ResidualExample] = []
    seen: set[tuple[date, str]] = set()
    month_weights: dict[str, float] = defaultdict(float)
    row_hashes: list[str] = []
    with gzip.open(dataset, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not required <= set(reader.fieldnames):
            raise DataQualityError("Phase 9D residual dataset has an unexpected schema")
        for line, row in enumerate(reader, start=2):
            recorded_row = row.pop("dataset_row_sha256")
            if _row_digest(row) != recorded_row:
                raise DataQualityError(f"Phase 9D residual row hash is invalid at line {line}")
            try:
                formation = date.fromisoformat(row["formation_date"])
                outcome = date.fromisoformat(row["outcome_date"])
                fold = int(row["outer_validation_fold"]) if row["outer_validation_fold"] else None
                anchor = float(row["anchor_centered_rank"])
                target = float(row["label_centered_rank"])
                residual = float(row["residual_target"])
                features = tuple(float(row[column]) for column in CORRECTION_COLUMNS)
                weight = float(row["residual_sample_weight"])
                relative_return = float(row["benchmark_relative_return"])
            except (TypeError, ValueError) as error:
                raise DataQualityError(f"invalid Phase 9D residual row at line {line}") from error
            numeric = (anchor, target, residual, *features, weight, relative_return)
            identity = formation, row["security_id"]
            if row["partition"] != "development" or formation >= HOLDOUT or outcome >= HOLDOUT:
                raise DataQualityError(f"holdout or partition violation at line {line}")
            if identity in seen or not all(math.isfinite(value) for value in numeric) or weight <= 0:
                raise DataQualityError(f"duplicate or invalid Phase 9D residual row at line {line}")
            if not math.isclose(residual, target - anchor, rel_tol=0.0, abs_tol=1e-15):
                raise DataQualityError(f"residual target does not reconcile at line {line}")
            if fold is not None and fold not in range(1, 5):
                raise DataQualityError(f"invalid outer fold at line {line}")
            seen.add(identity)
            month_weights[row["calendar_month"]] += weight
            row_hashes.append(recorded_row)
            examples.append(ResidualExample(
                formation, row["calendar_month"], row["security_id"], fold,
                anchor, target, residual, (features[0], features[1]), weight,
                relative_return, outcome, recorded_row,
            ))
    if len(examples) != report.get("row_count"):
        raise DataQualityError("Phase 9D residual row count differs from its report")
    if any(not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-12) for total in month_weights.values()):
        raise DataQualityError("Phase 9D residual month weights do not sum to one")
    if sha256("\n".join(row_hashes).encode()).hexdigest() != report.get("dataset_logical_sha256"):
        raise DataQualityError("Phase 9D logical dataset hash is invalid")
    return tuple(examples), report


def materialize_dataset(
    *,
    database_url: str,
    source_dataset: Path,
    feature_panel: Path,
    monthly_dataset: Path,
    eligibility_audit: Path,
    destination: Path,
) -> dict[str, object]:
    manifest_path = destination.with_suffix("").with_suffix(".json")
    anchors_path = destination.with_name(destination.name.replace(".csv.gz", ".anchors.json"))
    if destination.exists() or manifest_path.exists() or anchors_path.exists():
        raise DataQualityError("refusing to overwrite immutable Phase 9D dataset artifacts")
    print("[phase-9d-dataset] 1/5 Authenticating source datasets, folds, lineage, and P9D.1 audit", flush=True)
    source_manifest, folds = _validate_inputs(source_dataset)
    registration = _load_registration(REGISTRATION)
    examples, sources = _read_dataset(source_dataset)
    validate_rows(examples, sources, folds)
    audit = _load_audit(eligibility_audit)
    if _sha256_file(feature_panel) != source_manifest["source_panel_sha256"]:
        raise DataQualityError("Phase 9C feature panel differs from the model dataset")
    label_lineage, feature_lineage = _source_lineage_paths(source_dataset, feature_panel)
    if _sha256_file(label_lineage) != source_manifest["label_lineage_file_sha256"]:
        raise DataQualityError("Phase 9C label lineage differs from its manifest")
    panel_manifest_path = feature_panel.with_suffix("").with_suffix(".json")
    panel_manifest = json.loads(panel_manifest_path.read_text(encoding="utf-8"))
    if _sha256_file(feature_lineage) != panel_manifest["lineage_file_sha256"]:
        raise DataQualityError("Phase 9C feature lineage differs from its manifest")
    monthly_manifest_path = monthly_dataset.with_suffix(".json")
    monthly, monthly_manifest = load_clean_examples(monthly_dataset, monthly_manifest_path)
    if any(row.formation_date >= HOLDOUT or row.outcome_date >= HOLDOUT for row in monthly):
        raise DataQualityError("monthly anchor source reaches the consumed holdout")

    print("[phase-9d-dataset] 2/5 Reconstructing point-in-time full-universe anchor inputs", flush=True)
    _, all_by_formation = _panel_index(feature_panel)
    wanted_formations = sorted({row.formation_date for row in examples})
    by_formation = {formation: all_by_formation[formation] for formation in wanted_formations}
    keys = {(formation, security_id) for formation, rows in by_formation.items() for security_id in rows}
    raw = _load_active_raw_panel(feature_panel, keys)
    security_ids = sorted({security_id for _, security_id in keys})
    sectors, active_values, active_source_sha256 = _load_static_sectors_and_liquidity(
        database_url,
        security_ids=security_ids,
        formations=wanted_formations,
        conservative_asof=True,
    )
    ranked_inputs = _rank_active_inputs(
        raw=raw, by_formation=by_formation, sectors=sectors, active_values=active_values,
    )

    print("[phase-9d-dataset] 3/5 Producing chronological cross-fitted elastic-net anchors", flush=True)
    anchors, anchor_records = build_cross_fitted_anchors(
        folds=folds, monthly=monthly, examples=examples,
        by_formation=by_formation, ranked_inputs=ranked_inputs,
        outcome_dates={
            key: date.fromisoformat(source["outcome_date"])
            for key, source in sources.items()
        },
    )

    print("[phase-9d-dataset] 4/5 Joining frozen labels and two registered accounting families", flush=True)
    staged: list[dict[str, object]] = []
    exclusions = Counter()
    family_coverage = Counter()
    formation_family: dict[date, Counter[str]] = defaultdict(Counter)
    earliest_anchor_formation = min(key[0] for key in anchors)
    for example in examples:
        key = example.formation_date, example.security_id
        anchor = anchors.get(key)
        if anchor is None:
            reason = (
                "initial_insufficient_earlier_anchor_history"
                if example.formation_date < earliest_anchor_formation
                else "fold_local_anchor_required_input_unavailable"
            )
            exclusions[reason] += 1
            continue
        source = sources[key]
        if example.formation_date >= HOLDOUT or date.fromisoformat(source["outcome_date"]) >= HOLDOUT:
            raise DataQualityError("Phase 9D dataset attempted to read the consumed holdout")
        for family in ("investment_issuance", "profitability_quality"):
            if source[f"{family}_informative"] == "true":
                family_coverage[family] += 1
                formation_family[example.formation_date][family] += 1
        anchor_lineage = {
            "episode": anchor.episode,
            "configuration": anchor.configuration,
            "fit_sha256": anchor.fit_sha256,
            "raw_prediction": format(anchor.raw_prediction, ".17g"),
            "centered_rank": format(anchor.centered_rank, ".17g"),
            "active_input_source_sha256": active_source_sha256,
        }
        row: dict[str, object] = {
            "partition": "development",
            "formation_date": example.formation_date.isoformat(),
            "decision_at": source["decision_at"],
            "calendar_month": example.calendar_month,
            "security_id": example.security_id,
            "entry_date": source["entry_date"],
            "outcome_date": source["outcome_date"],
            "outer_validation_fold": str(_outer_validation_fold(folds, example.formation_date) or ""),
            "anchor_episode": anchor.episode,
            "anchor_l1": format(anchor.configuration[0], ".17g"),
            "anchor_l2": format(anchor.configuration[1], ".17g"),
            "anchor_fit_sha256": anchor.fit_sha256,
            "anchor_raw_prediction": format(anchor.raw_prediction, ".17g"),
            "anchor_centered_rank": format(anchor.centered_rank, ".17g"),
            "label_centered_rank": format(example.target, ".17g"),
            "residual_target": format(example.target - anchor.centered_rank, ".17g"),
            "investment_issuance_value": source["investment_issuance_value"],
            "profitability_quality_value": source["profitability_quality_value"],
            "source_sample_weight": source["sample_weight"],
            "residual_sample_weight": "",
            "benchmark_relative_return": source["benchmark_relative_return"],
            "investment_issuance_informative": source["investment_issuance_informative"],
            "profitability_quality_informative": source["profitability_quality_informative"],
            "source_panel_row_sha256": source["source_panel_row_sha256"],
            "label_sha256": source["label_sha256"],
            "source_dataset_row_sha256": source["dataset_row_sha256"],
            "anchor_lineage_sha256": _canonical_hash(anchor_lineage),
        }
        staged.append(row)
    month_counts = Counter(str(row["calendar_month"]) for row in staged)
    for row in staged:
        row["residual_sample_weight"] = format(1.0 / month_counts[str(row["calendar_month"])], ".17g")
        row["dataset_row_sha256"] = _row_digest(row)
    staged.sort(key=lambda row: (row["formation_date"], row["security_id"]))
    if not staged:
        raise DataQualityError("Phase 9D residual dataset is empty")

    fields = tuple(staged[0])
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as raw_output:
        with gzip.GzipFile(filename="", fileobj=raw_output, mode="wb", mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="") as text_output:
                writer = csv.DictWriter(text_output, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                writer.writerows(staged)

    print("[phase-9d-dataset] 5/5 Verifying coverage, folds, provenance, and deterministic hashes", flush=True)
    formation_counts = Counter(date.fromisoformat(str(row["formation_date"])) for row in staged)
    aggregate_coverage = {
        family: family_coverage[family] / len(staged) for family in ("investment_issuance", "profitability_quality")
    }
    minimum_coverage = {
        family: min(
            formation_family[formation][family] / count
            for formation, count in formation_counts.items()
        )
        for family in aggregate_coverage
    }
    row_hashes = [str(row["dataset_row_sha256"]) for row in staged]
    anchor_document: dict[str, object] = {
        "anchor_protocol": "chronological_cross_fitted_monthly_elastic_net_v1",
        "earliest_tuning_episode": EARLIEST_TUNING_EPISODE,
        "earliest_residual_formation": min(formation_counts).isoformat(),
        "episodes": anchor_records,
        "anchor_source_sha256": active_source_sha256,
        "anchor_row_count_full_universe": len(anchors),
    }
    anchor_document["anchor_manifest_sha256"] = _canonical_hash(anchor_document)
    _write_json(anchors_path, anchor_document)
    month_weight_sums = {
        month: sum(
            float(row["residual_sample_weight"])
            for row in staged if row["calendar_month"] == month
        )
        for month in sorted(month_counts)
    }
    selection_overlap_violations = sum(
        date.fromisoformat(str(diagnostic["latest_outcome_used"]))
        >= date.fromisoformat(str(diagnostic["selection_information_cutoff_exclusive"]))
        for episode in anchor_records
        for diagnostic in episode.get("configuration_diagnostics", ())
        if diagnostic.get("latest_outcome_used")
    )
    gates = {
        "holdout_not_read": all(
            date.fromisoformat(str(row["formation_date"])) < HOLDOUT
            and date.fromisoformat(str(row["outcome_date"])) < HOLDOUT
            for row in staged
        ),
        "label_overlap_violations_zero": folds["label_overlap_violations"] == 0,
        "all_rows_have_cross_fitted_anchor": len(staged) == len(examples) - sum(exclusions.values()),
        "all_rows_have_complete_lineage": all(
            row[column] for row in staged for column in (
                "source_panel_row_sha256", "label_sha256", "source_dataset_row_sha256",
                "anchor_fit_sha256", "anchor_lineage_sha256", "dataset_row_sha256",
            )
        ),
        "correction_family_aggregate_coverage": all(value >= 0.80 for value in aggregate_coverage.values()),
        "correction_family_minimum_formation_coverage": all(value >= 0.70 for value in minimum_coverage.values()),
        "existing_fold_hash_preserved": bool(folds["fold_sha256"]),
        "anchor_selection_outcome_overlap_violations_zero": selection_overlap_violations == 0,
        "monthly_weights_sum_to_one": all(
            math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-12)
            for total in month_weight_sums.values()
        ),
    }
    provenance = {
        "source_dataset_sha256": _sha256_file(source_dataset),
        "source_dataset_report_sha256": source_manifest["report_sha256"],
        "source_label_lineage_sha256": _sha256_file(label_lineage),
        "source_feature_panel_sha256": _sha256_file(feature_panel),
        "source_feature_panel_report_sha256": panel_manifest["report_hash"],
        "source_feature_lineage_sha256": _sha256_file(feature_lineage),
        "monthly_anchor_dataset_sha256": _sha256_file(monthly_dataset),
        "monthly_anchor_manifest_sha256": _sha256_file(monthly_manifest_path),
        "p9d1_audit_sha256": audit["audit_sha256"],
        "phase_9d_registration_sha256": _sha256_file(REGISTRATION),
        "phase_9d_registration_logical_sha256": registration["registration_sha256"],
        "amended_protocol_sha256": _sha256_file(PROTOCOL),
        "fold_sha256": folds["fold_sha256"],
        "active_input_source_sha256": active_source_sha256,
        "anchor_manifest_sha256": anchor_document["anchor_manifest_sha256"],
        "builder_code_sha256": _canonical_hash({
            path.name: _sha256_file(path)
            for path in (
                Path(__file__),
                Path(__file__).with_name("model_eligibility.py"),
                Path(__file__).with_name("model_evaluation_repair.py"),
                Path(__file__).with_name("phase_9d_eligibility_audit.py"),
            )
        }),
    }
    report: dict[str, object] = {
        "dataset_key": DATASET_KEY,
        "dataset_version": DATASET_VERSION,
        "row_count": len(staged),
        "formation_count": len(formation_counts),
        "formation_start": min(formation_counts).isoformat(),
        "formation_end": max(formation_counts).isoformat(),
        "security_count": len({row["security_id"] for row in staged}),
        "excluded_rows": dict(sorted(exclusions.items())),
        "model_features": list(CORRECTION_COLUMNS),
        "target": "label_centered_rank_minus_cross_fitted_anchor_centered_rank",
        "availability_indicators_enter_model": False,
        "weighting": "each calendar month sums to one across included weekly security rows",
        "month_weight_sums": month_weight_sums,
        "aggregate_informative_coverage": aggregate_coverage,
        "minimum_formation_informative_coverage": minimum_coverage,
        "outer_validation_rows": {
            str(fold): sum(row["outer_validation_fold"] == str(fold) for row in staged)
            for fold in range(1, 5)
        },
        "source_example_count": len(examples),
        "anchor_selection_outcome_overlap_violations": selection_overlap_violations,
        "dataset_logical_sha256": sha256("\n".join(row_hashes).encode()).hexdigest(),
        "dataset_file_sha256": _sha256_file(destination),
        "provenance": provenance,
        "gates": gates,
        "passed": all(gates.values()),
        "holdout_used": False,
        "live_model_changed": False,
        "limitations": [
            "Tier B current-survivors cohort is survivorship biased",
            "current sectors are static and not historical point-in-time classifications",
            "the earliest registered inner validation episode tunes later anchors only and is excluded",
            "reused development history cannot provide independent confirmation or deployment approval",
        ],
    }
    report["report_sha256"] = _canonical_hash(report)
    _write_json(manifest_path, report)
    if not report["passed"]:
        raise DataQualityError("Phase 9D residual dataset failed its integrity gates")
    print(
        f"[phase-9d-dataset] Complete: rows={len(staged)}; formations={len(formation_counts)}; "
        f"dataset_sha256={report['dataset_file_sha256']}; live_model_changed=false",
        flush=True,
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--source-dataset", type=Path, default=Path("data/derived/phase_9c_weekly_rank_development_v1.csv.gz"))
    parser.add_argument("--feature-panel", type=Path, default=Path("data/derived/phase_9c_weekly_feature_panel_v1.csv.gz"))
    parser.add_argument("--monthly-dataset", type=Path, default=Path("data/derived/training/tier_b_clean_monthly_model_development_v1.csv"))
    parser.add_argument("--eligibility-audit", type=Path, default=Path("data/derived/phase_9d_exact_zero_eligibility_audit_v1.json"))
    parser.add_argument("--destination", type=Path, default=Path("data/derived/phase_9d_anchored_residual_development_v1.csv.gz"))
    arguments = parser.parse_args()
    values = dict(__import__("os").environ)
    values.update(_dotenv_values(arguments.env_file))
    database_url = values.get("DATABASE_URL")
    if not database_url:
        raise DataQualityError("DATABASE_URL is required")
    materialize_dataset(
        database_url=database_url,
        source_dataset=arguments.source_dataset,
        feature_panel=arguments.feature_panel,
        monthly_dataset=arguments.monthly_dataset,
        eligibility_audit=arguments.eligibility_audit,
        destination=arguments.destination,
    )


if __name__ == "__main__":
    main()
