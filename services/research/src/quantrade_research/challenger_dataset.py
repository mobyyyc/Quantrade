"""Build a development-only common-sample dataset for Phase 9 model comparisons."""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import csv
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path

from .candidate_feature_diagnostics import _reason
from .candidate_features import calculate_downside_volatility_60d, calculate_return_on_assets_change_yoy
from .features import FeatureRegistry, baseline_feature_registry, next_generation_candidate_registry
from .fundamentals import FundamentalFactObservation
from .historical_training_export import HOLDOUT_START
from .historical_replay import historical_decision_at
from .momentum import FeaturePriceObservation
from .quality import DataQualityError
from .score_run import _dotenv_values


DATASET_KEY = "sp500_current_survivors_20d_next_gen_common"
DATASET_VERSION = "v1"
ACCEPTED_CANDIDATE_KEYS = ("downside_volatility_60d", "return_on_assets_change_yoy")
CANDIDATE_COLUMNS = tuple(f"{key}_percentile" for key in ACCEPTED_CANDIDATE_KEYS)


def _combined_registry() -> FeatureRegistry:
    accepted = tuple(
        definition
        for definition in next_generation_candidate_registry().definitions()
        if definition.key in ACCEPTED_CANDIDATE_KEYS
    )
    return FeatureRegistry((*baseline_feature_registry().definitions(), *accepted))


def _validate_source(dataset: Path, manifest: Path) -> dict[str, object]:
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
        expected_hash = str(document["content_sha256"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid source training-dataset manifest") from error
    if sha256(dataset.read_bytes()).hexdigest() != expected_hash:
        raise DataQualityError("source training dataset does not match its immutable manifest")
    if document.get("dataset_key") != "sp500_current_survivors_20d" or document.get("dataset_version") != "v1":
        raise DataQualityError("challenger dataset requires the frozen Tier-B source dataset v1")
    return document


def _load_candidate_inputs(database_url: str, security_ids: set[str], end_date: date):
    import psycopg

    prices: dict[str, list[FeaturePriceObservation]] = defaultdict(list)
    facts: dict[str, list[FundamentalFactObservation]] = defaultdict(list)
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT security_id::text, session_date, close_price, adjustment_basis, available_at, volume
               FROM quantrade.daily_price_bars
               WHERE security_id = ANY(%s::uuid[]) AND session = 'regular'
                 AND adjustment_basis = 'split_adjusted' AND session_date <= %s
               ORDER BY security_id, session_date""",
            (list(security_ids), end_date),
        )
        for row in cursor:
            prices[row[0]].append(FeaturePriceObservation(*row))
        cursor.execute(
            """SELECT security_id::text, filing_id::text, taxonomy, concept, unit, fact_value,
                      period_start, period_end, available_at
               FROM quantrade.filing_facts
               WHERE security_id = ANY(%s::uuid[]) AND period_end <= %s
                 AND taxonomy = 'us-gaap' AND unit = 'USD'
                 AND concept IN ('NetIncomeLoss', 'ProfitLoss', 'Assets')
               ORDER BY security_id, period_end, available_at""",
            (list(security_ids), end_date),
        )
        for row in cursor:
            facts[row[0]].append(FundamentalFactObservation(*row))
    return prices, facts


def _development_identity(dataset: Path) -> tuple[set[str], date, int]:
    securities: set[str] = set()
    end_date: date | None = None
    rows = 0
    with dataset.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"partition", "score_date", "security_id", "sector_code"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise DataQualityError("source training dataset lacks the required identity columns")
        for row in reader:
            if row.get("partition") != "development":
                continue
            score_date = date.fromisoformat(row["score_date"])
            if score_date >= HOLDOUT_START:
                raise DataQualityError("development source row reaches the locked holdout")
            securities.add(row["security_id"])
            end_date = max(end_date, score_date) if end_date else score_date
            rows += 1
    if not rows or end_date is None:
        raise DataQualityError("source training dataset has no development rows")
    return securities, end_date, rows


def _percentiles(values: list[tuple[str, Decimal]], *, higher_is_better: bool) -> dict[str, Decimal]:
    ordered = sorted(values, key=lambda item: (item[1], item[0]))
    if len(ordered) < 2:
        return {}
    denominator = Decimal(len(ordered) - 1)
    result: dict[str, Decimal] = {}
    position = 0
    while position < len(ordered):
        end = position
        while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[position][1]:
            end += 1
        raw = Decimal(position + end) / Decimal("2") / denominator
        percentile = raw if higher_is_better else Decimal("1") - raw
        for security_id, _ in ordered[position:end + 1]:
            result[security_id] = percentile
        position = end + 1
    return result


def _rank_by_sector(
    rows: list[dict[str, str]], raw: dict[str, Decimal], *, higher_is_better: bool,
) -> dict[str, Decimal]:
    grouped: dict[str, list[tuple[str, Decimal]]] = defaultdict(list)
    for row in rows:
        security_id = row["security_id"]
        if security_id in raw:
            grouped[row["sector_code"]].append((security_id, raw[security_id]))
    ranked: dict[str, Decimal] = {}
    for values in grouped.values():
        ranked.update(_percentiles(values, higher_is_better=higher_is_better))
    return ranked


def build_challenger_dataset(
    *,
    database_url: str,
    source_dataset: Path,
    source_manifest: Path,
    destination: Path,
) -> dict[str, object]:
    """Export only pre-holdout rows where both accepted candidate inputs are available."""
    source_metadata = _validate_source(source_dataset, source_manifest)
    if destination.exists():
        raise DataQualityError(f"refusing to overwrite immutable challenger dataset: {destination}")
    security_ids, end_date, source_development_rows = _development_identity(source_dataset)
    prices, facts = _load_candidate_inputs(database_url, security_ids, end_date)
    price_dates = {
        security_id: [item.session_date for item in observations]
        for security_id, observations in prices.items()
    }
    for observations in facts.values():
        observations.sort(key=lambda item: (item.available_at, item.period_end, item.filing_id))
    fact_available_times = {
        security_id: [item.available_at for item in observations]
        for security_id, observations in facts.items()
    }
    registry = next_generation_candidate_registry()
    destination.parent.mkdir(parents=True, exist_ok=True)
    excluded = Counter()
    written = 0
    formation_count = 0
    output_fieldnames: list[str]
    with source_dataset.open("r", encoding="utf-8", newline="") as source, destination.open(
        "w", encoding="utf-8", newline=""
    ) as output:
        reader = csv.DictReader(source)
        if reader.fieldnames is None:
            raise DataQualityError("source training dataset has no header")
        output_fieldnames = [*reader.fieldnames, *CANDIDATE_COLUMNS]
        writer = csv.DictWriter(output, fieldnames=output_fieldnames, lineterminator="\n")
        writer.writeheader()
        current_date: date | None = None
        current_rows: list[dict[str, str]] = []

        def flush(rows: list[dict[str, str]], score_date: date | None) -> None:
            nonlocal written, formation_count
            if not rows or score_date is None:
                return
            formation_count += 1
            decision_at = historical_decision_at(score_date)
            downside_raw: dict[str, Decimal] = {}
            roa_change_raw: dict[str, Decimal] = {}
            for row in rows:
                security_id = row["security_id"]
                price_history = prices[security_id]
                end_index = bisect_right(price_dates.get(security_id, []), score_date)
                eligible_prices: list[FeaturePriceObservation] = []
                for item in reversed(price_history[:end_index]):
                    if item.available_at <= decision_at:
                        eligible_prices.append(item)
                        if len(eligible_prices) == 61:
                            break
                eligible_prices.reverse()
                fact_history = facts[security_id]
                fact_end_index = bisect_right(
                    fact_available_times.get(security_id, []), decision_at,
                )
                eligible_facts = [
                    item for item in fact_history[:fact_end_index]
                    if item.period_end <= score_date
                ]
                try:
                    downside_raw[security_id] = calculate_downside_volatility_60d(
                        eligible_prices,
                        security_id=security_id,
                        formation_date=score_date,
                        decision_at=decision_at,
                        registry=registry,
                    ).value
                except (DataQualityError, ArithmeticError, ValueError) as error:
                    excluded[f"downside_volatility_60d:{_reason(error)}"] += 1
                try:
                    roa_change_raw[security_id] = calculate_return_on_assets_change_yoy(
                        eligible_facts,
                        security_id=security_id,
                        formation_date=score_date,
                        decision_at=decision_at,
                        registry=registry,
                    ).value
                except (DataQualityError, ArithmeticError, ValueError) as error:
                    excluded[f"return_on_assets_change_yoy:{_reason(error)}"] += 1
            downside_ranks = _rank_by_sector(rows, downside_raw, higher_is_better=False)
            roa_change_ranks = _rank_by_sector(rows, roa_change_raw, higher_is_better=True)
            for row in rows:
                security_id = row["security_id"]
                if security_id not in downside_ranks or security_id not in roa_change_ranks:
                    excluded["common_sample:missing_candidate_rank"] += 1
                    continue
                row[CANDIDATE_COLUMNS[0]] = str(downside_ranks[security_id])
                row[CANDIDATE_COLUMNS[1]] = str(roa_change_ranks[security_id])
                writer.writerow(row)
                written += 1
            if formation_count % 50 == 0:
                print(
                    f"dataset_progress_formations={formation_count}; latest_date={score_date}; "
                    f"common_rows={written}",
                    flush=True,
                )

        for row in reader:
            if row.get("partition") != "development":
                continue
            score_date = date.fromisoformat(row["score_date"])
            if current_date is not None and score_date != current_date:
                flush(current_rows, current_date)
                current_rows = []
            current_date = score_date
            current_rows.append(row)
        flush(current_rows, current_date)
    if not written:
        raise DataQualityError("challenger dataset has no complete common-sample rows")
    coverage = Decimal(written) / Decimal(source_development_rows)
    if coverage < Decimal("0.90"):
        raise DataQualityError(f"challenger common-sample coverage is below 90%: {coverage}")
    metadata: dict[str, object] = {
        "dataset_key": DATASET_KEY,
        "dataset_version": DATASET_VERSION,
        "development_only": True,
        "holdout_used": False,
        "data_capability_tier": "B",
        "source_dataset_sha256": source_metadata["content_sha256"],
        "source_development_rows": source_development_rows,
        "common_sample_rows": written,
        "common_sample_coverage": str(coverage),
        "formation_count": formation_count,
        "candidate_columns": list(CANDIDATE_COLUMNS),
        "combined_feature_registry_hash": _combined_registry().registry_hash,
        "exclusions": dict(sorted(excluded.items())),
        "content_sha256": sha256(destination.read_bytes()).hexdigest(),
        "limitations": source_metadata["limitations"],
    }
    return metadata


def _settings(env_file: Path):
    from .config import Settings

    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the development-only Phase 9 common-sample dataset")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    metadata = build_challenger_dataset(
        database_url=settings.database_url,
        source_dataset=arguments.source,
        source_manifest=arguments.source_manifest,
        destination=arguments.output,
    )
    manifest = arguments.output.with_suffix(".json")
    if manifest.exists():
        raise DataQualityError(f"refusing to overwrite immutable challenger manifest: {manifest}")
    manifest.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"common_sample_rows={metadata['common_sample_rows']}; "
        f"coverage={metadata['common_sample_coverage']}; holdout_used=false"
    )


if __name__ == "__main__":
    main()
