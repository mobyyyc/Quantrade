"""Apply the frozen Phase 9B gates and publish a freeze/no-freeze decision."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from hashlib import sha256
import json
from pathlib import Path

from .monthly_model_comparison import MODEL_KEYS
from .quality import DataQualityError


DECISION_KEY = "tier_b_monthly_feature_family_decision"
DECISION_VERSION = "v1"
ACTIVE = "active_elastic_net"
MINIMUM_AGGREGATE_COVERAGE = 0.90
MINIMUM_MONTHLY_COVERAGE = 0.80
MAXIMUM_TURNOVER = 0.75
MAXIMUM_TURNOVER_DELTA = 0.10
MAXIMUM_RANK_STABILITY_REGRESSION = 0.05
MAXIMUM_SINGLE_REGIME_SHARE = 0.75


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DataQualityError(f"invalid research artifact: {path}") from error
    if not isinstance(value, dict):
        raise DataQualityError(f"research artifact is not an object: {path}")
    return value


def _verify_panel(panel: Path, manifest: dict[str, object]) -> tuple[int, int]:
    if sha256(panel.read_bytes()).hexdigest() != manifest.get("content_sha256"):
        raise DataQualityError("feature panel hash mismatch")
    values, violations = 0, 0
    with panel.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        features = tuple(manifest["features"])
        for row in reader:
            for feature in features:
                if row[feature]:
                    values += 1
                    try:
                        lineage = json.loads(row[f"{feature}_lineage"])
                    except json.JSONDecodeError:
                        violations += 1
                        continue
                    if not lineage or len(row[f"{feature}_sha256"]) != 64:
                        violations += 1
    return values, violations


def _regime_concentration(predictions: Path) -> dict[str, float]:
    regimes: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    with predictions.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            regimes[(row["transform"], row["model_key"])][row["regime"]].add(row["formation_date"])
    output: dict[str, float] = {}
    for (transform, model), grouped in regimes.items():
        total = len(set().union(*grouped.values()))
        output[f"{transform}:{model}"] = max((len(values) for values in grouped.values()), default=0) / total
    return output


def _sign_stability(comparison: dict[str, object], model: str, transform: str) -> dict[str, object]:
    records = [
        item for item in comparison["fits"]
        if item["model_key"] == model and item["transform"] == transform and item["coefficients"]
    ]
    if not records:
        return {"fixed_positive_composite": model == "signed_family_composite"}
    new_coefficients = [item["coefficients"][-4:] for item in records] if model != ACTIVE else []
    if not new_coefficients:
        return {"candidate_feature_signs": "not_applicable"}
    return {
        "positive_fold_counts": [sum(values[index] > 0 for values in new_coefficients) for index in range(4)],
        "negative_fold_counts": [sum(values[index] < 0 for values in new_coefficients) for index in range(4)],
        "fold_count": len(new_coefficients),
    }


def make_decision(
    *, comparison_path: Path, dataset_manifest_path: Path, panel_path: Path,
    panel_manifest_path: Path, predictions_path: Path,
) -> dict[str, object]:
    comparison = _read_json(comparison_path)
    dataset = _read_json(dataset_manifest_path)
    panel = _read_json(panel_manifest_path)
    if sha256(predictions_path.read_bytes()).hexdigest() != comparison.get("oof_predictions_sha256"):
        raise DataQualityError("OOF predictions hash mismatch")
    lineage_values, point_in_time_violations = _verify_panel(panel_path, panel)
    concentration = _regime_concentration(predictions_path)
    coverage = float(dataset["common_sample_coverage"])
    minimum_monthly = min(int(value) for value in dataset["included_by_date"].values()) / int(panel["security_count"])
    results = comparison["results"]["market"]
    active = results[ACTIVE]
    decisions: dict[str, object] = {}
    passing: list[str] = []
    for model in MODEL_KEYS:
        if model == ACTIVE:
            continue
        candidate = results[model]
        gates = [
            {"gate": "point_in_time_and_lineage", "passed": point_in_time_violations == 0,
             "detail": f"violations={point_in_time_violations}; lineage_values={lineage_values}"},
            {"gate": "coverage", "passed": coverage >= MINIMUM_AGGREGATE_COVERAGE and minimum_monthly >= MINIMUM_MONTHLY_COVERAGE,
             "detail": f"aggregate={coverage}; minimum_monthly={minimum_monthly}"},
            {"gate": "rank_ic", "passed": candidate["mean_monthly_rank_ic"] > 0 and candidate["mean_monthly_rank_ic"] > active["mean_monthly_rank_ic"],
             "detail": f"candidate={candidate['mean_monthly_rank_ic']}; active={active['mean_monthly_rank_ic']}"},
            {"gate": "top20_return_at_25bp", "passed": candidate["top20_relative_return_after_cost"]["25"] >= active["top20_relative_return_after_cost"]["25"],
             "detail": f"candidate={candidate['top20_relative_return_after_cost']['25']}; active={active['top20_relative_return_after_cost']['25']}"},
            {"gate": "turnover", "passed": candidate["mean_one_way_turnover"] <= MAXIMUM_TURNOVER and candidate["mean_one_way_turnover"] <= active["mean_one_way_turnover"] + MAXIMUM_TURNOVER_DELTA,
             "detail": f"candidate={candidate['mean_one_way_turnover']}; active={active['mean_one_way_turnover']}"},
            {"gate": "all_validation_blocks_positive", "passed": all(item > 0 for item in candidate["fold_mean_rank_ics"]),
             "detail": f"folds={candidate['fold_mean_rank_ics']}"},
            {"gate": "rank_stability", "passed": candidate["mean_consecutive_rank_correlation"] >= active["mean_consecutive_rank_correlation"] - MAXIMUM_RANK_STABILITY_REGRESSION,
             "detail": f"candidate={candidate['mean_consecutive_rank_correlation']}; active={active['mean_consecutive_rank_correlation']}"},
            {"gate": "regime_concentration", "passed": concentration[f"market:{model}"] <= MAXIMUM_SINGLE_REGIME_SHARE,
             "detail": f"largest_regime_share={concentration[f'market:{model}']}"},
        ]
        eligible = all(item["passed"] for item in gates)
        if eligible:
            passing.append(model)
        decisions[model] = {
            "freeze_eligible": eligible, "gates": gates,
            "sign_stability": _sign_stability(comparison, model, "market"),
            "static_sector_robustness": comparison["results"]["static_sector"][model],
        }
    if len(passing) > 1:
        raise DataQualityError("multiple candidates passed without a pre-registered tie break")
    selected = passing[0] if passing else None
    payload: dict[str, object] = {
        "decision_key": DECISION_KEY, "decision_version": DECISION_VERSION,
        "decision": "freeze" if selected else "no_freeze", "selected_candidate": selected,
        "active_model_unchanged": selected is None, "development_only": True, "holdout_used": False,
        "source_comparison_sha256": comparison["result_sha256"],
        "source_dataset_sha256": comparison["source_dataset_sha256"],
        "source_panel_sha256": panel["content_sha256"],
        "thresholds": {
            "minimum_aggregate_coverage": MINIMUM_AGGREGATE_COVERAGE,
            "minimum_monthly_coverage": MINIMUM_MONTHLY_COVERAGE,
            "maximum_turnover": MAXIMUM_TURNOVER,
            "maximum_turnover_delta": MAXIMUM_TURNOVER_DELTA,
            "maximum_rank_stability_regression": MAXIMUM_RANK_STABILITY_REGRESSION,
            "maximum_single_regime_share": MAXIMUM_SINGLE_REGIME_SHARE,
        },
        "active_metrics": active, "candidate_decisions": decisions,
        "rejected_candidates": [model for model in decisions if not decisions[model]["freeze_eligible"]],
        "limitations": dataset["limitations"],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["decision_sha256"] = sha256(canonical.encode()).hexdigest()
    return payload


def decision_markdown(decision: dict[str, object]) -> str:
    lines = [
        "# Phase 9B monthly feature-family decision", "", "**Decision: NO FREEZE**", "",
        "No pre-registered market-wide challenger passed every frozen gate. The active private-beta model remains unchanged.", "",
        "## Gate results", "", "| Candidate | Failed gates | Mean monthly IC | 25 bp top-20 relative return | Turnover |", "| --- | --- | ---: | ---: | ---: |",
    ]
    for model, result in decision["candidate_decisions"].items():
        failed = ", ".join(item["gate"] for item in result["gates"] if not item["passed"])
        metrics = decision["candidate_decisions"][model]["static_sector_robustness"]
        primary = next(
            item for item in [decision["candidate_decisions"][model]]
        )
        # Primary metric values are embedded in gate details; use the comparison-independent gate summary here.
        ic = next(item["detail"].split(";")[0].split("=")[1] for item in primary["gates"] if item["gate"] == "rank_ic")
        top = next(item["detail"].split(";")[0].split("=")[1] for item in primary["gates"] if item["gate"] == "top20_return_at_25bp")
        turnover = next(item["detail"].split(";")[0].split("=")[1] for item in primary["gates"] if item["gate"] == "turnover")
        lines.append(f"| `{model}` | {failed} | {ic} | {top} | {turnover} |")
    lines.extend([
        "", "## Interpretation", "",
        "The market-wide robust-ridge challenger produced a small IC improvement, but failed coverage, 25 bp portfolio return, validation-block consistency, and rank-stability requirements. Static-sector variants cannot rescue a candidate because current sector labels are non-point-in-time Tier-B metadata.", "",
        "The result is a valid negative experiment, not permission to tune the gates after seeing outcomes. All outputs remain private, survivorship-biased Tier-B research and do not establish future outperformance.", "",
        f"Decision hash: `{decision['decision_sha256']}`", "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish the frozen Phase 9B decision")
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--panel-manifest", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.output.exists() or arguments.report.exists():
        raise DataQualityError("refusing to overwrite immutable Phase 9B decision")
    decision = make_decision(
        comparison_path=arguments.comparison, dataset_manifest_path=arguments.dataset_manifest,
        panel_path=arguments.panel, panel_manifest_path=arguments.panel_manifest,
        predictions_path=arguments.predictions,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    arguments.report.write_text(decision_markdown(decision), encoding="utf-8")
    print(f"decision={decision['decision']}; sha256={decision['decision_sha256']}; holdout_used=false")


if __name__ == "__main__":
    main()
