"""Chronological, paired research comparison. Never registers or deploys a model."""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import replace
from datetime import date
import csv
import gzip
import io
import json
import math
from pathlib import Path
import random
from statistics import fmean

from .clean_monthly_model_dataset import load_clean_examples
from .monthly_model_comparison import fit_linear_model
from .phase_9c_model_comparison import (
    Example, Prediction, LinearFit, RIDGE_PENALTIES, _validate_inputs, _read_dataset,
    _sha256_file, _canonical_hash, _load_active_raw_panel, _attach_active_features,
    _load_static_sectors_and_liquidity, _rows_for, _predict, _fit_document,
    fit_ridge, monthly_rank_ic,
)
from .quality import DataQualityError
from .score_run import _dotenv_values

REFERENCE = "monthly_elastic_net_fold_local"
CHALLENGER = "weekly_six_family_ridge_fold_local"
ELASTIC_GRID = tuple((l1, l2) for l1 in (0.0001, 0.001) for l2 in (0.001, 0.01, 0.1))
HOLDOUT = date(2025, 7, 1)
PROTOCOL = Path("MODEL_EVALUATION_REPAIR_PROTOCOL.md")


def progress(message: str) -> None:
    print(f"[evaluation-repair] {message}", flush=True)


def validate_rows(examples, sources, folds) -> None:
    """Do not trust a previously recorded zero-violations counter alone."""
    if len(examples) != len(sources):
        raise DataQualityError("dataset key count mismatch")
    outcomes = {}
    by_date = defaultdict(list)
    for item in examples:
        key = item.formation_date, item.security_id
        raw = sources[key]
        outcome = date.fromisoformat(raw["outcome_date"])
        entry = date.fromisoformat(raw["entry_date"])
        if not item.formation_date < entry < outcome < HOLDOUT:
            raise DataQualityError("invalid or holdout-reaching outcome")
        if not all(math.isfinite(x) for x in (*item.family_features, item.target,
                                               item.relative_return, item.sample_weight)):
            raise DataQualityError("non-finite dataset value")
        if item.sample_weight <= 0:
            raise DataQualityError("non-positive sample weight")
        outcomes[key] = outcome
        by_date[item.formation_date].append(item)
    for outer in folds["outer_folds"]:
        for split in [outer, *outer["inner_folds"]]:
            train = [date.fromisoformat(x) for x in split["training_formations"]]
            valid = [date.fromisoformat(x) for x in split["validation_formations"]]
            if not train or not valid or len(train) != len(set(train)) or len(valid) != len(set(valid)):
                raise DataQualityError("empty or duplicate fold dates")
            if max(train) >= min(valid) or any(x not in by_date for x in train + valid):
                raise DataQualityError("non-chronological or missing fold dates")
            if any(outcomes[x.formation_date, x.security_id] >= min(valid)
                   for day in train for x in by_date[day]):
                raise DataQualityError("training outcome overlaps validation")
            if split is not outer and not set(train + valid) <= {
                date.fromisoformat(x) for x in outer["training_formations"]
            }:
                raise DataQualityError("inner window escapes outer training")


def reference_training(monthly, split):
    cutoff = date.fromisoformat(max(split["training_formations"]))
    start = date.fromisoformat(min(split["validation_formations"]))
    selected = [x for x in monthly if x.formation_date <= cutoff and x.outcome_date < start]
    if len({x.formation_date for x in selected}) < 6:
        raise DataQualityError("insufficient earlier monthly reference history")
    return selected


def fit_reference(rows, params):
    model = fit_linear_model(rows, lambda x: x.base, family="elastic_net", l1=params[0], l2=params[1])
    result = LinearFit(model.means, model.scales, model.intercept, model.coefficients)
    if not all(math.isfinite(x) for x in (*result.means, *result.scales, *result.coefficients, result.target_mean)):
        raise DataQualityError("non-finite reference fit")
    return result


def attach_full_universe(examples, panel, database_url):
    # Peer ranks must not depend on whether a future label was completed.
    universe = []
    wanted_dates = {x.formation_date for x in examples}
    with gzip.open(panel, "rt", encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            day = date.fromisoformat(raw["formation_date"])
            if day in wanted_dates:
                universe.append(Example(day, day.strftime("%Y-%m"), raw["security_id"],
                                        0, 0, 1, (), "reference-peer-only"))
    keys = {(x.formation_date, x.security_id) for x in universe}
    if len(keys) != len(universe):
        raise DataQualityError("duplicate reference peer row")
    raw = _load_active_raw_panel(panel, keys)
    sectors, values, lineage = _load_static_sectors_and_liquidity(
        database_url, security_ids=sorted({x.security_id for x in universe}),
        formations=sorted(wanted_dates), conservative_asof=True,
    )
    attached = _attach_active_features(universe, raw, sectors, values)
    index = {(x.formation_date, x.security_id): x.active_features for x in attached}
    result = [replace(x, active_features=index[x.formation_date, x.security_id]) for x in examples]
    if any(not all(math.isfinite(v) for v in x.active_features) for x in result if x.active_features is not None):
        raise DataQualityError("non-finite reference inputs")
    return result, lineage


def select_configuration(records):
    best = max(x["mean_monthly_rank_ic"] for x in records)
    # Both grids are ordered by increasing regularization.
    return max(x["configuration"] for x in records if x["mean_monthly_rank_ic"] >= best - 0.002)


def tune(monthly, index, outer, model_key):
    records = []
    grid = ELASTIC_GRID if model_key == REFERENCE else RIDGE_PENALTIES
    for config in grid:
        predictions = []
        for inner in outer["inner_folds"]:
            training = _rows_for(inner["training_formations"], index)
            validation = [x for x in _rows_for(inner["validation_formations"], index)
                          if x.active_features is not None]
            if not validation:
                raise DataQualityError("empty paired inner sample")
            if model_key == REFERENCE:
                fit = fit_reference(reference_training(monthly, inner), config)
                getter = lambda x: x.active_features
            else:
                fit = fit_ridge(training, penalty=config, feature_getter=lambda x: x.family_features)
                getter = lambda x: x.family_features
            predictions.extend(_predict(model_key, outer["outer_fold"], fit, validation, getter))
        score, monthly_ic = monthly_rank_ic(predictions)
        records.append({"configuration": config, "mean_monthly_rank_ic": score, "monthly_rank_ic": monthly_ic})
    return select_configuration(records), records


def bootstrap(deltas):
    values = list(deltas)
    if len(values) < 6:
        raise DataQualityError("insufficient months for uncertainty diagnostic")
    rng = random.Random(20260830)
    samples = []
    for _ in range(10000):
        drawn = []
        while len(drawn) < len(values):
            start = rng.randrange(len(values))
            drawn.extend(values[(start + j) % len(values)] for j in range(3))
        samples.append(fmean(drawn[:len(values)]))
    samples.sort()
    return {"lower_95": samples[249], "upper_95": samples[9749],
            "probability_positive": sum(x > 0 for x in samples) / len(samples),
            "resamples": 10000, "block_months": 3, "seed": 20260830}


def summary(predictions):
    result = {}
    for name in (REFERENCE, CHALLENGER):
        rows = [x for x in predictions if x.model_key == name]
        score, months = monthly_rank_ic(rows)
        groups = defaultdict(list)
        for x in rows:
            groups[x.example.formation_date].append(x)
        top_months = defaultdict(list)
        for day, group in groups.items():
            if len(group) < 20:
                raise DataQualityError("fewer than 20 paired stocks")
            top = sorted(group, key=lambda x: (-x.value, x.example.security_id))[:20]
            top_months[day.strftime("%Y-%m")].append(fmean(x.example.relative_return for x in top))
        result[name] = {"paired_rows": len(rows), "mean_monthly_rank_ic": score,
                        "monthly_rank_ic": months,
                        "outer_block_rank_ic": {str(f): monthly_rank_ic([x for x in rows if x.outer_fold == f])[0]
                                                for f in sorted({x.outer_fold for x in rows})},
                        "weekly_top20_gross_relative_return_diagnostic": fmean(fmean(x) for x in top_months.values())}
    a, b = result[REFERENCE]["monthly_rank_ic"], result[CHALLENGER]["monthly_rank_ic"]
    if a.keys() != b.keys():
        raise DataQualityError("unpaired monthly evaluation")
    result["challenger_minus_reference_ic"] = fmean(b[k] - a[k] for k in sorted(a))
    result["paired_ic_bootstrap"] = bootstrap([b[k] - a[k] for k in sorted(a)])
    return result


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def run(*, dataset, panel, monthly_path, output, database_url):
    if output.exists():
        raise DataQualityError("output run directory already exists; use a new --output directory")
    progress("1/7 Authenticating frozen development artifacts and actual-outcome purges")
    metadata, folds = _validate_inputs(dataset)
    if _sha256_file(panel) != metadata["source_panel_sha256"]:
        raise DataQualityError("feature panel hash mismatch")
    examples, sources = _read_dataset(dataset)
    validate_rows(examples, sources, folds)
    monthly_manifest = monthly_path.with_suffix(".json")
    monthly, _ = load_clean_examples(monthly_path, monthly_manifest)
    if any(not x.formation_date < x.outcome_date < HOLDOUT for x in monthly):
        raise DataQualityError("monthly reference label reaches holdout")
    output.mkdir(parents=True, exist_ok=False)
    provenance = {"protocol_sha256": _sha256_file(PROTOCOL), "dataset_sha256": _sha256_file(dataset),
                  "panel_sha256": _sha256_file(panel), "monthly_sha256": _sha256_file(monthly_path),
                  "monthly_manifest_sha256": _sha256_file(monthly_manifest), "fold_sha256": folds["fold_sha256"],
                  "code_sha256": _canonical_hash({p.name: _sha256_file(p) for p in (
                      Path(__file__), Path(__file__).with_name("phase_9c_model_comparison.py"),
                      Path(__file__).with_name("monthly_model_comparison.py"))})}
    write_json(output / "started.json", provenance)
    progress("2/7 Reconstructing full-universe reference inputs (read-only database, no downloads)")
    examples, lineage = attach_full_universe(examples, panel, database_url)
    provenance["reference_source_sha256"] = lineage
    index = defaultdict(list)
    for x in examples:
        index[x.formation_date].append(x)
    predictions, fits, coverage = [], [], []
    for outer in folds["outer_folds"]:
        number = outer["outer_fold"]
        progress(f"{number + 2}/7 Outer block {number}/4: inner tuning, earlier-only fitting, paired validation")
        training = _rows_for(outer["training_formations"], index)
        all_validation = _rows_for(outer["validation_formations"], index)
        paired = [x for x in all_validation if x.active_features is not None]
        coverage.append({"outer_fold": number, "eligible_label_rows": len(all_validation),
                         "paired_rows": len(paired), "excluded_missing_reference_inputs": len(all_validation) - len(paired)})
        reference_rows = reference_training(monthly, outer)
        record = {"outer_fold": number, "training_end": max(outer["training_formations"]),
                  "validation_start": min(outer["validation_formations"]),
                  "validation_end": max(outer["validation_formations"]),
                  "reference_training_end": max(x.formation_date for x in reference_rows).isoformat(),
                  "reference_max_outcome": max(x.outcome_date for x in reference_rows).isoformat(),
                  "reference_training_rows": len(reference_rows), "challenger_training_rows": len(training)}
        for name in (REFERENCE, CHALLENGER):
            config, tuning = tune(monthly, index, outer, name)
            fit = fit_reference(reference_rows, config) if name == REFERENCE else fit_ridge(
                training, penalty=config, feature_getter=lambda x: x.family_features)
            getter = (lambda x: x.active_features) if name == REFERENCE else (lambda x: x.family_features)
            predictions.extend(_predict(name, number, fit, paired, getter))
            record[name] = {"configuration": config, "inner_tuning": tuning, **_fit_document(fit)}
        fits.append(record)
        write_json(output / f"fold-{number}.json", record)
    progress("7/7 Writing research-only fits, paired metrics, and reproducibility hashes")
    # Final settings selected from the last registered INNER windows, never outer diagnostics.
    final = {}
    for name in (REFERENCE, CHALLENGER):
        config = fits[-1][name]["configuration"]
        fit = fit_reference(monthly, config) if name == REFERENCE else fit_ridge(
            examples, penalty=config, feature_getter=lambda x: x.family_features)
        final[name] = {"configuration": config, "selection": "last outer block's registered inner windows only",
                       "status": "research_only_not_deployable", **_fit_document(fit)}
    prediction_file = output / "predictions.csv.gz"
    with prediction_file.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, lineterminator="\n")
                writer.writerow(["model", "fold", "formation_date", "security_id", "prediction", "target", "relative_return", "source_row_sha256"])
                for x in sorted(predictions, key=lambda p: (p.model_key, p.outer_fold, p.example.formation_date, p.example.security_id)):
                    writer.writerow([x.model_key, x.outer_fold, x.example.formation_date, x.example.security_id,
                                     format(x.value, ".17g"), format(x.example.target, ".17g"),
                                     format(x.example.relative_return, ".17g"), x.example.dataset_row_sha256])
    write_json(output / "final-research-fits.json", final)
    report = {"version": "leakage_safe_evaluation_repair_v1", "provenance": provenance,
              "coverage": coverage, "metrics": summary(predictions),
              "prediction_sha256": _sha256_file(prediction_file),
              "fits_sha256": _canonical_hash(fits), "final_fit_sha256": _canonical_hash(final),
              "holdout_used": False, "deployed": False, "independent_confirmation": False,
              "decision": "diagnostic_only_pending_portfolio_and_forward_gates",
              "limitations": ["Tier-B survivors and static sectors", "reused development history",
                              "recipe comparison, not isolated estimator effect",
                              "reference-complete paired sample may be non-random",
                              "weekly top20 overlapping gross outcomes are not a tradable portfolio",
                              "legacy monthly reference target is split-adjusted; evaluation labels include dividends"]}
    write_json(output / "report.json", report)
    progress(f"Complete. Report: {output / 'report.json'}; live model unchanged")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--dataset", type=Path, default=Path("data/derived/phase_9c_weekly_rank_development_v1.csv.gz"))
    parser.add_argument("--panel", type=Path, default=Path("data/derived/phase_9c_weekly_feature_panel_v1.csv.gz"))
    parser.add_argument("--monthly", type=Path, default=Path("data/derived/training/tier_b_clean_monthly_model_development_v1.csv"))
    args = parser.parse_args()
    values = _dotenv_values(args.env_file)
    if not values.get("DATABASE_URL"):
        raise DataQualityError("DATABASE_URL is required for read-only reference reconstruction")
    run(dataset=args.dataset, panel=args.panel, monthly_path=args.monthly,
        output=args.output, database_url=values["DATABASE_URL"])


if __name__ == "__main__":
    main()
