"""Read-only direct comparison; never deploys or modifies scores."""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from .active_model import load_active_model, _path_from_file_uri
from .clean_monthly_development_validation import _assert_final_fit_matches
from .clean_monthly_model_dataset import load_clean_examples
from .model_evaluation_repair import bootstrap
from .monthly_model_comparison import OUTER_BLOCKS, Prediction, fit_linear_model, metrics
from .phase_9c_model_comparison import _canonical_hash, _sha256_file
from .quality import DataQualityError
from .score_run import _dotenv_values


def compare(examples, configurations):
    if any(not x.formation_date < x.outcome_date < date(2025, 7, 1) for x in examples):
        raise DataQualityError("invalid or holdout-reaching monthly outcome")
    if len({(x.formation_date, x.security_id) for x in examples}) != len(examples):
        raise DataQualityError("duplicate monthly example")
    results, series, sets = {}, {}, {}
    for name, (l1, l2) in configurations.items():
        predictions = []
        for fold, (start, end) in enumerate(OUTER_BLOCKS, 1):
            validation = [x for x in examples if start <= x.formation_date <= end]
            if not validation:
                raise DataQualityError("empty evaluation block")
            first = min(x.formation_date for x in validation)
            training = [x for x in examples if x.outcome_date < first]
            if not training or max(x.formation_date for x in training) >= first:
                raise DataQualityError("invalid training boundary")
            fit = fit_linear_model(training, lambda x: x.base, family="elastic_net", l1=l1, l2=l2)
            predictions.extend(Prediction(name, "base", fold, x.formation_date, x.security_id,
                                          fit.predict(x.base), x.target, x.security_return,
                                          x.benchmark_return, "retrospective") for x in validation)
        results[name] = metrics(predictions)
        days = sorted({x.formation_date for x in predictions})
        series[name] = {day.isoformat(): metrics([x for x in predictions if x.formation_date == day])[
            "mean_monthly_rank_ic"] for day in days}
        sets[name] = {day.isoformat(): {x.security_id for x in sorted(
            [x for x in predictions if x.formation_date == day],
            key=lambda x: (-x.predicted, x.security_id))[:20]} for day in days}
    deltas = [series["new"][day] - series["current"][day] for day in series["current"]]
    return {"results": results, "monthly_rank_ic": series,
            "new_minus_current_ic_bootstrap": bootstrap(deltas),
            "top20_names_different_by_formation": {
                day: len(sets["new"][day] - sets["current"][day]) for day in sets["current"]},
            "decision": "no_swap_without_independent_confirmation_and_existing_promotion_gates",
            "deployed": False, "holdout_read": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--candidate-run", type=Path,
                        default=Path("data/derived/evaluation-repair/20260907-v1-replay"))
    args = parser.parse_args()
    database_url = _dotenv_values(args.env_file)["DATABASE_URL"]
    active = load_active_model(database_url)
    import psycopg
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute("SELECT artifact_uri,artifact_sha256 FROM quantrade.model_artifacts WHERE model_version=%s",
                       (active.model_version,))
        uri, digest = cursor.fetchone()
    artifact_path = _path_from_file_uri(uri)
    if _sha256_file(artifact_path) != digest:
        raise DataQualityError("active artifact hash mismatch")
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    if artifact.get("family") != "elastic_net":
        raise DataQualityError("current model is not the expected elastic net")
    final = json.loads((args.candidate_run / "final-research-fits.json").read_text(encoding="utf-8"))
    report = json.loads((args.candidate_run / "report.json").read_text(encoding="utf-8"))
    if _canonical_hash(final) != report["final_fit_sha256"]:
        raise DataQualityError("candidate fit hash mismatch")
    dataset = Path("data/derived/training/tier_b_clean_monthly_model_development_v1.csv")
    examples, metadata = load_clean_examples(dataset, dataset.with_suffix(".json"))
    if metadata["content_sha256"] != report["provenance"]["monthly_sha256"]:
        raise DataQualityError("candidate training lineage mismatch")
    if artifact["source_dataset"]["content_sha256"] != metadata["content_sha256"]:
        raise DataQualityError("active training lineage differs")
    _assert_final_fit_matches(artifact, examples)
    candidate = final["monthly_elastic_net_fold_local"]
    configs = {"current": (artifact["l1_penalty"], artifact["l2_penalty"]),
               "new": tuple(candidate["configuration"])}
    fit = fit_linear_model(examples, lambda x: x.base, family="elastic_net",
                           l1=configs["new"][0], l2=configs["new"][1])
    if tuple(candidate["coefficients"]) != fit.coefficients or tuple(candidate["feature_means"]) != fit.means or (
        tuple(candidate["feature_scales"]) != fit.scales or candidate["target_mean"] != fit.intercept
    ):
        raise DataQualityError("candidate does not reproduce from the registered configuration")
    result = compare(examples, configs)
    result.update({"active_model": active.model_version, "configurations": configs,
                   "source_dataset_sha256": metadata["content_sha256"],
                   "active_artifact_sha256": digest, "candidate_fit_sha256": report["final_fit_sha256"]})
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
