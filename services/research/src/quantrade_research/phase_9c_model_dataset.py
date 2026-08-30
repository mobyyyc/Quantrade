"""Build the label-safe Phase 9C weekly development dataset and fold manifest."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Mapping, Sequence

from .phase_9c_feature_panel import PANEL_KEY, PANEL_VERSION
from .phase_9c_features import FAMILY_KEYS, FEATURE_RULE_VERSION, RAW_FEATURE_KEYS
from .quality import DataQualityError
from .score_run import _dotenv_values
from .wealth_ledger import (
    LEDGER_RULE, WealthAction, WealthPriceMark, calculate_relative_wealth_return,
    calculate_wealth_return,
)


DATASET_KEY = "phase_9c_weekly_rank_development"
DATASET_VERSION = "v1"
HOLDOUT_START = date(2025, 7, 1)
LABEL_HORIZON_SESSIONS = 20
MINIMUM_INFORMATIVE_FAMILIES = 3
MINIMUM_AGGREGATE_LABEL_COVERAGE = 0.95
MINIMUM_FORMATION_LABEL_COVERAGE = 0.90
OUTER_BLOCKS = (
    (date(2023, 7, 1), date(2023, 12, 31)),
    (date(2024, 1, 1), date(2024, 6, 30)),
    (date(2024, 7, 1), date(2024, 12, 31)),
    (date(2025, 1, 1), date(2025, 6, 30)),
)


@dataclass(frozen=True, slots=True)
class LabelPriceBar:
    lineage_id: str
    security_id: str
    session_date: date
    open_price: Decimal
    available_at: datetime

    def mark(self) -> WealthPriceMark:
        return WealthPriceMark(self.session_date, self.open_price, self.available_at)


@dataclass(frozen=True, slots=True)
class LabelWindow:
    formation_date: date
    entry_date: date
    outcome_date: date
    sessions: tuple[date, ...]


@dataclass(frozen=True, slots=True)
class LabelOutcome:
    security_return: Decimal
    benchmark_return: Decimal
    benchmark_relative_return: Decimal
    entry_date: date
    outcome_date: date
    label_sha256: str
    lineage: Mapping[str, object]


def _canonical_hash(document: object) -> str:
    return sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _panel_paths(panel: Path) -> tuple[Path, Path]:
    base = panel.with_suffix("") if panel.suffix == ".gz" else panel
    return base.with_suffix(".json"), base.with_suffix(".lineage.tsv.gz")


def _output_paths(destination: Path) -> tuple[Path, Path, Path]:
    base = destination.with_suffix("") if destination.suffix == ".gz" else destination
    return (
        base.with_suffix(".json"),
        base.with_suffix(".label_lineage.tsv.gz"),
        base.with_suffix(".folds.json"),
    )


def _validate_panel(panel: Path) -> dict[str, object]:
    manifest_path, lineage_path = _panel_paths(panel)
    try:
        metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid Phase 9C feature-panel manifest") from error
    if metadata.get("panel_key") != PANEL_KEY or metadata.get("panel_version") != PANEL_VERSION:
        raise DataQualityError("unexpected Phase 9C feature-panel version")
    if metadata.get("feature_rule_version") != FEATURE_RULE_VERSION or metadata.get("passed") is not True:
        raise DataQualityError("Phase 9C feature panel is not an approved passing artifact")
    if metadata.get("holdout_used") is not False or date.fromisoformat(str(metadata["end_date"])) >= HOLDOUT_START:
        raise DataQualityError("Phase 9C feature panel must not contain the consumed holdout")
    if _sha256_file(panel) != metadata.get("panel_file_sha256"):
        raise DataQualityError("Phase 9C feature panel does not match its manifest")
    if not lineage_path.exists() or _sha256_file(lineage_path) != metadata.get("lineage_file_sha256"):
        raise DataQualityError("Phase 9C feature lineage does not match its manifest")
    recorded_report_hash = metadata.get("report_hash")
    report_payload = dict(metadata)
    report_payload.pop("report_hash", None)
    if _canonical_hash(report_payload) != recorded_report_hash:
        raise DataQualityError("Phase 9C feature-panel report hash is invalid")
    return metadata


def _row_hash(row: Mapping[str, object]) -> str:
    return _canonical_hash({key: row[key] for key in sorted(row) if key not in {"row_hash", "dataset_row_sha256"}})


def _load_panel_index(panel: Path) -> tuple[tuple[str, ...], tuple[date, ...], dict[tuple[date, str], bool]]:
    security_ids: set[str] = set()
    formations: set[date] = set()
    eligibility: dict[tuple[date, str], bool] = {}
    with gzip.open(panel, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"security_id", "formation_date", "score_eligible", "row_hash"}
        if not reader.fieldnames or not required <= set(reader.fieldnames):
            raise DataQualityError("Phase 9C feature panel has an unexpected schema")
        for row in reader:
            # The immutable compressed file is already authenticated against
            # the approved manifest. Its row digest was calculated before CSV
            # serialization, so integer and boolean types cannot be recreated
            # faithfully from the string-only CSV representation.
            if not row["row_hash"]:
                raise DataQualityError("Phase 9C feature-panel row lineage is missing")
            formation = date.fromisoformat(row["formation_date"])
            security_id = row["security_id"]
            key = formation, security_id
            if key in eligibility:
                raise DataQualityError("Phase 9C feature panel contains a duplicate row")
            security_ids.add(security_id)
            formations.add(formation)
            eligibility[key] = row["score_eligible"] == "true"
    ordered_securities, ordered_formations = tuple(sorted(security_ids)), tuple(sorted(formations))
    if len(ordered_securities) != 500:
        raise DataQualityError("Phase 9C model dataset requires the fixed 500-security cohort")
    if len(eligibility) != len(ordered_securities) * len(ordered_formations):
        raise DataQualityError("Phase 9C feature panel is not a complete formation grid")
    return ordered_securities, ordered_formations, eligibility


def _action(row: Sequence[object]) -> WealthAction:
    return WealthAction(
        action_id=str(row[0]), action_type=str(row[1]), process_date=row[2],
        effective_date=row[3], cash_amount=row[4], ratio_numerator=row[5],
        ratio_denominator=row[6], currency=str(row[7]) if row[7] else None,
        available_at=row[8], source_reference=str(row[9]),
    )


def _load_label_inputs(
    database_url: str, *, security_ids: Sequence[str], formations: Sequence[date],
):
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute(
            """SELECT concat_ws('|',benchmark_ticker,session_date::text,adjustment_basis),
                      benchmark_ticker,session_date,open_price,available_at
                 FROM quantrade.benchmark_daily_price_bars
                WHERE benchmark_ticker='SPY' AND session='regular' AND adjustment_basis='unadjusted'
                  AND session_date > %s AND session_date < %s ORDER BY session_date""",
            (formations[0], HOLDOUT_START),
        )
        benchmark = {
            row[2]: LabelPriceBar(str(row[0]), str(row[1]), row[2], Decimal(row[3]), row[4])
            for row in cursor
        }
        sessions = tuple(sorted(benchmark))
        windows: dict[date, LabelWindow] = {}
        for formation in formations:
            future = tuple(item for item in sessions if item > formation)
            if len(future) <= LABEL_HORIZON_SESSIONS:
                continue
            selected = future[:LABEL_HORIZON_SESSIONS + 1]
            if selected[-1] >= HOLDOUT_START:
                continue
            windows[formation] = LabelWindow(formation, selected[0], selected[-1], selected)
        if not windows:
            raise DataQualityError("no label-safe Phase 9C windows are available")
        needed_sessions = sorted({session for window in windows.values() for session in window.sessions})
        cursor.execute(
            """SELECT daily_price_bar_id::text,security_id::text,session_date,open_price,available_at
                 FROM quantrade.daily_price_bars
                WHERE security_id=ANY(%s::uuid[]) AND session='regular'
                  AND adjustment_basis='unadjusted' AND session_date=ANY(%s::date[])
                ORDER BY security_id,session_date""",
            (list(security_ids), needed_sessions),
        )
        prices: dict[str, dict[date, LabelPriceBar]] = defaultdict(dict)
        for row in cursor:
            security_id, session = str(row[1]), row[2]
            if session in prices[security_id]:
                raise DataQualityError("duplicate unadjusted label price bar")
            prices[security_id][session] = LabelPriceBar(
                str(row[0]), security_id, session, Decimal(row[3]), row[4],
            )
        first_entry = min(item.entry_date for item in windows.values())
        last_outcome = max(item.outcome_date for item in windows.values())
        cursor.execute(
            """SELECT security_id::text,provider_action_id,action_type,process_date,effective_date,
                      cash_amount,ratio_numerator,ratio_denominator,currency,available_at,source_reference
                 FROM quantrade.corporate_actions
                WHERE security_id=ANY(%s::uuid[])
                  AND COALESCE(effective_date,process_date) > %s
                  AND COALESCE(effective_date,process_date) <= %s
                ORDER BY security_id,COALESCE(effective_date,process_date),provider_action_id""",
            (list(security_ids), first_entry, last_outcome),
        )
        actions: dict[str, list[WealthAction]] = defaultdict(list)
        for row in cursor:
            actions[str(row[0])].append(_action(row[1:]))
        cursor.execute(
            """SELECT provider_action_id,action_type,process_date,effective_date,cash_amount,
                      ratio_numerator,ratio_denominator,currency,available_at,source_reference
                 FROM quantrade.benchmark_corporate_actions
                WHERE benchmark_ticker='SPY'
                  AND COALESCE(effective_date,process_date) > %s
                  AND COALESCE(effective_date,process_date) <= %s
                ORDER BY COALESCE(effective_date,process_date),provider_action_id""",
            (first_entry, last_outcome),
        )
        benchmark_actions = tuple(_action(row) for row in cursor)
    return windows, prices, benchmark, actions, benchmark_actions


def _ledger_result(
    bars: Sequence[LabelPriceBar], actions: Sequence[WealthAction], window: LabelWindow,
):
    if tuple(item.session_date for item in bars) != window.sessions:
        return None
    return calculate_wealth_return(
        entry_date=window.entry_date, exit_date=window.outcome_date,
        entry_price=bars[0].open_price, exit_price=bars[-1].open_price,
        entry_available_at=bars[0].available_at, exit_available_at=bars[-1].available_at,
        actions=actions, intermediate_prices=tuple(item.mark() for item in bars),
    )


def _label_outcome(
    *, security_id: str, window: LabelWindow, security_prices: Mapping[date, LabelPriceBar],
    benchmark_prices: Mapping[date, LabelPriceBar], security_actions: Sequence[WealthAction],
    benchmark_actions: Sequence[WealthAction],
) -> tuple[LabelOutcome | None, str | None]:
    security_bars = tuple(security_prices[item] for item in window.sessions if item in security_prices)
    benchmark_bars = tuple(benchmark_prices[item] for item in window.sessions if item in benchmark_prices)
    if len(security_bars) != len(window.sessions):
        return None, "missing_complete_security_price_path"
    if len(benchmark_bars) != len(window.sessions):
        return None, "missing_complete_benchmark_price_path"
    security = _ledger_result(security_bars, security_actions, window)
    benchmark = _ledger_result(benchmark_bars, benchmark_actions, window)
    if security is None or benchmark is None:
        return None, "missing_complete_price_path"
    relative = calculate_relative_wealth_return(security, benchmark)
    if relative.status != "completed":
        return None, relative.unavailable_reason or "wealth_ledger_withheld"
    assert security.wealth_return is not None
    assert benchmark.wealth_return is not None
    assert relative.benchmark_relative_return is not None
    lineage: dict[str, object] = {
        "security_id": security_id,
        "formation_date": window.formation_date.isoformat(),
        "entry_date": window.entry_date.isoformat(),
        "outcome_date": window.outcome_date.isoformat(),
        "security_bar_ids": [item.lineage_id for item in security_bars],
        "benchmark_bar_ids": [item.lineage_id for item in benchmark_bars],
        "security_action_ids": list(security.action_ids),
        "benchmark_action_ids": list(benchmark.action_ids),
        "security_ledger_sha256": security.digest,
        "benchmark_ledger_sha256": benchmark.digest,
        "ledger_rule": LEDGER_RULE,
    }
    label_document = {
        "security_return": str(security.wealth_return),
        "benchmark_return": str(benchmark.wealth_return),
        "benchmark_relative_return": str(relative.benchmark_relative_return),
        "lineage": lineage,
    }
    label_hash = _canonical_hash(label_document)
    return LabelOutcome(
        security.wealth_return, benchmark.wealth_return, relative.benchmark_relative_return,
        window.entry_date, window.outcome_date, label_hash, lineage,
    ), None


def centered_label_ranks(values: Mapping[str, Decimal]) -> dict[str, Decimal]:
    ordered = sorted(values.items(), key=lambda item: (item[1], item[0]))
    if len(ordered) < 2:
        return {}
    denominator = Decimal(len(ordered) - 1)
    output: dict[str, Decimal] = {}
    position = 0
    while position < len(ordered):
        end = position
        while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[position][1]:
            end += 1
        rank = Decimal(position + end) / Decimal("2") / denominator * Decimal("2") - Decimal("1")
        for security_id, _ in ordered[position:end + 1]:
            output[security_id] = rank
        position = end + 1
    return output


def _month_key(value: date) -> str:
    return value.strftime("%Y-%m")


def _exclusion_category(reason: str) -> str:
    if reason.startswith("unexplained structural price discontinuity"):
        return "unexplained_structural_price_discontinuity"
    if reason.startswith("corporate action has no effective date"):
        return "undated_corporate_action"
    if reason.startswith("unresolved complex corporate action"):
        return reason.replace(" ", "_").replace(":_", ":")
    return reason


def _formation_hash(values: Sequence[date]) -> str:
    return sha256("\n".join(item.isoformat() for item in values).encode()).hexdigest()


def build_nested_folds(
    formation_outcomes: Mapping[date, date], included_rows: Mapping[date, int],
) -> dict[str, object]:
    formations = tuple(sorted(formation_outcomes))
    outer_folds: list[dict[str, object]] = []
    violations = 0
    for fold_number, (block_start, block_end) in enumerate(OUTER_BLOCKS, start=1):
        validation = tuple(item for item in formations if block_start <= item <= block_end)
        if not validation:
            raise DataQualityError(f"outer fold {fold_number} has no label-safe validation formations")
        validation_start = validation[0]
        prior = tuple(item for item in formations if item < validation_start)
        training = tuple(item for item in prior if formation_outcomes[item] < validation_start)
        purged = tuple(item for item in prior if item not in training)
        if not training:
            raise DataQualityError(f"outer fold {fold_number} has no purged training formations")
        violations += sum(formation_outcomes[item] >= validation_start for item in training)
        training_months = sorted({_month_key(item) for item in training})
        if len(training_months) < 9:
            raise DataQualityError(f"outer fold {fold_number} lacks nine months for nested tuning")
        tuning_months = training_months[-9:]
        inner_folds: list[dict[str, object]] = []
        for inner_number in range(3):
            selected_months = tuple(tuning_months[inner_number * 3:(inner_number + 1) * 3])
            inner_validation = tuple(item for item in training if _month_key(item) in selected_months)
            inner_start = inner_validation[0]
            inner_prior = tuple(item for item in training if item < inner_start)
            inner_training = tuple(item for item in inner_prior if formation_outcomes[item] < inner_start)
            inner_purged = tuple(item for item in inner_prior if item not in inner_training)
            if not inner_training or not inner_validation:
                raise DataQualityError("nested chronological split is empty after outcome-overlap purge")
            violations += sum(formation_outcomes[item] >= inner_start for item in inner_training)
            inner_folds.append({
                "inner_fold": inner_number + 1,
                "validation_months": list(selected_months),
                "training_formations": [item.isoformat() for item in inner_training],
                "purged_formations": [item.isoformat() for item in inner_purged],
                "validation_formations": [item.isoformat() for item in inner_validation],
                "training_formation_sha256": _formation_hash(inner_training),
                "validation_formation_sha256": _formation_hash(inner_validation),
                "training_rows": sum(included_rows[item] for item in inner_training),
                "validation_rows": sum(included_rows[item] for item in inner_validation),
            })
        outer_folds.append({
            "outer_fold": fold_number,
            "registered_block": [block_start.isoformat(), block_end.isoformat()],
            "training_formations": [item.isoformat() for item in training],
            "purged_formations": [item.isoformat() for item in purged],
            "validation_formations": [item.isoformat() for item in validation],
            "training_formation_sha256": _formation_hash(training),
            "validation_formation_sha256": _formation_hash(validation),
            "training_rows": sum(included_rows[item] for item in training),
            "validation_rows": sum(included_rows[item] for item in validation),
            "inner_folds": inner_folds,
        })
    return {
        "fold_rule": "phase_9c_nested_chronological_actual_outcome_purge_v1",
        "holdout_start": HOLDOUT_START.isoformat(),
        "outcome_overlap_rule": "training outcome_date must be earlier than validation formation_date",
        "inner_tuning_rule": "last nine eligible training months split into three continuous three-month blocks",
        "outer_folds": outer_folds,
        "label_overlap_violations": violations,
    }


def _dataset_fields() -> list[str]:
    fields = [
        "partition", "formation_date", "decision_at", "calendar_month", "security_id",
        "entry_date", "outcome_date", "security_return", "benchmark_return",
        "benchmark_relative_return", "label_centered_rank", "sample_weight",
    ]
    fields.extend(f"{key}_centered_rank" for key in RAW_FEATURE_KEYS)
    fields.extend(f"{key}_available" for key in RAW_FEATURE_KEYS)
    for family in FAMILY_KEYS:
        fields.extend((f"{family}_value", f"{family}_availability", f"{family}_informative"))
    fields.extend(("source_panel_row_sha256", "label_sha256", "dataset_row_sha256"))
    return fields


def _audit_written_dataset(
    dataset: Path, lineage: Path, expected: Mapping[tuple[date, str], LabelOutcome],
) -> dict[str, object]:
    row_keys: set[tuple[date, str]] = set()
    row_hashes: list[str] = []
    row_violations = 0
    with gzip.open(dataset, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != _dataset_fields():
            raise DataQualityError("Phase 9C model dataset has an unexpected serialized schema")
        for row in reader:
            key = date.fromisoformat(row["formation_date"]), row["security_id"]
            outcome = expected.get(key)
            if key in row_keys or outcome is None:
                row_violations += 1
            row_keys.add(key)
            if row["dataset_row_sha256"] != _row_hash(row):
                row_violations += 1
            if not outcome or row["label_sha256"] != outcome.label_sha256:
                row_violations += 1
            if row["partition"] != "development" or date.fromisoformat(row["outcome_date"]) >= HOLDOUT_START:
                row_violations += 1
            rank = Decimal(row["label_centered_rank"])
            if rank < Decimal("-1") or rank > Decimal("1"):
                row_violations += 1
            row_hashes.append(row["dataset_row_sha256"])
    lineage_keys: set[tuple[date, str]] = set()
    lineage_violations = 0
    with gzip.open(lineage, "rt", encoding="utf-8", newline="") as handle:
        header = handle.readline().rstrip("\n")
        if header != "security_id\tformation_date\tlabel_sha256\tpayload":
            raise DataQualityError("Phase 9C label lineage has an unexpected schema")
        for line in handle:
            security_id, formation_text, label_hash, payload_text = line.rstrip("\n").split("\t", 3)
            formation = date.fromisoformat(formation_text)
            key = formation, security_id
            outcome = expected.get(key)
            if key in lineage_keys or outcome is None or label_hash != outcome.label_sha256:
                lineage_violations += 1
            lineage_keys.add(key)
            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError:
                lineage_violations += 1
                continue
            if (
                payload.get("security_id") != security_id
                or payload.get("formation_date") != formation_text
                or len(payload.get("security_bar_ids", ())) != LABEL_HORIZON_SESSIONS + 1
                or len(payload.get("benchmark_bar_ids", ())) != LABEL_HORIZON_SESSIONS + 1
            ):
                lineage_violations += 1
    expected_keys = set(expected)
    return {
        "row_count": len(row_hashes),
        "row_violations": row_violations,
        "lineage_count": len(lineage_keys),
        "lineage_violations": lineage_violations,
        "row_key_coverage": row_keys == expected_keys,
        "lineage_key_coverage": lineage_keys == expected_keys,
        "logical_sha256": sha256("\n".join(row_hashes).encode()).hexdigest(),
    }


def _build_model_dataset(
    *, database_url: str, panel: Path, destination: Path,
) -> dict[str, object]:
    panel_metadata = _validate_panel(panel)
    metadata_path, lineage_path, folds_path = _output_paths(destination)
    outputs = (destination, metadata_path, lineage_path, folds_path)
    if any(item.exists() for item in outputs):
        raise DataQualityError("refusing to overwrite immutable Phase 9C model-dataset artifacts")
    security_ids, formations, feature_eligibility = _load_panel_index(panel)
    windows, prices, benchmark, actions, benchmark_actions = _load_label_inputs(
        database_url, security_ids=security_ids, formations=formations,
    )
    exclusions = Counter()
    outcomes: dict[tuple[date, str], LabelOutcome] = {}
    label_ranks: dict[tuple[date, str], Decimal] = {}
    eligible_feature_rows = Counter()
    completed_labels = Counter()
    candidate_formation_coverage: dict[date, float] = {}
    excluded_formations: dict[date, dict[str, object]] = {}
    replay_input = None
    for formation_index, formation in enumerate(formations, start=1):
        window = windows.get(formation)
        if window is None:
            exclusions["label_window_reaches_consumed_holdout"] += len(security_ids)
            continue
        values: dict[str, Decimal] = {}
        for security_id in security_ids:
            if not feature_eligibility[(formation, security_id)]:
                exclusions["feature_row_not_score_eligible"] += 1
                continue
            eligible_feature_rows[formation] += 1
            outcome, reason = _label_outcome(
                security_id=security_id, window=window,
                security_prices=prices.get(security_id, {}), benchmark_prices=benchmark,
                security_actions=actions.get(security_id, ()), benchmark_actions=benchmark_actions,
            )
            if outcome is None:
                exclusions[_exclusion_category(reason or "label_unavailable")] += 1
                continue
            outcomes[(formation, security_id)] = outcome
            values[security_id] = outcome.benchmark_relative_return
            completed_labels[formation] += 1
            replay_input = (
                security_id, window, prices.get(security_id, {}), benchmark,
                actions.get(security_id, ()), benchmark_actions, outcome.label_sha256,
            )
        ranks = centered_label_ranks(values)
        if values and len(ranks) != len(values):
            raise DataQualityError("label rank construction failed")
        coverage = len(values) / eligible_feature_rows[formation] if eligible_feature_rows[formation] else 0
        candidate_formation_coverage[formation] = coverage
        if coverage < MINIMUM_FORMATION_LABEL_COVERAGE:
            for security_id in values:
                outcomes.pop((formation, security_id), None)
            exclusions["formation_below_label_coverage_gate"] += len(values)
            excluded_formations[formation] = {
                "feature_eligible_rows": eligible_feature_rows[formation],
                "completed_label_rows": len(values),
                "coverage": coverage,
                "reason": "completed label coverage below the frozen 90% cross-sectional minimum",
            }
            ranks = {}
        label_ranks.update(((formation, security_id), value) for security_id, value in ranks.items())
        if formation_index == 1 or formation_index % 20 == 0 or formation_index == len(formations):
            print(
                f"model_dataset_label_progress={formation_index}/{len(formations)}; "
                f"formation={formation.isoformat()}; label_coverage={coverage:.4f}",
                flush=True,
            )
    included_counts = Counter(formation for formation, _ in outcomes)
    included_formations = tuple(sorted(included_counts))
    if not included_formations or replay_input is None:
        raise DataQualityError("Phase 9C model dataset has no completed labels")
    formation_counts_by_month = Counter(_month_key(item) for item in included_formations)
    formation_outcomes = {
        formation: windows[formation].outcome_date for formation in included_formations
    }
    fold_document = build_nested_folds(formation_outcomes, included_counts)
    fold_document["dataset_key"] = DATASET_KEY
    fold_document["dataset_version"] = DATASET_VERSION
    fold_document["feature_panel_sha256"] = panel_metadata["panel_file_sha256"]
    fold_document["fold_sha256"] = _canonical_hash(fold_document)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial_panel = destination.with_name(destination.name + ".partial")
    partial_lineage = lineage_path.with_name(lineage_path.name + ".partial")
    row_hashes: list[str] = []
    month_weights: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    lineage_count = 0
    try:
        with (
            gzip.open(panel, "rt", encoding="utf-8", newline="") as source,
            gzip.open(partial_panel, "wt", encoding="utf-8", newline="") as output,
            gzip.open(partial_lineage, "wt", encoding="utf-8", newline="\n") as lineage,
        ):
            reader = csv.DictReader(source)
            writer = csv.DictWriter(output, fieldnames=_dataset_fields(), lineterminator="\n")
            writer.writeheader()
            lineage.write("security_id\tformation_date\tlabel_sha256\tpayload\n")
            for source_row in reader:
                formation = date.fromisoformat(source_row["formation_date"])
                security_id = source_row["security_id"]
                outcome = outcomes.get((formation, security_id))
                if outcome is None:
                    continue
                month = _month_key(formation)
                weight = (
                    Decimal("1") / Decimal(formation_counts_by_month[month])
                    / Decimal(included_counts[formation])
                )
                row: dict[str, object] = {
                    "partition": "development",
                    "formation_date": formation.isoformat(),
                    "decision_at": source_row["decision_at"],
                    "calendar_month": month,
                    "security_id": security_id,
                    "entry_date": outcome.entry_date.isoformat(),
                    "outcome_date": outcome.outcome_date.isoformat(),
                    "security_return": str(outcome.security_return),
                    "benchmark_return": str(outcome.benchmark_return),
                    "benchmark_relative_return": str(outcome.benchmark_relative_return),
                    "label_centered_rank": str(label_ranks[(formation, security_id)]),
                    "sample_weight": str(weight),
                }
                for key in RAW_FEATURE_KEYS:
                    row[f"{key}_centered_rank"] = source_row[f"{key}_centered_rank"]
                    row[f"{key}_available"] = source_row[f"{key}_available"]
                for family in FAMILY_KEYS:
                    row[f"{family}_value"] = source_row[f"{family}_value"]
                    row[f"{family}_availability"] = source_row[f"{family}_availability"]
                    row[f"{family}_informative"] = source_row[f"{family}_informative"]
                row["source_panel_row_sha256"] = source_row["row_hash"]
                row["label_sha256"] = outcome.label_sha256
                row["dataset_row_sha256"] = _row_hash(row)
                writer.writerow(row)
                row_hashes.append(str(row["dataset_row_sha256"]))
                month_weights[month] += weight
                lineage.write("\t".join((
                    security_id, formation.isoformat(), outcome.label_sha256,
                    json.dumps(outcome.lineage, sort_keys=True, separators=(",", ":")),
                )) + "\n")
                lineage_count += 1
        os.replace(partial_panel, destination)
        os.replace(partial_lineage, lineage_path)
    finally:
        for partial in (partial_panel, partial_lineage):
            if partial.exists():
                partial.unlink()
    folds_path.write_text(json.dumps(fold_document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    replay_security, replay_window, replay_prices, replay_benchmark, replay_actions, replay_spy_actions, expected = replay_input
    replay, replay_reason = _label_outcome(
        security_id=replay_security, window=replay_window,
        security_prices=replay_prices, benchmark_prices=replay_benchmark,
        security_actions=replay_actions, benchmark_actions=replay_spy_actions,
    )
    replay_hash = replay.label_sha256 if replay else None
    artifact_audit = _audit_written_dataset(destination, lineage_path, outcomes)
    eligible_total = sum(eligible_feature_rows[formation] for formation in included_formations)
    raw_panel_rows = len(security_ids) * len(formations)
    label_coverage = len(outcomes) / eligible_total
    formation_label_coverage = {
        formation.isoformat(): completed_labels[formation] / eligible_feature_rows[formation]
        for formation in included_formations
    }
    gates = {
        "holdout_not_used": max(formation_outcomes.values()) < HOLDOUT_START,
        "completed_label_lineage": lineage_count == len(outcomes),
        "dataset_row_hashes": (
            len(row_hashes) == len(outcomes)
            and len(set(row_hashes)) == len(row_hashes)
            and artifact_audit["row_count"] == len(outcomes)
            and artifact_audit["row_violations"] == 0
            and artifact_audit["row_key_coverage"] is True
        ),
        "serialized_label_lineage": (
            artifact_audit["lineage_count"] == len(outcomes)
            and artifact_audit["lineage_violations"] == 0
            and artifact_audit["lineage_key_coverage"] is True
        ),
        "deterministic_label_replay": replay_reason is None and replay_hash == expected,
        "calendar_month_weight": all(
            abs(value - Decimal("1")) <= Decimal("1e-24") for value in month_weights.values()
        ),
        "nested_fold_label_purge": fold_document["label_overlap_violations"] == 0,
        "aggregate_label_coverage": label_coverage >= MINIMUM_AGGREGATE_LABEL_COVERAGE,
        "minimum_formation_label_coverage": (
            min(formation_label_coverage.values()) >= MINIMUM_FORMATION_LABEL_COVERAGE
        ),
        "low_coverage_formations_fail_closed": all(
            formation not in included_formations for formation in excluded_formations
        ),
    }
    metadata: dict[str, object] = {
        "dataset_key": DATASET_KEY,
        "dataset_version": DATASET_VERSION,
        "feature_rule_version": FEATURE_RULE_VERSION,
        "source_panel_sha256": panel_metadata["panel_file_sha256"],
        "source_panel_logical_sha256": panel_metadata["panel_hash"],
        "source_lineage_sha256": panel_metadata["lineage_file_sha256"],
        "research_cohort": panel_metadata["research_cohort"],
        "data_capability_tier": "B",
        "survivorship_biased": True,
        "development_only": True,
        "holdout_used": False,
        "holdout_start": HOLDOUT_START.isoformat(),
        "label_horizon_sessions": LABEL_HORIZON_SESSIONS,
        "label_rule": LEDGER_RULE,
        "label_target": "same-formation centered rank of stock-minus-SPY 20-session wealth return",
        "execution_convention": "next regular-session open through the open after 20 completed sessions",
        "provider_control_policy": (
            "explicit ledger validated by the frozen P9C.2 July-2025-to-June-2026 provider-control audit; "
            "provider-adjusted returns do not replace development labels"
        ),
        "formation_count": len(included_formations),
        "security_count": len(security_ids),
        "source_panel_row_count": raw_panel_rows,
        "feature_eligible_row_count": eligible_total,
        "row_count": len(outcomes),
        "label_coverage_of_feature_eligible_rows": label_coverage,
        "minimum_formation_label_coverage": min(formation_label_coverage.values()),
        "aggregate_label_coverage_gate": MINIMUM_AGGREGATE_LABEL_COVERAGE,
        "formation_label_coverage_gate": MINIMUM_FORMATION_LABEL_COVERAGE,
        "formation_label_coverage": formation_label_coverage,
        "candidate_formation_label_coverage": {
            key.isoformat(): value for key, value in sorted(candidate_formation_coverage.items())
        },
        "excluded_low_coverage_formations": {
            key.isoformat(): value for key, value in sorted(excluded_formations.items())
        },
        "exclusions": dict(sorted(exclusions.items())),
        "model_features": [f"{family}_value" for family in FAMILY_KEYS],
        "diagnostic_features": [
            *(f"{key}_centered_rank" for key in RAW_FEATURE_KEYS),
            *(f"{key}_available" for key in RAW_FEATURE_KEYS),
            *(f"{family}_availability" for family in FAMILY_KEYS),
        ],
        "availability_enters_model": False,
        "minimum_informative_families": MINIMUM_INFORMATIVE_FAMILIES,
        "sample_weighting": "each calendar month sums to one across its weekly formations and eligible rows",
        "month_weight_sums": {key: str(value) for key, value in sorted(month_weights.items())},
        "dataset_logical_sha256": sha256("\n".join(row_hashes).encode()).hexdigest(),
        "dataset_file_sha256": _sha256_file(destination),
        "label_lineage_file_sha256": _sha256_file(lineage_path),
        "fold_file_sha256": _sha256_file(folds_path),
        "fold_logical_sha256": fold_document["fold_sha256"],
        "label_lineage_record_count": lineage_count,
        "serialized_artifact_audit": artifact_audit,
        "replay_formation": replay_window.formation_date.isoformat(),
        "replay_security_id": replay_security,
        "replay_label_sha256": replay_hash,
        "gates": gates,
        "passed": all(gates.values()),
        "limitations": [
            "current-survivors S&P 500 cohort; historical results remain survivorship biased",
            "the consumed July 2025 through June 2026 holdout is excluded from development",
            "complex or incomplete corporate-action windows are withheld rather than repaired",
            "provider total-return bars validate the ledger engine but are not the development label source",
            "availability diagnostics are not model inputs in Phase 9C v1",
        ],
    }
    metadata["report_sha256"] = _canonical_hash(metadata)
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not metadata["passed"]:
        raise DataQualityError("Phase 9C weekly model dataset failed frozen integrity gates")
    return metadata


def build_model_dataset(
    *, database_url: str, panel: Path, destination: Path,
) -> dict[str, object]:
    """Build atomically, removing only artifacts created by a failed attempt."""
    metadata_path, lineage_path, folds_path = _output_paths(destination)
    outputs = (destination, metadata_path, lineage_path, folds_path)
    existed_before = {item: item.exists() for item in outputs}
    try:
        return _build_model_dataset(
            database_url=database_url, panel=panel, destination=destination,
        )
    except BaseException:
        for path in outputs:
            if not existed_before[path] and path.exists():
                path.unlink()
        raise


def _settings(env_file: Path):
    from .config import Settings

    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Phase 9C weekly rank development dataset")
    parser.add_argument(
        "--panel", type=Path,
        default=Path("data/derived/phase_9c_weekly_feature_panel_v1.csv.gz"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("data/derived/phase_9c_weekly_rank_development_v1.csv.gz"),
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    metadata = build_model_dataset(
        database_url=settings.database_url, panel=arguments.panel, destination=arguments.output,
    )
    print(json.dumps({
        "passed": metadata["passed"],
        "rows": metadata["row_count"],
        "formations": metadata["formation_count"],
        "label_coverage": metadata["label_coverage_of_feature_eligible_rows"],
        "minimum_formation_label_coverage": metadata["minimum_formation_label_coverage"],
        "report_sha256": metadata["report_sha256"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
