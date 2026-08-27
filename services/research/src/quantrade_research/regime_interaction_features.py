"""Materialize the pre-registered SPY regime-interaction features without fitting."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from itertools import islice
import json
import os
from pathlib import Path
import tempfile
from typing import Sequence

import psycopg

from .config import Settings
from .historical_training_export import HOLDOUT_START
from .quality import DataQualityError
from .score_run import _dotenv_values


DATASET_KEY = "sp500_current_survivors_20d_regime_interactions"
DATASET_VERSION = "v1"
SOURCE_DATASET_KEY = "sp500_current_survivors_20d"
SOURCE_DATASET_VERSION = "v1"
LOOKBACK_SESSIONS = 60
CLIP_LIMIT = Decimal("0.30")
INTERACTION_COLUMNS = (
    "momentum_12_1_market_trend_interaction_v1",
    "relative_strength_6m_market_trend_interaction_v1",
)
FEATURE_DEFINITIONS = (
    {
        "key": INTERACTION_COLUMNS[0],
        "version": "v1",
        "formula": "(momentum_12_1_percentile - 0.5) * market_trend_60d",
        "market_trend_formula": "clip(SPY_close_t / SPY_close_t_minus_60_sessions - 1, -0.30, 0.30) / 0.30",
    },
    {
        "key": INTERACTION_COLUMNS[1],
        "version": "v1",
        "formula": "(relative_strength_6m_percentile - 0.5) * market_trend_60d",
        "market_trend_formula": "clip(SPY_close_t / SPY_close_t_minus_60_sessions - 1, -0.30, 0.30) / 0.30",
    },
)
FEATURE_DEFINITION_SHA256 = sha256(
    json.dumps(FEATURE_DEFINITIONS, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()


@dataclass(frozen=True, slots=True)
class BenchmarkBar:
    session_date: date
    close_price: Decimal
    available_at: datetime


@dataclass(frozen=True, slots=True)
class MarketTrendSignal:
    raw_return: Decimal
    normalized_signal: Decimal
    used_bars: tuple[BenchmarkBar, ...]


def _decimal(value: str, field: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except (InvalidOperation, TypeError) as error:
        raise DataQualityError(f"invalid {field}") from error
    if not parsed.is_finite():
        raise DataQualityError(f"non-finite {field}")
    return parsed


def calculate_market_trend_signal(
    *, score_date: date, decision_at: datetime, bars: Sequence[BenchmarkBar],
) -> MarketTrendSignal:
    """Calculate the frozen 60-session signal from bars public by decision time."""
    if decision_at.tzinfo is None or decision_at.utcoffset() is None:
        raise DataQualityError("decision timestamp must include a UTC offset")
    eligible = tuple(
        item for item in bars
        if item.session_date <= score_date and item.available_at <= decision_at
    )
    if len(eligible) < LOOKBACK_SESSIONS + 1:
        raise DataQualityError("insufficient_point_in_time_spy_history")
    window = eligible[-(LOOKBACK_SESSIONS + 1):]
    if window[-1].session_date != score_date:
        raise DataQualityError("missing_same_session_spy_close")
    if any(item.close_price <= 0 for item in window):
        raise DataQualityError("non_positive_spy_close")
    raw_return = window[-1].close_price / window[0].close_price - Decimal("1")
    clipped = min(CLIP_LIMIT, max(-CLIP_LIMIT, raw_return))
    return MarketTrendSignal(raw_return, clipped / CLIP_LIMIT, window)


def calculate_interactions(
    momentum_percentile: Decimal,
    relative_strength_percentile: Decimal,
    market_signal: Decimal,
) -> tuple[Decimal, Decimal]:
    for name, value in (
        ("momentum percentile", momentum_percentile),
        ("relative-strength percentile", relative_strength_percentile),
    ):
        if not value.is_finite() or value < 0 or value > 1:
            raise DataQualityError(f"{name} must be finite and between zero and one")
    if not market_signal.is_finite() or market_signal < -1 or market_signal > 1:
        raise DataQualityError("market signal must be finite and between minus one and one")
    center = Decimal("0.5")
    return (
        (momentum_percentile - center) * market_signal,
        (relative_strength_percentile - center) * market_signal,
    )


def load_benchmark_bars(database_url: str, through_date: date) -> tuple[BenchmarkBar, ...]:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT session_date, close_price, available_at
               FROM quantrade.benchmark_daily_price_bars
               WHERE benchmark_ticker = 'SPY'
                 AND session = 'regular'
                 AND adjustment_basis = 'split_adjusted'
                 AND session_date <= %s
               ORDER BY session_date ASC""",
            (through_date,),
        )
        bars = tuple(BenchmarkBar(item[0], Decimal(item[1]), item[2]) for item in cursor.fetchall())
    if not bars:
        raise DataQualityError("SPY split-adjusted history is unavailable")
    dates = [item.session_date for item in bars]
    if len(dates) != len(set(dates)):
        raise DataQualityError("SPY history contains duplicate session dates")
    return bars


def _validate_source(source: Path, manifest: Path) -> dict[str, object]:
    try:
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
        expected_hash = str(metadata["content_sha256"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid source training-dataset manifest") from error
    if sha256(source.read_bytes()).hexdigest() != expected_hash:
        raise DataQualityError("source training dataset does not match its immutable manifest")
    if (
        metadata.get("dataset_key") != SOURCE_DATASET_KEY
        or metadata.get("dataset_version") != SOURCE_DATASET_VERSION
    ):
        raise DataQualityError("regime interactions require the frozen Tier-B source dataset v1")
    if not isinstance(metadata.get("development_row_count"), int) or metadata["development_row_count"] <= 0:
        raise DataQualityError("source manifest lacks a valid development row count")
    return metadata


def _source_identity(
    source: Path, expected_development_rows: int,
) -> tuple[dict[date, datetime], int, str, tuple[str, ...]]:
    decisions: dict[date, datetime] = {}
    development_rows = 0
    registry_hashes: set[str] = set()
    with source.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "partition", "score_date", "security_id", "decision_at", "feature_registry_hash",
            "momentum_12_1_percentile", "relative_strength_6m_percentile",
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise DataQualityError("source training dataset lacks regime-interaction inputs")
        fieldnames = tuple(reader.fieldnames)
        seen: set[tuple[date, str]] = set()
        for line_number, row in enumerate(islice(reader, expected_development_rows), start=2):
            if row.get("partition") != "development":
                raise DataQualityError("source manifest development boundary is invalid")
            try:
                score_date = date.fromisoformat(row["score_date"])
                decision_at = datetime.fromisoformat(row["decision_at"])
            except (KeyError, TypeError, ValueError) as error:
                raise DataQualityError(f"invalid source identity at line {line_number}") from error
            if score_date >= HOLDOUT_START:
                raise DataQualityError("development source row reaches the locked holdout")
            if decision_at.tzinfo is None or decision_at.utcoffset() is None:
                raise DataQualityError("source decision timestamp lacks a UTC offset")
            prior_decision = decisions.setdefault(score_date, decision_at)
            if prior_decision != decision_at:
                raise DataQualityError(f"inconsistent decision timestamp for {score_date}")
            identity = (score_date, row["security_id"])
            if identity in seen:
                raise DataQualityError(f"duplicate source training row: {identity}")
            seen.add(identity)
            registry_hashes.add(row["feature_registry_hash"])
            development_rows += 1
    if not decisions or not development_rows:
        raise DataQualityError("source training dataset has no development rows")
    if development_rows != expected_development_rows:
        raise DataQualityError("source dataset ended before its declared development boundary")
    if len(registry_hashes) != 1 or len(next(iter(registry_hashes))) != 64:
        raise DataQualityError("source development rows do not share one valid feature registry")
    return decisions, development_rows, registry_hashes.pop(), fieldnames


def _regime(raw_return: Decimal) -> str:
    if raw_return <= Decimal("-0.05"):
        return "bearish"
    if raw_return >= Decimal("0.05"):
        return "bullish"
    return "range_bound"


def materialize_regime_interaction_dataset(
    *, source: Path, source_manifest: Path, destination: Path, bars: Sequence[BenchmarkBar],
) -> dict[str, object]:
    """Write a development-only audited feature dataset; never fit a model."""
    source_metadata = _validate_source(source, source_manifest)
    if destination.exists():
        raise DataQualityError(f"refusing to overwrite immutable regime dataset: {destination}")
    expected_rows = int(source_metadata["development_row_count"])
    decisions, development_rows, base_registry_hash, source_fields = _source_identity(
        source, expected_rows,
    )
    ordered_bars = tuple(sorted(bars, key=lambda item: (item.session_date, item.available_at)))
    if len({item.session_date for item in ordered_bars}) != len(ordered_bars):
        raise DataQualityError("SPY history contains duplicate session dates")

    signals: dict[date, MarketTrendSignal] = {}
    excluded_dates: Counter[str] = Counter()
    used_bars: set[BenchmarkBar] = set()
    for score_date, decision_at in sorted(decisions.items()):
        try:
            signal = calculate_market_trend_signal(
                score_date=score_date, decision_at=decision_at, bars=ordered_bars,
            )
        except DataQualityError as error:
            excluded_dates[str(error)] += 1
            continue
        signals[score_date] = signal
        used_bars.update(signal.used_bars)

    destination.parent.mkdir(parents=True, exist_ok=True)
    source_by_date: Counter[date] = Counter()
    output_by_date: Counter[date] = Counter()
    exclusions: Counter[str] = Counter()
    interaction_min = [Decimal("Infinity"), Decimal("Infinity")]
    interaction_max = [Decimal("-Infinity"), Decimal("-Infinity")]
    written = 0
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", delete=False,
            dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp",
        ) as output:
            temporary_path = Path(output.name)
            writer = csv.DictWriter(
                output, fieldnames=[*source_fields, *INTERACTION_COLUMNS], lineterminator="\n",
            )
            writer.writeheader()
            with source.open("r", encoding="utf-8", newline="") as source_handle:
                reader = csv.DictReader(source_handle)
                for line_number, row in enumerate(islice(reader, development_rows), start=2):
                    if row.get("partition") != "development":
                        raise DataQualityError("source manifest development boundary is invalid")
                    score_date = date.fromisoformat(row["score_date"])
                    source_by_date[score_date] += 1
                    signal = signals.get(score_date)
                    if signal is None:
                        exclusions["missing_point_in_time_spy_signal"] += 1
                        continue
                    try:
                        interactions = calculate_interactions(
                            _decimal(row["momentum_12_1_percentile"], "momentum percentile"),
                            _decimal(row["relative_strength_6m_percentile"], "relative-strength percentile"),
                            signal.normalized_signal,
                        )
                    except DataQualityError as error:
                        exclusions[str(error)] += 1
                        continue
                    for index, (column, value) in enumerate(zip(INTERACTION_COLUMNS, interactions)):
                        row[column] = format(value, "f")
                        interaction_min[index] = min(interaction_min[index], value)
                        interaction_max[index] = max(interaction_max[index], value)
                    writer.writerow(row)
                    output_by_date[score_date] += 1
                    written += 1
        if not written:
            raise DataQualityError("regime-interaction dataset has no complete rows")
        coverage = Decimal(written) / Decimal(development_rows)
        date_coverages = {
            score_date: Decimal(output_by_date[score_date]) / Decimal(count)
            for score_date, count in source_by_date.items()
        }
        if coverage < Decimal("0.90"):
            raise DataQualityError(f"regime-interaction coverage is below 90%: {coverage}")
        temporary_path.replace(destination)
        temporary_path = None
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    canonical_bars = "\n".join(
        f"{item.session_date.isoformat()}|{item.close_price}|{item.available_at.isoformat()}"
        for item in sorted(used_bars, key=lambda value: (value.session_date, value.available_at))
    )
    regime_counts = Counter(_regime(item.raw_return) for item in signals.values())
    combined_registry_hash = sha256(
        f"{base_registry_hash}|{FEATURE_DEFINITION_SHA256}".encode("utf-8")
    ).hexdigest()
    return {
        "dataset_key": DATASET_KEY,
        "dataset_version": DATASET_VERSION,
        "status": "feature_materialization_complete",
        "development_only": True,
        "holdout_used": False,
        "model_fitted": False,
        "data_capability_tier": "B",
        "source_dataset_sha256": source_metadata["content_sha256"],
        "source_development_rows": development_rows,
        "materialized_rows": written,
        "coverage": str(coverage),
        "formation_count": len(source_by_date),
        "materialized_formation_count": len(output_by_date),
        "minimum_formation_coverage": str(min(date_coverages.values())),
        "date_start": min(output_by_date).isoformat(),
        "date_end": max(output_by_date).isoformat(),
        "interaction_columns": list(INTERACTION_COLUMNS),
        "interaction_ranges": {
            column: {"minimum": str(interaction_min[index]), "maximum": str(interaction_max[index])}
            for index, column in enumerate(INTERACTION_COLUMNS)
        },
        "market_signal": {
            "lookback_sessions": LOOKBACK_SESSIONS,
            "clip_limit": str(CLIP_LIMIT),
            "available_at_rule": "SPY bars must be public by the dated 8:00 p.m. Toronto decision",
            "regime_formation_counts": dict(sorted(regime_counts.items())),
            "excluded_formation_counts": dict(sorted(excluded_dates.items())),
        },
        "point_in_time_violations": 0,
        "exclusions": dict(sorted(exclusions.items())),
        "base_feature_registry_hash": base_registry_hash,
        "interaction_definition_sha256": FEATURE_DEFINITION_SHA256,
        "combined_feature_registry_hash": combined_registry_hash,
        "benchmark_lineage_sha256": sha256(canonical_bars.encode("utf-8")).hexdigest(),
        "content_sha256": sha256(destination.read_bytes()).hexdigest(),
        "limitations": source_metadata["limitations"],
    }


def render_audit_report(metadata: dict[str, object]) -> str:
    signal = metadata["market_signal"]
    assert isinstance(signal, dict)
    ranges = metadata["interaction_ranges"]
    assert isinstance(ranges, dict)
    regime_counts = signal["regime_formation_counts"]
    assert isinstance(regime_counts, dict)
    lines = [
        "# Regime-Interaction Feature Audit",
        "",
        "## Decision",
        "",
        "P9A.3 passes. The two pre-registered SPY regime-interaction features were",
        "materialized on development data only. No challenger was fitted, the locked",
        "holdout was not opened, and the active model was not changed.",
        "",
        "## Coverage",
        "",
        f"- Rows: {int(metadata['materialized_rows']):,} of {int(metadata['source_development_rows']):,}",
        f"- Aggregate coverage: {Decimal(str(metadata['coverage'])):.2%}",
        f"- Minimum formation coverage: {Decimal(str(metadata['minimum_formation_coverage'])):.2%}",
        f"- Formations: {metadata['materialized_formation_count']} of {metadata['formation_count']}",
        f"- Date span: {metadata['date_start']} through {metadata['date_end']}",
        f"- Point-in-time violations: {metadata['point_in_time_violations']}",
        "",
        "## Market regimes",
        "",
        f"- Bearish formations: {regime_counts.get('bearish', 0)}",
        f"- Range-bound formations: {regime_counts.get('range_bound', 0)}",
        f"- Bullish formations: {regime_counts.get('bullish', 0)}",
        "",
        "## Feature ranges",
        "",
    ]
    for column in INTERACTION_COLUMNS:
        item = ranges[column]
        assert isinstance(item, dict)
        lines.append(f"- `{column}`: {item['minimum']} to {item['maximum']}")
    lines.extend([
        "",
        "## Provenance",
        "",
        f"- Source dataset SHA-256: `{metadata['source_dataset_sha256']}`",
        f"- Interaction-definition SHA-256: `{metadata['interaction_definition_sha256']}`",
        f"- Combined feature-registry SHA-256: `{metadata['combined_feature_registry_hash']}`",
        f"- SPY lineage SHA-256: `{metadata['benchmark_lineage_sha256']}`",
        f"- Materialized dataset SHA-256: `{metadata['content_sha256']}`",
        "",
        "The dataset remains Tier-B survivorship-biased private research. Passing this",
        "audit authorizes only the pre-registered development comparison in P9A.4.",
        "It does not establish that the challenger is useful or eligible for freezing.",
        "",
    ])
    return "\n".join(lines)


def _settings(env_file: Path) -> Settings:
    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize and audit pre-registered SPY interactions")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    manifest = arguments.output.with_suffix(".json")
    for path in (arguments.output, manifest, arguments.report):
        if path.exists():
            raise DataQualityError(f"refusing to overwrite immutable output: {path}")
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    source_metadata = _validate_source(arguments.source, arguments.source_manifest)
    decisions, _, _, _ = _source_identity(
        arguments.source, int(source_metadata["development_row_count"]),
    )
    bars = load_benchmark_bars(settings.database_url, max(decisions))
    metadata = materialize_regime_interaction_dataset(
        source=arguments.source,
        source_manifest=arguments.source_manifest,
        destination=arguments.output,
        bars=bars,
    )
    manifest.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    arguments.report.write_text(render_audit_report(metadata), encoding="utf-8")
    print(
        f"rows={metadata['materialized_rows']}; coverage={metadata['coverage']}; "
        "point_in_time_violations=0; model_fitted=false; holdout_used=false"
    )


if __name__ == "__main__":
    main()
