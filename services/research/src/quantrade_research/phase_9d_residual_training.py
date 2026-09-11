"""Fit the frozen Phase 9D residual-ridge challenger in chronological folds."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from dataclasses import dataclass
from datetime import date
import gzip
from hashlib import sha256
import io
import json
import math
from pathlib import Path
from statistics import fmean
from typing import Mapping, Sequence

from .phase_9c_model_comparison import _canonical_hash, _sha256_file, _solve, spearman
from .phase_9d_eligibility_audit import _load_registration
from .phase_9d_residual_dataset import (
    CORRECTION_COLUMNS,
    DATASET_KEY,
    DATASET_VERSION,
    ResidualExample,
    load_residual_dataset,
)
from .quality import DataQualityError


MODEL_KEY = "anchored_accounting_residual_ridge_v1"
TRAINING_VERSION = "v1"
PENALTIES = (1.0, 10.0, 100.0)
TIE_TOLERANCE = 0.002
HOLDOUT_START = date(2025, 7, 1)
REGISTRATION = Path("research/registrations/phase_9d_anchored_stability_v1.json")
DEFAULT_FOLDS = Path("data/derived/phase_9c_weekly_rank_development_v1.folds.json")


@dataclass(frozen=True, slots=True)
class ResidualRidgeFit:
    penalty: float
    means: tuple[float, float]
    scales: tuple[float, float]
    coefficients: tuple[float, float]

    def predict(self, values: Sequence[float]) -> float:
        if len(values) != len(self.means):
            raise DataQualityError("residual feature width differs from fitted model")
        return sum(
            coefficient * ((value - mean) / scale)
            for coefficient, value, mean, scale in zip(
                self.coefficients, values, self.means, self.scales, strict=True,
            )
        )


def _month_balanced_weights(rows: Sequence[ResidualExample]) -> tuple[float, ...]:
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        totals[row.calendar_month] += row.sample_weight
    if not totals or any(value <= 0 for value in totals.values()):
        raise DataQualityError("residual fit has invalid calendar-month weights")
    return tuple(row.sample_weight / totals[row.calendar_month] for row in rows)


def fit_residual_ridge(
    rows: Sequence[ResidualExample], *, penalty: float,
) -> ResidualRidgeFit:
    """Fit weighted standardized ridge with the frozen zero-intercept rule."""
    if not rows or penalty not in PENALTIES:
        raise DataQualityError("residual ridge received an unregistered fit request")
    weights = _month_balanced_weights(rows)
    total = sum(weights)
    means = tuple(
        sum(weight * row.correction_features[index] for weight, row in zip(weights, rows, strict=True)) / total
        for index in range(2)
    )
    scales = tuple(
        math.sqrt(
            sum(
                weight * (row.correction_features[index] - means[index]) ** 2
                for weight, row in zip(weights, rows, strict=True)
            ) / total
        )
        for index in range(2)
    )
    if any(scale <= 1e-12 or not math.isfinite(scale) for scale in scales):
        raise DataQualityError("residual ridge has a degenerate training feature")
    standardized = [
        tuple((value - means[index]) / scales[index] for index, value in enumerate(row.correction_features))
        for row in rows
    ]
    gram = [[0.0, 0.0], [0.0, 0.0]]
    covariance = [0.0, 0.0]
    for weight, values, row in zip(weights, standardized, rows, strict=True):
        for left in range(2):
            covariance[left] += weight * values[left] * row.residual_target / total
            for right in range(2):
                gram[left][right] += weight * values[left] * values[right] / total
    for index in range(2):
        gram[index][index] += penalty
    coefficients = _solve(gram, covariance)
    numeric = (*means, *scales, *coefficients)
    if not all(math.isfinite(value) for value in numeric):
        raise DataQualityError("residual ridge produced non-finite parameters")
    return ResidualRidgeFit(
        penalty, (means[0], means[1]), (scales[0], scales[1]),
        (coefficients[0], coefficients[1]),
    )


def _fit_document(fit: ResidualRidgeFit) -> dict[str, object]:
    document: dict[str, object] = {
        "model_key": MODEL_KEY,
        "family": "ridge",
        "fit_intercept": False,
        "penalty": fit.penalty,
        "feature_columns": list(CORRECTION_COLUMNS),
        "feature_means": fit.means,
        "feature_scales": fit.scales,
        "coefficients": fit.coefficients,
    }
    document["fit_sha256"] = _canonical_hash(document)
    return document


def candidate_prediction(row: ResidualExample, fit: ResidualRidgeFit) -> tuple[float, float]:
    residual = fit.predict(row.correction_features)
    return residual, row.anchor_centered_rank + residual


def _monthly_rank_ic(
    rows: Sequence[ResidualExample], fit: ResidualRidgeFit,
) -> tuple[float, dict[str, float]]:
    by_formation: dict[tuple[str, date], list[ResidualExample]] = defaultdict(list)
    for row in rows:
        by_formation[row.calendar_month, row.formation_date].append(row)
    monthly: dict[str, list[float]] = defaultdict(list)
    for (month, _), formation_rows in sorted(by_formation.items()):
        if len(formation_rows) < 2:
            raise DataQualityError("residual tuning rank IC requires at least two rows")
        monthly[month].append(spearman([
            (
                row.security_id,
                candidate_prediction(row, fit)[1],
                row.label_centered_rank,
            )
            for row in formation_rows
        ]))
    if not monthly:
        raise DataQualityError("residual tuning produced no monthly diagnostics")
    values = {month: fmean(scores) for month, scores in sorted(monthly.items())}
    return fmean(values.values()), values


def _rows_for(
    formations: Sequence[str], index: Mapping[date, Sequence[ResidualExample]],
) -> list[ResidualExample]:
    return [row for value in formations for row in index.get(date.fromisoformat(value), ())]


def _validated_split_rows(
    split: Mapping[str, object], index: Mapping[date, Sequence[ResidualExample]],
) -> tuple[list[ResidualExample], list[ResidualExample]]:
    training = _rows_for(split["training_formations"], index)
    validation = _rows_for(split["validation_formations"], index)
    if not training or not validation:
        raise DataQualityError("registered residual split has insufficient cross-fitted rows")
    validation_start = min(row.formation_date for row in validation)
    if max(row.formation_date for row in training) >= validation_start:
        raise DataQualityError("residual split is not chronological")
    if any(row.outcome_date >= validation_start for row in training):
        raise DataQualityError("residual training outcome overlaps validation")
    return training, validation


def _select_penalty(records: Sequence[Mapping[str, object]]) -> float:
    if {float(record["penalty"]) for record in records} != set(PENALTIES):
        raise DataQualityError("residual tuning did not evaluate the frozen penalty grid")
    best = max(float(record["mean_monthly_rank_ic"]) for record in records)
    return max(
        float(record["penalty"])
        for record in records
        if float(record["mean_monthly_rank_ic"]) >= best - TIE_TOLERANCE
    )


def tune_outer_fold(
    *,
    outer: Mapping[str, object],
    index: Mapping[date, Sequence[ResidualExample]],
) -> tuple[float, list[dict[str, object]], list[dict[str, object]]]:
    predictions: dict[float, list[tuple[ResidualExample, float]]] = {
        penalty: [] for penalty in PENALTIES
    }
    inner_records: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    for inner in outer["inner_folds"]:
        try:
            training, validation = _validated_split_rows(inner, index)
        except DataQualityError as error:
            if "insufficient cross-fitted rows" not in str(error):
                raise
            skipped.append({
                "inner_fold": inner["inner_fold"],
                "reason": "initial_insufficient_earlier_cross_fitted_anchor_history",
            })
            continue
        record: dict[str, object] = {
            "inner_fold": inner["inner_fold"],
            "training_start": min(row.formation_date for row in training).isoformat(),
            "training_end": max(row.formation_date for row in training).isoformat(),
            "latest_training_outcome": max(row.outcome_date for row in training).isoformat(),
            "validation_start": min(row.formation_date for row in validation).isoformat(),
            "validation_end": max(row.formation_date for row in validation).isoformat(),
            "training_rows": len(training),
            "validation_rows": len(validation),
            "penalties": [],
        }
        for penalty in PENALTIES:
            fit = fit_residual_ridge(training, penalty=penalty)
            score, monthly = _monthly_rank_ic(validation, fit)
            record["penalties"].append({
                "penalty": penalty,
                "mean_monthly_rank_ic": score,
                "monthly_rank_ic": monthly,
                "fit_sha256": _fit_document(fit)["fit_sha256"],
            })
            predictions[penalty].extend(
                (row, candidate_prediction(row, fit)[1]) for row in validation
            )
        inner_records.append(record)
    if not inner_records:
        raise DataQualityError("outer fold has no usable inner residual validation")

    aggregate: list[dict[str, object]] = []
    for penalty in PENALTIES:
        by_formation: dict[tuple[str, date], list[tuple[ResidualExample, float]]] = defaultdict(list)
        for row, value in predictions[penalty]:
            by_formation[row.calendar_month, row.formation_date].append((row, value))
        monthly: dict[str, list[float]] = defaultdict(list)
        for (month, _), formation_rows in sorted(by_formation.items()):
            monthly[month].append(spearman([
                (row.security_id, value, row.label_centered_rank)
                for row, value in formation_rows
            ]))
        monthly_values = {month: fmean(values) for month, values in sorted(monthly.items())}
        aggregate.append({
            "penalty": penalty,
            "mean_monthly_rank_ic": fmean(monthly_values.values()),
            "monthly_rank_ic": monthly_values,
            "validation_rows": len(predictions[penalty]),
        })
    return _select_penalty(aggregate), aggregate, inner_records + skipped


def _validate_registration(registration: Mapping[str, object]) -> None:
    candidate = registration.get("candidate")
    if not isinstance(candidate, dict):
        raise DataQualityError("Phase 9D registration has no candidate")
    if candidate.get("model_key") != MODEL_KEY:
        raise DataQualityError("registered Phase 9D candidate differs from the trainer")
    if candidate.get("penalties") != [1, 10, 100] or candidate.get("configuration_count") != 3:
        raise DataQualityError("registered Phase 9D penalty budget differs from the trainer")
    if candidate.get("correction_families") != ["investment_issuance", "profitability_quality"]:
        raise DataQualityError("registered Phase 9D feature set differs from the trainer")
    if candidate.get("fit_intercept") is not False:
        raise DataQualityError("registered Phase 9D residual model must not fit an intercept")


def _load_folds(path: Path, dataset_report: Mapping[str, object]) -> dict[str, object]:
    try:
        folds = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid Phase 9D fold source") from error
    payload = dict(folds)
    recorded = payload.pop("fold_sha256", None)
    if _canonical_hash(payload) != recorded:
        raise DataQualityError("Phase 9D fold manifest hash is invalid")
    if recorded != dataset_report["provenance"].get("fold_sha256"):
        raise DataQualityError("Phase 9D dataset and folds do not match")
    if folds.get("holdout_start") != HOLDOUT_START.isoformat() or folds.get("label_overlap_violations") != 0:
        raise DataQualityError("Phase 9D folds violate the holdout or purge contract")
    if len(folds.get("outer_folds", ())) != 4:
        raise DataQualityError("Phase 9D requires exactly four registered outer folds")
    return folds


def _write_json(path: Path, document: object) -> None:
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def run_training(
    *, dataset: Path, folds_path: Path, registration_path: Path, output: Path,
) -> dict[str, object]:
    if output.exists():
        raise DataQualityError("output run directory already exists; use a new path")
    print("[phase-9d-training] 1/6 Authenticating dataset, folds, and frozen candidate", flush=True)
    rows, dataset_report = load_residual_dataset(dataset)
    registration = _load_registration(registration_path)
    _validate_registration(registration)
    folds = _load_folds(folds_path, dataset_report)
    index: dict[date, list[ResidualExample]] = defaultdict(list)
    for row in rows:
        index[row.formation_date].append(row)
    output.mkdir(parents=True, exist_ok=False)
    provenance = {
        "dataset_sha256": _sha256_file(dataset),
        "dataset_report_sha256": dataset_report["report_sha256"],
        "fold_file_sha256": _sha256_file(folds_path),
        "fold_logical_sha256": folds["fold_sha256"],
        "registration_file_sha256": _sha256_file(registration_path),
        "registration_logical_sha256": registration["registration_sha256"],
        "builder_code_sha256": _sha256_file(Path(__file__)),
    }
    _write_json(output / "started.json", provenance)

    all_predictions: list[dict[str, object]] = []
    fit_records: list[dict[str, object]] = []
    for outer in folds["outer_folds"]:
        number = int(outer["outer_fold"])
        print(
            f"[phase-9d-training] {number + 1}/6 Outer fold {number}/4: inner tuning and earlier-only fit",
            flush=True,
        )
        selected, tuning, inner_records = tune_outer_fold(outer=outer, index=index)
        training, validation = _validated_split_rows(outer, index)
        if any(row.outer_validation_fold != number for row in validation):
            raise DataQualityError("residual dataset outer-fold marker is inconsistent")
        fit = fit_residual_ridge(training, penalty=selected)
        fit_document = _fit_document(fit)
        record: dict[str, object] = {
            "outer_fold": number,
            "training_start": min(row.formation_date for row in training).isoformat(),
            "training_end": max(row.formation_date for row in training).isoformat(),
            "latest_training_outcome": max(row.outcome_date for row in training).isoformat(),
            "validation_start": min(row.formation_date for row in validation).isoformat(),
            "validation_end": max(row.formation_date for row in validation).isoformat(),
            "training_rows": len(training),
            "validation_rows": len(validation),
            "selected_penalty": selected,
            "selection_rule": "highest equal-calendar-month inner rank IC; larger penalty within 0.002",
            "inner_tuning": tuning,
            "inner_fold_details": inner_records,
            "fit": fit_document,
        }
        record["fold_record_sha256"] = _canonical_hash(record)
        fit_records.append(record)
        _write_json(output / f"fold-{number}.json", record)
        for row in validation:
            residual, candidate = candidate_prediction(row, fit)
            prediction: dict[str, object] = {
                "model_key": MODEL_KEY,
                "outer_fold": str(number),
                "formation_date": row.formation_date.isoformat(),
                "calendar_month": row.calendar_month,
                "security_id": row.security_id,
                "anchor_centered_rank": format(row.anchor_centered_rank, ".17g"),
                "predicted_residual": format(residual, ".17g"),
                "candidate_raw_score": format(candidate, ".17g"),
                "label_centered_rank": format(row.label_centered_rank, ".17g"),
                "benchmark_relative_return": format(row.benchmark_relative_return, ".17g"),
                "selected_penalty": format(selected, ".17g"),
                "fit_sha256": fit_document["fit_sha256"],
                "source_dataset_row_sha256": row.dataset_row_sha256,
            }
            prediction["prediction_row_sha256"] = _canonical_hash(prediction)
            all_predictions.append(prediction)

    print("[phase-9d-training] 6/6 Writing deterministic predictions and fit manifest", flush=True)
    all_predictions.sort(key=lambda row: (
        int(row["outer_fold"]), row["formation_date"], row["security_id"],
    ))
    prediction_path = output / "outer-predictions.csv.gz"
    with prediction_path.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="") as text:
                writer = csv.DictWriter(text, fieldnames=tuple(all_predictions[0]), lineterminator="\n")
                writer.writeheader()
                writer.writerows(all_predictions)
    fit_manifest: dict[str, object] = {
        "training_key": MODEL_KEY,
        "training_version": TRAINING_VERSION,
        "candidate_configuration_count": len(PENALTIES),
        "penalties": PENALTIES,
        "feature_columns": CORRECTION_COLUMNS,
        "fit_intercept": False,
        "outer_folds": fit_records,
    }
    fit_manifest["fit_manifest_sha256"] = _canonical_hash(fit_manifest)
    _write_json(output / "fits.json", fit_manifest)
    overlap_violations = sum(
        date.fromisoformat(record["latest_training_outcome"])
        >= date.fromisoformat(record["validation_start"])
        for record in fit_records
    )
    report: dict[str, object] = {
        "training_key": MODEL_KEY,
        "training_version": TRAINING_VERSION,
        "provenance": provenance,
        "configuration_count": len(PENALTIES),
        "penalties": PENALTIES,
        "feature_columns": CORRECTION_COLUMNS,
        "fit_intercept": False,
        "outer_fold_count": len(fit_records),
        "outer_prediction_rows": len(all_predictions),
        "selected_penalties": {
            str(record["outer_fold"]): record["selected_penalty"] for record in fit_records
        },
        "prediction_file_sha256": _sha256_file(prediction_path),
        "prediction_logical_sha256": sha256(
            "\n".join(str(row["prediction_row_sha256"]) for row in all_predictions).encode()
        ).hexdigest(),
        "fit_manifest_sha256": fit_manifest["fit_manifest_sha256"],
        "training_outcome_overlap_violations": overlap_violations,
        "holdout_used": False,
        "outer_performance_evaluated": False,
        "live_model_changed": False,
        "gates": {
            "exact_registered_configuration_count": len(PENALTIES) == 3,
            "exact_registered_features": CORRECTION_COLUMNS == (
                "investment_issuance_value", "profitability_quality_value",
            ),
            "four_outer_fits": len(fit_records) == 4,
            "outer_predictions_complete": len(all_predictions) == sum(
                int(record["validation_rows"]) for record in fit_records
            ),
            "training_outcome_overlap_violations_zero": overlap_violations == 0,
            "all_predictions_before_holdout": all(
                date.fromisoformat(str(row["formation_date"])) < HOLDOUT_START
                for row in all_predictions
            ),
        },
        "limitations": [
            "Tier B current-survivors cohort is survivorship biased",
            "current sectors are static rather than historical point-in-time classifications",
            "outer labels are serialized for P9D.4 but no outer performance metric is computed here",
            "reused development history cannot independently confirm or promote the challenger",
        ],
    }
    report["passed"] = all(report["gates"].values())
    report["report_sha256"] = _canonical_hash(report)
    _write_json(output / "report.json", report)
    if not report["passed"]:
        raise DataQualityError("Phase 9D residual training failed integrity gates")
    print(
        f"[phase-9d-training] Complete: predictions={len(all_predictions)}; "
        f"prediction_sha256={report['prediction_file_sha256']}; outer_metrics_evaluated=false; "
        "live_model_changed=false",
        flush=True,
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/derived/phase_9d_anchored_residual_development_v1.csv.gz"))
    parser.add_argument("--folds", type=Path, default=DEFAULT_FOLDS)
    parser.add_argument("--registration", type=Path, default=REGISTRATION)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    run_training(
        dataset=arguments.dataset, folds_path=arguments.folds,
        registration_path=arguments.registration, output=arguments.output,
    )


if __name__ == "__main__":
    main()
