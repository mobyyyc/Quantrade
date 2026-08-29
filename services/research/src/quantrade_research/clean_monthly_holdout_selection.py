"""Freeze clean-model monthly holdout selections before any return is read."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import date
from hashlib import sha256
import json
import math
from pathlib import Path

from .clean_monthly_baseline_panel import FEATURES, HOLDOUT_END, HOLDOUT_START, PANEL_KEY, PANEL_VERSION
from .quality import DataQualityError


PORTFOLIO_SIZE = 20


def _document(path: Path, label: str) -> tuple[dict[str, object], bytes]:
    try:
        payload = path.read_bytes()
        return json.loads(payload), payload
    except (OSError, json.JSONDecodeError) as error:
        raise DataQualityError(f"invalid {label}") from error


def freeze_clean_holdout_selection(
    *, panel: Path, panel_manifest: Path, model_artifact: Path, output: Path,
) -> dict[str, object]:
    if output.exists():
        raise DataQualityError("refusing to overwrite immutable clean holdout selection")
    panel_meta, panel_manifest_bytes = _document(panel_manifest, "clean panel manifest")
    model, model_bytes = _document(model_artifact, "clean model artifact")
    if panel_meta.get("panel_key") != PANEL_KEY or panel_meta.get("panel_version") != PANEL_VERSION:
        raise DataQualityError("unexpected clean panel version")
    panel_hash = sha256(panel.read_bytes()).hexdigest()
    if panel_hash != panel_meta.get("content_sha256"):
        raise DataQualityError("clean holdout panel does not match its manifest")
    try:
        source_panel_hash = model["source_dataset"]["source_panel_sha256"]  # type: ignore[index]
        holdout_used = model["holdout_used"]
        holdout_evaluated = model["holdout_evaluated"]
        columns = tuple(str(value) for value in model["feature_columns"])
        means = tuple(float(value) for value in model["feature_means"])
        scales = tuple(float(value) for value in model["feature_scales"])
        coefficients = tuple(float(value) for value in model["coefficients"])
        intercept = float(model["target_mean"])
    except (KeyError, TypeError, ValueError) as error:
        raise DataQualityError("clean model has an invalid inference schema") from error
    if source_panel_hash != panel_hash:
        raise DataQualityError("clean model and holdout panel do not share the same feature source")
    if holdout_used is not False or holdout_evaluated is not False:
        raise DataQualityError("clean model is not holdout-naive")
    expected_columns = tuple(f"{feature}_percentile" for feature in FEATURES)
    if columns != expected_columns or not (len(columns) == len(means) == len(scales) == len(coefficients)):
        raise DataQualityError("clean model feature schema does not match the clean panel")
    if any(scale <= 0 for scale in scales) or not all(math.isfinite(value) for value in (*means, *scales, *coefficients, intercept)):
        raise DataQualityError("clean model has invalid parameters")
    grouped: dict[date, list[dict[str, object]]] = defaultdict(list)
    with panel.open("r", encoding="utf-8", newline="") as handle:
        for line, row in enumerate(csv.DictReader(handle), start=2):
            formation = date.fromisoformat(row["formation_date"])
            if row["partition"] != "holdout":
                continue
            if not HOLDOUT_START <= formation <= HOLDOUT_END:
                raise DataQualityError(f"holdout panel row {line} is outside the locked period")
            if not row["baseline_rank"] or any(not row[feature] for feature in FEATURES):
                continue
            values = tuple(float(row[feature]) for feature in FEATURES)
            prediction = intercept + sum(
                coefficient * ((value - mean) / scale)
                for value, mean, scale, coefficient in zip(values, means, scales, coefficients)
            )
            grouped[formation].append({
                "security_id": row["security_id"], "ticker": row["ticker"],
                "baseline_rank": int(row["baseline_rank"]),
                "predicted_relative_return": prediction,
            })
    formations = []
    for formation in sorted(grouped):
        rows = grouped[formation]
        if len(rows) < PORTFOLIO_SIZE:
            raise DataQualityError(f"clean holdout formation {formation} has fewer than 20 eligible names")
        baseline = sorted(rows, key=lambda row: (row["baseline_rank"], row["security_id"]))[:PORTFOLIO_SIZE]
        candidate = sorted(rows, key=lambda row: (-row["predicted_relative_return"], row["security_id"]))[:PORTFOLIO_SIZE]
        formations.append({
            "formation_date": formation.isoformat(), "shared_eligible_count": len(rows),
            "baseline": [
                {"security_id": row["security_id"], "ticker": row["ticker"], "baseline_rank": row["baseline_rank"]}
                for row in baseline
            ],
            "elastic_net": [
                {"security_id": row["security_id"], "ticker": row["ticker"],
                 "predicted_relative_return": row["predicted_relative_return"]}
                for row in candidate
            ],
        })
    if len(formations) != 12:
        raise DataQualityError(f"clean holdout requires 12 monthly formations, found {len(formations)}")
    result = {
        "status": "selection_manifest_prepared", "holdout_performance_evaluated": False,
        "model_card": model["model_version"], "portfolio_size": PORTFOLIO_SIZE,
        "holdout": {"start_date": HOLDOUT_START.isoformat(), "end_date": HOLDOUT_END.isoformat()},
        "ranking_tie_break": "ascending stable security_id",
        "source_panel_sha256": panel_hash,
        "source_panel_manifest_sha256": sha256(panel_manifest_bytes).hexdigest(),
        "source_model_artifact_sha256": sha256(model_bytes).hexdigest(),
        "formations": formations,
        "next_step": "Prepare fixed next-open execution periods, then evaluate this manifest without reranking.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze clean-model holdout selections without reading returns")
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--panel-manifest", type=Path, required=True)
    parser.add_argument("--model-artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm-locked-holdout", action="store_true")
    arguments = parser.parse_args()
    if not arguments.confirm_locked_holdout:
        raise DataQualityError("locked holdout selection requires --confirm-locked-holdout")
    result = freeze_clean_holdout_selection(
        panel=arguments.panel, panel_manifest=arguments.panel_manifest,
        model_artifact=arguments.model_artifact, output=arguments.output,
    )
    print(
        f"holdout_formations={len(result['formations'])}; model={result['model_card']}; "
        f"performance_evaluated=false"
    )


if __name__ == "__main__":
    main()
