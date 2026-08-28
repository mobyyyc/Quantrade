"""Build the label-safe monthly Phase 9B model dataset and robustness ranks."""

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

from .monthly_feature_panel import FEATURES, HOLDOUT_START, PANEL_KEY, PANEL_VERSION
from .quality import DataQualityError
from .score_run import _dotenv_values


DATASET_KEY = "tier_b_monthly_model_development"
DATASET_VERSION = "v1"
BASE_FEATURES = (
    "momentum_12_1", "relative_strength_6m", "trailing_volatility_60d",
    "median_dollar_volume_20d", "earnings_yield_ttm", "return_on_assets_ttm",
)
MARKET_FEATURES = tuple(f"{item}_market" for item in FEATURES)
SECTOR_FEATURES = tuple(f"{item}_static_sector" for item in FEATURES)
HIGHER_IS_BETTER = {item: False for item in FEATURES}


def _validate_panel(panel: Path, manifest: Path) -> dict[str, object]:
    try:
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid monthly feature-panel manifest") from error
    if metadata.get("panel_key") != PANEL_KEY or metadata.get("panel_version") != PANEL_VERSION:
        raise DataQualityError("unexpected monthly feature panel version")
    if sha256(panel.read_bytes()).hexdigest() != metadata.get("content_sha256"):
        raise DataQualityError("monthly feature panel does not match its manifest")
    if metadata.get("holdout_used") is not False:
        raise DataQualityError("monthly feature panel must be development-only")
    return metadata


def centered_percentiles(values: dict[str, Decimal], *, higher_is_better: bool) -> dict[str, Decimal]:
    ordered = sorted(values.items(), key=lambda item: (item[1], item[0]))
    if len(ordered) < 2:
        return {}
    denominator = Decimal(len(ordered) - 1)
    output: dict[str, Decimal] = {}
    index = 0
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[index][1]:
            end += 1
        percentile = Decimal(index + end) / Decimal("2") / denominator
        if not higher_is_better:
            percentile = Decimal("1") - percentile
        for security_id, _ in ordered[index:end + 1]:
            output[security_id] = percentile - Decimal("0.5")
        index = end + 1
    return output


def _load_panel(panel: Path):
    raw: dict[date, dict[str, dict[str, Decimal]]] = defaultdict(lambda: defaultdict(dict))
    row_hashes: dict[tuple[date, str], str] = {}
    decisions: dict[date, str] = {}
    with panel.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            formation = date.fromisoformat(row["formation_date"])
            security_id = row["security_id"]
            decisions[formation] = row["decision_at"]
            hashes: list[str] = []
            for feature in FEATURES:
                hashes.append(row[f"{feature}_sha256"])
                if row[feature]:
                    raw[formation][feature][security_id] = Decimal(row[feature])
            row_hashes[(formation, security_id)] = sha256("|".join(hashes).encode()).hexdigest()
    return raw, row_hashes, decisions


def _load_database_inputs(database_url: str, formation_dates: tuple[date, ...]):
    import psycopg

    baseline: dict[date, dict[str, dict[str, Decimal]]] = defaultdict(lambda: defaultdict(dict))
    sectors: dict[str, str] = {}
    security_opens: dict[tuple[str, date], Decimal] = {}
    benchmark: dict[date, tuple[Decimal, Decimal]] = {}
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT DISTINCT ON (snapshot.score_date,snapshot.security_id,explanation.feature_key)
                      snapshot.score_date,snapshot.security_id::text,explanation.feature_key,explanation.percentile
               FROM quantrade.score_snapshots snapshot
               JOIN quantrade.score_explanations explanation USING(score_snapshot_id)
               WHERE snapshot.score_date=ANY(%s::date[]) AND snapshot.eligible
                 AND explanation.feature_key=ANY(%s) AND explanation.percentile IS NOT NULL
               ORDER BY snapshot.score_date,snapshot.security_id,explanation.feature_key,snapshot.created_at DESC""",
            (list(formation_dates), list(BASE_FEATURES)),
        )
        for formation, security_id, feature, percentile in cursor:
            baseline[formation][feature][security_id] = Decimal(percentile) - Decimal("0.5")
        cursor.execute(
            """SELECT DISTINCT ON (security_id) security_id::text,sector_code
               FROM quantrade.sector_classifications
               ORDER BY security_id,as_of_date DESC,available_at DESC"""
        )
        sectors.update((str(row[0]), str(row[1])) for row in cursor)
        cursor.execute(
            """SELECT session_date,open_price,close_price
               FROM quantrade.benchmark_daily_price_bars
               WHERE benchmark_ticker='SPY' AND session='regular' AND adjustment_basis='split_adjusted'
                 AND session_date <= %s ORDER BY session_date""",
            (HOLDOUT_START,),
        )
        benchmark.update((row[0], (Decimal(row[1]), Decimal(row[2]))) for row in cursor)
        sessions = sorted(benchmark)
        label_dates: set[date] = set()
        windows: dict[date, tuple[date, date]] = {}
        for formation in formation_dates:
            future = [item for item in sessions if item > formation]
            if len(future) < 21:
                continue
            execution, outcome = future[0], future[20]
            if outcome >= HOLDOUT_START:
                continue
            windows[formation] = execution, outcome
            label_dates.update((execution, outcome))
        cursor.execute(
            """SELECT security_id::text,session_date,open_price
               FROM quantrade.daily_price_bars
               WHERE session='regular' AND adjustment_basis='split_adjusted'
                 AND session_date=ANY(%s::date[])""",
            (list(sorted(label_dates)),),
        )
        security_opens.update(((str(row[0]), row[1]), Decimal(row[2])) for row in cursor)
    return baseline, sectors, benchmark, windows, security_opens


def build_monthly_model_dataset(
    *, database_url: str, panel: Path, panel_manifest: Path, destination: Path,
) -> dict[str, object]:
    panel_metadata = _validate_panel(panel, panel_manifest)
    if destination.exists() or destination.with_suffix(".json").exists():
        raise DataQualityError("refusing to overwrite immutable monthly model dataset")
    raw, row_hashes, decisions = _load_panel(panel)
    formation_dates = tuple(sorted(raw))
    baseline, sectors, benchmark, windows, security_opens = _load_database_inputs(database_url, formation_dates)
    market_ranks: dict[date, dict[str, dict[str, Decimal]]] = defaultdict(dict)
    sector_ranks: dict[date, dict[str, dict[str, Decimal]]] = defaultdict(dict)
    for formation in formation_dates:
        for feature in FEATURES:
            values = raw[formation][feature]
            market_ranks[formation][feature] = centered_percentiles(
                values, higher_is_better=HIGHER_IS_BETTER[feature],
            )
            grouped: dict[str, dict[str, Decimal]] = defaultdict(dict)
            for security_id, value in values.items():
                if security_id in sectors:
                    grouped[sectors[security_id]][security_id] = value
            ranked: dict[str, Decimal] = {}
            for group in grouped.values():
                ranked.update(centered_percentiles(group, higher_is_better=HIGHER_IS_BETTER[feature]))
            sector_ranks[formation][feature] = ranked
    destination.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "partition", "formation_date", "decision_at", "security_id", "sector_code",
        "execution_date", "outcome_date", "security_return", "benchmark_return",
        "benchmark_relative_return", "formation_weight", "spy_trend_60d", "spy_volatility_60d",
        *BASE_FEATURES, *MARKET_FEATURES, *SECTOR_FEATURES, "panel_row_sha256",
    ]
    exclusions = Counter()
    rows = 0
    included_by_date = Counter()
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        staged: dict[date, list[dict[str, str]]] = defaultdict(list)
        benchmark_dates = sorted(benchmark)
        for formation in formation_dates:
            if formation not in windows:
                exclusions["incomplete_label_window"] += len(row_hashes) // len(formation_dates)
                continue
            execution, outcome = windows[formation]
            benchmark_entry, benchmark_exit = benchmark[execution][0], benchmark[outcome][0]
            benchmark_return = benchmark_exit / benchmark_entry - Decimal("1")
            history = [benchmark[item][1] for item in benchmark_dates if item <= formation]
            if len(history) < 61:
                exclusions["insufficient_spy_regime_history"] += len(row_hashes) // len(formation_dates)
                continue
            spy_trend = history[-1] / history[-61] - Decimal("1")
            returns = [float(history[index] / history[index - 1] - 1) for index in range(len(history) - 59, len(history))]
            mean_return = sum(returns) / len(returns)
            spy_volatility = Decimal(str(math.sqrt(sum((item - mean_return) ** 2 for item in returns) / len(returns))))
            security_ids = sorted(security for day, security in row_hashes if day == formation)
            for security_id in security_ids:
                active = baseline.get(formation, {})
                if any(security_id not in active.get(feature, {}) for feature in BASE_FEATURES):
                    exclusions["missing_active_feature"] += 1
                    continue
                if any(security_id not in market_ranks[formation][feature] for feature in FEATURES):
                    exclusions["missing_candidate_feature"] += 1
                    continue
                if any(security_id not in sector_ranks[formation][feature] for feature in FEATURES):
                    exclusions["missing_sector_robustness_rank"] += 1
                    continue
                entry = security_opens.get((security_id, execution))
                exit_value = security_opens.get((security_id, outcome))
                if entry is None or exit_value is None or entry <= 0 or exit_value <= 0:
                    exclusions["missing_next_open_label"] += 1
                    continue
                security_return = exit_value / entry - Decimal("1")
                row = {
                    "partition": "development", "formation_date": formation.isoformat(),
                    "decision_at": decisions[formation], "security_id": security_id,
                    "sector_code": sectors[security_id], "execution_date": execution.isoformat(),
                    "outcome_date": outcome.isoformat(), "security_return": str(security_return),
                    "benchmark_return": str(benchmark_return),
                    "benchmark_relative_return": str(security_return - benchmark_return),
                    "spy_trend_60d": str(spy_trend), "spy_volatility_60d": str(spy_volatility),
                    "panel_row_sha256": row_hashes[(formation, security_id)],
                }
                row.update((feature, str(active[feature][security_id])) for feature in BASE_FEATURES)
                row.update((f"{feature}_market", str(market_ranks[formation][feature][security_id])) for feature in FEATURES)
                row.update((f"{feature}_static_sector", str(sector_ranks[formation][feature][security_id])) for feature in FEATURES)
                staged[formation].append(row)
        for formation in sorted(staged):
            weight = Decimal("1") / Decimal(len(staged[formation]))
            for row in staged[formation]:
                row["formation_weight"] = str(weight)
                writer.writerow(row)
                rows += 1
            included_by_date[formation.isoformat()] = len(staged[formation])
    expected = len(formation_dates) * int(panel_metadata["security_count"])
    content_hash = sha256(destination.read_bytes()).hexdigest()
    metadata: dict[str, object] = {
        "dataset_key": DATASET_KEY, "dataset_version": DATASET_VERSION,
        "content_sha256": content_hash, "source_panel_sha256": panel_metadata["content_sha256"],
        "development_only": True, "holdout_used": False, "label_horizon_sessions": 20,
        "execution_convention": "next_regular_session_open_to_open_after_20_completed_sessions",
        "formation_count": len(included_by_date), "row_count": rows,
        "expected_panel_rows": expected, "common_sample_coverage": str(Decimal(rows) / Decimal(expected)),
        "included_by_date": dict(included_by_date), "exclusions": dict(sorted(exclusions.items())),
        "base_features": list(BASE_FEATURES), "candidate_market_features": list(MARKET_FEATURES),
        "candidate_static_sector_features": list(SECTOR_FEATURES),
        "transformations": {
            "primary": "market-wide centered percentile",
            "robustness_only": "static current-sector centered percentile",
        },
        "formation_weighting": "each formation sums to one",
        "limitations": panel_metadata["limitations"],
    }
    destination.with_suffix(".json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return metadata


def _settings(env_file: Path):
    from .config import Settings

    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Phase 9B monthly model dataset")
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--panel-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    metadata = build_monthly_model_dataset(
        database_url=settings.database_url, panel=arguments.panel,
        panel_manifest=arguments.panel_manifest, destination=arguments.output,
    )
    print(
        f"monthly_dataset_rows={metadata['row_count']}; formations={metadata['formation_count']}; "
        f"coverage={metadata['common_sample_coverage']}; sha256={metadata['content_sha256']}",
    )


if __name__ == "__main__":
    main()
