"""Create a holdout-safe development dataset from the clean baseline panel."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
import math
import os
from pathlib import Path

from .clean_monthly_baseline_panel import FEATURES, HOLDOUT_START, PANEL_KEY, PANEL_VERSION
from .monthly_model_comparison import Example
from .quality import DataQualityError
from .score_run import _dotenv_values


DATASET_KEY = "tier_b_clean_monthly_model_development"
DATASET_VERSION = "v1"


def _panel_metadata(panel: Path, manifest: Path) -> dict[str, object]:
    try:
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid clean baseline panel manifest") from error
    if metadata.get("panel_key") != PANEL_KEY or metadata.get("panel_version") != PANEL_VERSION:
        raise DataQualityError("unexpected clean baseline panel version")
    if sha256(panel.read_bytes()).hexdigest() != metadata.get("content_sha256"):
        raise DataQualityError("clean baseline panel does not match its manifest")
    if metadata.get("holdout_performance_evaluated") is not False:
        raise DataQualityError("clean baseline panel has exposed holdout performance")
    return metadata


def _load_panel(panel: Path):
    rows: dict[date, dict[str, dict[str, str]]] = defaultdict(dict)
    with panel.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"partition", "formation_date", "decision_at", "security_id", "sector_code", "row_sha256", *FEATURES}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise DataQualityError("clean baseline panel lacks required columns")
        for line, row in enumerate(reader, start=2):
            formation = date.fromisoformat(row["formation_date"])
            if row["partition"] != "development" or formation >= HOLDOUT_START:
                continue
            security_id = row["security_id"]
            if security_id in rows[formation]:
                raise DataQualityError(f"duplicate clean panel row at line {line}")
            rows[formation][security_id] = row
    if not rows:
        raise DataQualityError("clean baseline panel has no development rows")
    return rows


def _labels(database_url: str, formations: tuple[date, ...]):
    import psycopg

    windows: dict[date, tuple[date, date, Decimal]] = {}
    security_opens: dict[tuple[str, date], Decimal] = {}
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT session_date,open_price FROM quantrade.benchmark_daily_price_bars
               WHERE benchmark_ticker='SPY' AND session='regular' AND adjustment_basis='split_adjusted'
                 AND session_date < %s ORDER BY session_date""",
            (HOLDOUT_START,),
        )
        benchmark = {row[0]: Decimal(row[1]) for row in cursor.fetchall()}
        sessions = sorted(benchmark)
        label_dates: set[date] = set()
        for formation in formations:
            future = [item for item in sessions if item > formation]
            if len(future) < 21:
                continue
            execution, outcome = future[0], future[20]
            if outcome >= HOLDOUT_START:
                continue
            entry, exit_value = benchmark[execution], benchmark[outcome]
            windows[formation] = execution, outcome, exit_value / entry - Decimal("1")
            label_dates.update((execution, outcome))
        cursor.execute(
            """SELECT security_id::text,session_date,open_price
               FROM quantrade.daily_price_bars
               WHERE session='regular' AND adjustment_basis='split_adjusted'
                 AND session_date=ANY(%s::date[])""",
            (list(sorted(label_dates)),),
        )
        security_opens = {(str(row[0]), row[1]): Decimal(row[2]) for row in cursor.fetchall()}
    return windows, security_opens


def build_clean_monthly_model_dataset(
    *, database_url: str, panel: Path, panel_manifest: Path, destination: Path,
) -> dict[str, object]:
    metadata = _panel_metadata(panel, panel_manifest)
    manifest = destination.with_suffix(".json")
    if destination.exists() or manifest.exists():
        raise DataQualityError("refusing to overwrite immutable clean monthly model dataset")
    panel_rows = _load_panel(panel)
    formations = tuple(sorted(panel_rows))
    windows, opens = _labels(database_url, formations)
    fields = [
        "partition", "formation_date", "decision_at", "security_id", "sector_code",
        "execution_date", "outcome_date", "security_return", "benchmark_return",
        "benchmark_relative_return", "formation_weight", *FEATURES, "panel_row_sha256",
    ]
    staged: dict[date, list[dict[str, str]]] = defaultdict(list)
    exclusions = Counter()
    for formation in formations:
        if formation not in windows:
            exclusions["label_window_overlaps_holdout_or_incomplete"] += len(panel_rows[formation])
            continue
        execution, outcome, benchmark_return = windows[formation]
        for security_id, source in sorted(panel_rows[formation].items()):
            if any(not source[feature] for feature in FEATURES):
                exclusions["missing_clean_base_feature"] += 1
                continue
            entry, exit_value = opens.get((security_id, execution)), opens.get((security_id, outcome))
            if entry is None or exit_value is None or entry <= 0 or exit_value <= 0:
                exclusions["missing_next_open_label"] += 1
                continue
            security_return = exit_value / entry - Decimal("1")
            row = {
                "partition": "development", "formation_date": formation.isoformat(),
                "decision_at": source["decision_at"], "security_id": security_id,
                "sector_code": source["sector_code"], "execution_date": execution.isoformat(),
                "outcome_date": outcome.isoformat(), "security_return": str(security_return),
                "benchmark_return": str(benchmark_return),
                "benchmark_relative_return": str(security_return - benchmark_return),
                "panel_row_sha256": source["row_sha256"],
            }
            row.update((feature, source[feature]) for feature in FEATURES)
            staged[formation].append(row)
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    included = {}
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for formation in sorted(staged):
            weight = Decimal("1") / Decimal(len(staged[formation]))
            for row in staged[formation]:
                row["formation_weight"] = str(weight)
                writer.writerow(row)
                count += 1
            included[formation.isoformat()] = len(staged[formation])
    output = {
        "dataset_key": DATASET_KEY, "dataset_version": DATASET_VERSION,
        "content_sha256": sha256(destination.read_bytes()).hexdigest(),
        "source_panel_sha256": metadata["content_sha256"],
        "development_only": True, "holdout_used": False, "holdout_evaluated": False,
        "label_horizon_sessions": 20,
        "execution_convention": "next_regular_session_open_to_open_after_20_completed_sessions",
        "row_count": count, "formation_count": len(included), "included_by_date": included,
        "feature_columns": list(FEATURES), "feature_registry_hash": metadata["feature_registry_hash"],
        "sec_form_scope": metadata["sec_form_scope"], "exclusions": dict(sorted(exclusions.items())),
        "formation_weighting": "each formation sums to one", "limitations": metadata["limitations"],
    }
    manifest.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def load_clean_examples(dataset: Path, manifest: Path) -> tuple[tuple[Example, ...], dict[str, object]]:
    try:
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid clean monthly dataset manifest") from error
    if metadata.get("dataset_key") != DATASET_KEY or metadata.get("dataset_version") != DATASET_VERSION:
        raise DataQualityError("unexpected clean monthly dataset version")
    if metadata.get("development_only") is not True or metadata.get("holdout_used") is not False:
        raise DataQualityError("clean monthly dataset is not development-only")
    if sha256(dataset.read_bytes()).hexdigest() != metadata.get("content_sha256"):
        raise DataQualityError("clean monthly dataset does not match its manifest")
    examples: list[Example] = []
    seen = set()
    with dataset.open("r", encoding="utf-8", newline="") as handle:
        for line, row in enumerate(csv.DictReader(handle), start=2):
            try:
                formation = date.fromisoformat(row["formation_date"])
                identity = formation, row["security_id"]
                values = tuple(float(row[feature]) for feature in FEATURES)
                numeric = (*values, float(row["benchmark_relative_return"]), float(row["security_return"]),
                           float(row["benchmark_return"]), float(row["formation_weight"]))
            except (KeyError, TypeError, ValueError) as error:
                raise DataQualityError(f"invalid clean monthly dataset row {line}") from error
            if identity in seen or formation >= HOLDOUT_START or not all(math.isfinite(value) for value in numeric):
                raise DataQualityError(f"unsafe clean monthly dataset row {line}")
            seen.add(identity)
            examples.append(Example(
                formation, date.fromisoformat(row["outcome_date"]), row["security_id"], values, (), (),
                numeric[-4], numeric[-3], numeric[-2], numeric[-1], 0.0, 0.0,
            ))
    return tuple(sorted(examples, key=lambda item: (item.formation_date, item.security_id))), metadata


def _settings(env_file: Path):
    from .config import Settings

    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the clean holdout-safe monthly development dataset")
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--panel-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    result = build_clean_monthly_model_dataset(
        database_url=settings.database_url, panel=arguments.panel,
        panel_manifest=arguments.panel_manifest, destination=arguments.output,
    )
    print(
        f"clean_training_rows={result['row_count']}; formations={result['formation_count']}; "
        f"sha256={result['content_sha256']}; holdout_used=false"
    )


if __name__ == "__main__":
    main()
