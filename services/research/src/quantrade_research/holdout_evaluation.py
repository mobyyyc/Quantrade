"""Fail-closed preparation of the one-time locked-holdout comparison.

This module deliberately separates ranking selection from the later execution
and cost calculation.  Once a confirmed selection manifest is written, the
portfolio engine must consume it as-is rather than re-rank after any result is
visible.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date
import json
import math
from pathlib import Path
from typing import Iterable

from .historical_training_export import HOLDOUT_END, HOLDOUT_START
from .quality import DataQualityError
from .regularized_training import FEATURE_COLUMNS, LinearModel


PORTFOLIO_SIZE = 20
MODEL_CARD_KEY = "tier_b_regularized_linear_development_v1"


@dataclass(frozen=True, slots=True)
class HoldoutRow:
    score_date: date
    security_id: str
    ticker: str
    baseline_rank: int
    features: tuple[float, ...]


def require_locked_holdout_confirmation(confirmed: bool) -> None:
    if not confirmed:
        raise DataQualityError(
            "locked holdout is protected; rerun only with --confirm-locked-holdout after explicit approval"
        )


def load_frozen_model(path: Path) -> LinearModel:
    """Load the development-selected elastic-net parameters, never refitting them."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if document["holdout_used"] is not False:
            raise DataQualityError("frozen model artifact is not development-only")
        model = document["final_development_model"]
        if model["family"] != "elastic_net" or model["l1_penalty"] != 0.001 or model["l2_penalty"] != 0.01:
            raise DataQualityError("frozen candidate parameters do not match the pre-registered model card")
        means = tuple(float(value) for value in model["feature_means"])
        scales = tuple(float(value) for value in model["feature_scales"])
        coefficients = tuple(float(value) for value in model["coefficients"])
        target_mean = float(model["target_mean"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid frozen development model artifact") from error
    if not (len(means) == len(scales) == len(coefficients) == len(FEATURE_COLUMNS)):
        raise DataQualityError("frozen model feature shape does not match the registered schema")
    if any(not math.isfinite(value) or value <= 0 for value in scales):
        raise DataQualityError("frozen model has invalid feature scales")
    return LinearModel("elastic_net", 0.001, 0.01, means, scales, target_mean, coefficients)


def load_holdout_rows(path: Path) -> tuple[HoldoutRow, ...]:
    """Read strictly the pre-locked holdout partition and reject mixed rows."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"partition", "score_date", "security_id", "ticker", "baseline_rank", *FEATURE_COLUMNS}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise DataQualityError("training CSV does not have the required holdout schema")
        rows: list[HoldoutRow] = []
        for line_number, row in enumerate(reader, start=2):
            if row.get("partition") != "holdout":
                continue
            try:
                score_date = date.fromisoformat(str(row["score_date"]))
                values = tuple(float(row[column]) for column in FEATURE_COLUMNS)
                entry = HoldoutRow(score_date, str(row["security_id"]), str(row["ticker"]), int(row["baseline_rank"]), values)
            except (KeyError, TypeError, ValueError) as error:
                raise DataQualityError(f"invalid holdout CSV line {line_number}") from error
            if not HOLDOUT_START <= entry.score_date <= HOLDOUT_END:
                raise DataQualityError(f"holdout CSV line {line_number} is outside the locked date range")
            if entry.baseline_rank < 1 or not all(math.isfinite(value) for value in entry.features):
                raise DataQualityError(f"holdout CSV line {line_number} has invalid ranking inputs")
            rows.append(entry)
    if not rows:
        raise DataQualityError("training CSV contains no locked-holdout rows")
    return tuple(rows)


def _formation_rows(rows: Iterable[HoldoutRow]) -> tuple[tuple[date, tuple[HoldoutRow, ...]], ...]:
    grouped: dict[tuple[int, int], list[HoldoutRow]] = {}
    for row in rows:
        grouped.setdefault((row.score_date.year, row.score_date.month), []).append(row)
    formations: list[tuple[date, tuple[HoldoutRow, ...]]] = []
    for _, month_rows in sorted(grouped.items()):
        formation_date = max(row.score_date for row in month_rows)
        candidates = tuple(row for row in month_rows if row.score_date == formation_date)
        if len({row.security_id for row in candidates}) != len(candidates):
            raise DataQualityError(f"duplicate security in holdout formation {formation_date}")
        formations.append((formation_date, candidates))
    return tuple(formations)


def build_selection_manifest(rows: Iterable[HoldoutRow], model: LinearModel) -> dict[str, object]:
    """Create deterministic shared-universe selections without computing returns."""
    formations: list[dict[str, object]] = []
    for formation_date, candidates in _formation_rows(rows):
        if len(candidates) < PORTFOLIO_SIZE:
            raise DataQualityError(f"formation {formation_date} has fewer than {PORTFOLIO_SIZE} shared eligible securities")
        baseline = sorted(candidates, key=lambda row: (row.baseline_rank, row.security_id))[:PORTFOLIO_SIZE]
        scored = [(row, model.predict(row.features)) for row in candidates]
        candidate = sorted(scored, key=lambda item: (-item[1], item[0].security_id))[:PORTFOLIO_SIZE]
        formations.append({
            "formation_date": formation_date.isoformat(),
            "shared_eligible_count": len(candidates),
            "baseline": [{"security_id": row.security_id, "ticker": row.ticker, "baseline_rank": row.baseline_rank} for row in baseline],
            "elastic_net": [
                {"security_id": row.security_id, "ticker": row.ticker, "predicted_relative_return": prediction}
                for row, prediction in candidate
            ],
        })
    if not formations:
        raise DataQualityError("holdout selection has no formation dates")
    return {
        "status": "selection_manifest_prepared",
        "model_card": MODEL_CARD_KEY,
        "holdout": {"start_date": HOLDOUT_START.isoformat(), "end_date": HOLDOUT_END.isoformat()},
        "portfolio_size": PORTFOLIO_SIZE,
        "ranking_tie_break": "ascending stable security_id",
        "holdout_performance_evaluated": False,
        "formations": formations,
        "next_step": "Run the separately approved execution-and-cost evaluator against this immutable selection manifest exactly once.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the one-time locked-holdout baseline versus elastic-net selection manifest")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--model-artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm-locked-holdout", action="store_true")
    arguments = parser.parse_args()
    require_locked_holdout_confirmation(arguments.confirm_locked_holdout)
    if arguments.output.exists():
        raise DataQualityError(f"refusing to overwrite immutable holdout selection manifest: {arguments.output}")
    model = load_frozen_model(arguments.model_artifact)
    manifest = build_selection_manifest(load_holdout_rows(arguments.input), model)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"holdout_formations={len(manifest['formations'])}; performance_evaluated=false")


if __name__ == "__main__":
    main()
