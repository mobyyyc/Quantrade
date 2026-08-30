"""Fit the pre-registered Phase 9C nested weekly rank comparison.

This module deliberately separates three questions:

* how the exact deployed artifact orders the historical cross-section;
* how its six active inputs behave when refit under the weekly rank protocol; and
* whether the frozen Phase 9C economic families add ranking information.

The consumed holdout is rejected before any model is fit. Hyperparameters are
selected solely from the registered inner folds; outer predictions are written
for later portfolio attribution and gate evaluation, never for tuning here.
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import defaultdict
import csv
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
import gzip
from hashlib import sha256
import io
import json
import math
from pathlib import Path
from statistics import fmean
from typing import Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .active_model import ActiveModelArtifact, load_active_model
from .phase_9c_features import FAMILY_KEYS
from .phase_9c_model_dataset import DATASET_KEY, DATASET_VERSION, HOLDOUT_START
from .quality import DataQualityError
from .score_run import _dotenv_values
from .sec_form_scope import RESEARCH_RELEVANT_FORMS


COMPARISON_KEY = "phase_9c_nested_weekly_rank_comparison"
COMPARISON_VERSION = "v1"
RIDGE_PENALTIES = (0.1, 1.0, 10.0, 100.0)
PAIRWISE_PENALTIES = (0.1, 1.0, 10.0, 100.0)
PAIR_COUNT_PER_FORMATION = 64
INNER_TIE_TOLERANCE = 0.002
ACTIVE_RAW_COLUMNS = (
    "momentum_12_1_raw",
    "relative_strength_6m_raw",
    "realized_volatility_60d_raw",
    "median_dollar_volume_20d_raw",
    "earnings_yield_ttm_raw",
    "return_on_assets_ttm_raw",
)
ACTIVE_MODEL_COLUMNS = (
    "momentum_12_1_percentile",
    "relative_strength_6m_percentile",
    "trailing_volatility_60d_percentile",
    "median_dollar_volume_20d_percentile",
    "earnings_yield_ttm_percentile",
    "return_on_assets_ttm_percentile",
)
ACTIVE_DIRECTIONS = (1, 1, -1, 1, 1, 1)
PREDICTION_COLUMNS = (
    "model_key", "outer_fold", "formation_date", "calendar_month", "security_id",
    "prediction", "label_centered_rank", "benchmark_relative_return", "dataset_row_sha256",
)


@dataclass(frozen=True, slots=True)
class Example:
    formation_date: date
    calendar_month: str
    security_id: str
    target: float
    relative_return: float
    sample_weight: float
    family_features: tuple[float, ...]
    dataset_row_sha256: str
    active_features: tuple[float, ...] | None = None


@dataclass(frozen=True, slots=True)
class LinearFit:
    means: tuple[float, ...]
    scales: tuple[float, ...]
    target_mean: float
    coefficients: tuple[float, ...]

    def predict(self, values: Sequence[float]) -> float:
        return self.target_mean + sum(
            coefficient * ((value - mean) / scale)
            for value, mean, scale, coefficient in zip(
                values, self.means, self.scales, self.coefficients, strict=True,
            )
        )


@dataclass(frozen=True, slots=True)
class Prediction:
    model_key: str
    outer_fold: int
    example: Example
    value: float


@dataclass(frozen=True, slots=True)
class ActiveFact:
    fact_id: str
    filing_id: str
    taxonomy: str
    concept: str
    unit: str
    value: float
    period_start: date | None
    period_end: date
    available_at: datetime


def _canonical_hash(document: object) -> str:
    return sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _artifact_paths(dataset: Path, destination: Path) -> tuple[Path, Path, Path]:
    dataset_base = dataset.with_suffix("") if dataset.suffix == ".gz" else dataset
    output_base = destination.with_suffix("") if destination.suffix == ".gz" else destination
    return (
        dataset_base.with_suffix(".json"),
        dataset_base.with_suffix(".folds.json"),
        output_base.with_suffix(".fits.json"),
    )


def _validate_inputs(dataset: Path) -> tuple[dict[str, object], dict[str, object]]:
    manifest_path, folds_path, _ = _artifact_paths(dataset, Path("unused.csv.gz"))
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        folds = json.loads(folds_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DataQualityError("invalid Phase 9C model-dataset artifacts") from error
    if manifest.get("dataset_key") != DATASET_KEY or manifest.get("dataset_version") != DATASET_VERSION:
        raise DataQualityError("unexpected Phase 9C model dataset")
    if manifest.get("passed") is not True or manifest.get("holdout_used") is not False:
        raise DataQualityError("Phase 9C model dataset is not an approved development artifact")
    if manifest.get("holdout_start") != HOLDOUT_START.isoformat():
        raise DataQualityError("Phase 9C comparison received an unexpected holdout boundary")
    if _sha256_file(dataset) != manifest.get("dataset_file_sha256"):
        raise DataQualityError("Phase 9C model dataset does not match its manifest")
    if _sha256_file(folds_path) != manifest.get("fold_file_sha256"):
        raise DataQualityError("Phase 9C fold file does not match the dataset manifest")
    manifest_payload = dict(manifest)
    recorded_report_hash = manifest_payload.pop("report_sha256", None)
    if _canonical_hash(manifest_payload) != recorded_report_hash:
        raise DataQualityError("Phase 9C model-dataset report hash is invalid")
    if folds.get("fold_sha256") != manifest.get("fold_logical_sha256"):
        raise DataQualityError("Phase 9C fold manifest does not match the dataset")
    folds_payload = dict(folds)
    recorded_fold_hash = folds_payload.pop("fold_sha256", None)
    if _canonical_hash(folds_payload) != recorded_fold_hash:
        raise DataQualityError("Phase 9C fold manifest hash is invalid")
    if folds.get("label_overlap_violations") != 0 or folds.get("holdout_start") != HOLDOUT_START.isoformat():
        raise DataQualityError("Phase 9C folds violate the holdout or purge contract")
    return manifest, folds


def _read_dataset(dataset: Path) -> tuple[list[Example], dict[tuple[date, str], dict[str, str]]]:
    examples: list[Example] = []
    source_rows: dict[tuple[date, str], dict[str, str]] = {}
    family_columns = tuple(f"{key}_value" for key in FAMILY_KEYS)
    with gzip.open(dataset, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "partition", "formation_date", "calendar_month", "security_id",
            "label_centered_rank", "benchmark_relative_return", "sample_weight",
            "dataset_row_sha256", *family_columns,
        }
        if not reader.fieldnames or not required <= set(reader.fieldnames):
            raise DataQualityError("Phase 9C model dataset has an unexpected schema")
        for row in reader:
            if row["partition"] != "development":
                raise DataQualityError("Phase 9C comparison received a non-development row")
            formation = date.fromisoformat(row["formation_date"])
            if formation >= HOLDOUT_START:
                raise DataQualityError("Phase 9C comparison encountered a holdout row")
            key = formation, row["security_id"]
            if key in source_rows:
                raise DataQualityError("duplicate Phase 9C model-dataset row")
            source_rows[key] = row
            examples.append(Example(
                formation, row["calendar_month"], row["security_id"],
                float(row["label_centered_rank"]), float(row["benchmark_relative_return"]),
                float(row["sample_weight"]), tuple(float(row[column]) for column in family_columns),
                row["dataset_row_sha256"],
            ))
    if not examples:
        raise DataQualityError("Phase 9C model dataset is empty")
    return examples, source_rows


def _load_active_raw_panel(panel: Path, wanted: set[tuple[date, str]]) -> dict[tuple[date, str], list[float | None]]:
    result: dict[tuple[date, str], list[float | None]] = {}
    panel_columns = (
        "momentum_12_1_raw", "relative_strength_6m_raw", "realized_volatility_60d_raw",
        "earnings_yield_ttm_raw", "return_on_assets_ttm_raw",
    )
    with gzip.open(panel, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(panel_columns) <= set(reader.fieldnames):
            raise DataQualityError("Phase 9C feature panel cannot reconstruct active inputs")
        for row in reader:
            key = date.fromisoformat(row["formation_date"]), row["security_id"]
            if key not in wanted:
                continue
            values = [float(row[column]) if row[column] else None for column in panel_columns]
            # Reserve index three for the database-derived unadjusted liquidity value.
            result[key] = [values[0], values[1], values[2], None, values[3], values[4]]
    if set(result) != wanted:
        raise DataQualityError("Phase 9C feature panel is missing model-dataset rows")
    return result


def _load_static_sectors_and_liquidity(
    database_url: str, *, security_ids: Sequence[str], formations: Sequence[date],
) -> tuple[dict[str, str], dict[tuple[date, str], tuple[float | None, float | None, float | None]], str]:
    import psycopg

    sectors: dict[str, str] = {}
    bars: dict[str, list[tuple[date, float, float, str]]] = defaultdict(list)
    split_closes: dict[tuple[date, str], tuple[float, str]] = {}
    facts: dict[str, list[ActiveFact]] = defaultdict(list)
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute(
            """SELECT DISTINCT ON (security_id) security_id::text,sector_code,as_of_date,available_at
                 FROM quantrade.sector_classifications
                WHERE security_id=ANY(%s::uuid[])
                ORDER BY security_id,as_of_date DESC,available_at DESC""",
            (list(security_ids),),
        )
        sector_rows = list(cursor)
        for security_id, sector, _, _ in sector_rows:
            sectors[str(security_id)] = str(sector)
        if set(sectors) != set(security_ids):
            raise DataQualityError("static Tier-B sectors are incomplete for the active reference")
        cursor.execute(
            """SELECT daily_price_bar_id::text,security_id::text,session_date,close_price,volume
                 FROM quantrade.daily_price_bars
                WHERE security_id=ANY(%s::uuid[]) AND session='regular'
                  AND adjustment_basis='unadjusted' AND session_date <= %s
                ORDER BY security_id,session_date""",
            (list(security_ids), formations[-1]),
        )
        for bar_id, security_id, session, close, volume in cursor:
            if volume is not None:
                bars[str(security_id)].append((session, float(close), float(volume), str(bar_id)))
        cursor.execute(
            """SELECT daily_price_bar_id::text,security_id::text,session_date,close_price
                 FROM quantrade.daily_price_bars
                WHERE security_id=ANY(%s::uuid[]) AND session='regular'
                  AND adjustment_basis='split_adjusted' AND session_date=ANY(%s::date[])
                ORDER BY security_id,session_date""",
            (list(security_ids), list(formations)),
        )
        for bar_id, security_id, session, close in cursor:
            key = session, str(security_id)
            if key in split_closes:
                raise DataQualityError("duplicate split-adjusted active-reference close")
            split_closes[key] = float(close), str(bar_id)
        cursor.execute(
            """SELECT ff.security_id::text,ff.filing_fact_id::text,ff.filing_id::text,ff.taxonomy,ff.concept,ff.unit,
                      ff.fact_value,ff.period_start,ff.period_end,ff.available_at
                 FROM quantrade.filing_facts ff
                 JOIN quantrade.filings filing ON filing.filing_id=ff.filing_id
                WHERE ff.security_id=ANY(%s::uuid[]) AND ff.period_end <= %s
                  AND filing.form=ANY(%s)
                  AND (ff.taxonomy,ff.concept,ff.unit) IN (
                    ('us-gaap','NetIncomeLoss','USD'),('us-gaap','ProfitLoss','USD'),
                    ('us-gaap','Assets','USD'),('dei','EntityCommonStockSharesOutstanding','shares'))
                ORDER BY ff.security_id,ff.period_end,ff.available_at,ff.filing_id""",
            (list(security_ids), formations[-1], list(sorted(RESEARCH_RELEVANT_FORMS))),
        )
        for row in cursor:
            facts[str(row[0])].append(ActiveFact(
                str(row[1]), str(row[2]), str(row[3]), str(row[4]), str(row[5]), float(row[6]),
                row[7], row[8], row[9],
            ))
    active_values: dict[tuple[date, str], tuple[float | None, float | None, float | None]] = {}
    lineage: list[str] = []
    for security_id in security_ids:
        rows = bars.get(security_id, [])
        sessions = [item[0] for item in rows]
        for formation in formations:
            end = bisect_right(sessions, formation)
            window = rows[max(0, end - 20):end]
            if len(window) != 20 or window[-1][0] != formation:
                liquidity = None
            else:
                values = sorted(close * volume for _, close, volume, _ in window)
                liquidity = (values[9] + values[10]) / 2.0
                lineage.extend(item[3] for item in window)
            earnings_yield, return_on_assets, fact_lineage = _active_fundamentals(
                facts.get(security_id, ()), split_closes.get((formation, security_id)), formation,
            )
            lineage.extend(fact_lineage)
            active_values[formation, security_id] = liquidity, earnings_yield, return_on_assets
    source_hash = _canonical_hash({
        "static_sector_rows": [(str(row[0]), str(row[1]), str(row[2]), str(row[3])) for row in sector_rows],
        "liquidity_bar_ids": sorted(set(lineage)),
        "limitation": "current sectors are static Tier-B groupings, not historical point-in-time sectors",
    })
    return sectors, active_values, source_hash


def _active_fundamentals(
    facts: Sequence[ActiveFact], split_close: tuple[float, str] | None, formation: date,
) -> tuple[float | None, float | None, tuple[str, ...]]:
    """Replay the deployed v2 annual-fact semantics without using Phase 9C TTM values."""
    decision_at = datetime.combine(formation, time(20), ZoneInfo("America/Toronto"))
    eligible = [fact for fact in facts if fact.period_end <= formation and fact.available_at <= decision_at]
    annual: ActiveFact | None = None
    for concept in ("NetIncomeLoss", "ProfitLoss"):
        candidates = [
            fact for fact in eligible
            if fact.taxonomy == "us-gaap" and fact.concept == concept and fact.unit == "USD"
            and fact.period_start is not None and 330 <= (fact.period_end - fact.period_start).days <= 370
        ]
        if candidates:
            annual = max(candidates, key=lambda item: (item.period_end, item.available_at, item.filing_id))
            break
    if annual is None or annual.period_start is None:
        return None, None, ()
    lineage = [annual.fact_id]
    shares = [
        fact for fact in eligible
        if fact.taxonomy == "dei" and fact.concept == "EntityCommonStockSharesOutstanding"
        and fact.unit == "shares"
    ]
    share = max(shares, key=lambda item: (item.period_end, item.available_at, item.filing_id)) if shares else None
    earnings_yield = None
    if share is not None and share.value > 0 and split_close is not None and split_close[0] > 0:
        earnings_yield = annual.value / (split_close[0] * share.value)
        lineage.extend((share.fact_id, split_close[1]))
    assets = [
        fact for fact in eligible
        if fact.taxonomy == "us-gaap" and fact.concept == "Assets" and fact.unit == "USD"
    ]
    beginning = [fact for fact in assets if 0 <= (annual.period_start - fact.period_end).days <= 7]
    ending = [fact for fact in assets if fact.period_end == annual.period_end]
    beginning_fact = max(beginning, key=lambda item: (item.period_end, item.available_at, item.filing_id)) if beginning else None
    ending_fact = max(ending, key=lambda item: (item.period_end, item.available_at, item.filing_id)) if ending else None
    return_on_assets = None
    if beginning_fact is not None and ending_fact is not None and beginning_fact.value > 0 and ending_fact.value > 0:
        return_on_assets = annual.value / ((beginning_fact.value + ending_fact.value) / 2.0)
        lineage.extend((beginning_fact.fact_id, ending_fact.fact_id))
    return earnings_yield, return_on_assets, tuple(lineage)


def _tie_percentiles(values: Sequence[tuple[str, float]], direction: int) -> dict[str, float]:
    if len(values) < 2:
        return {}
    ordered = sorted(values, key=lambda item: (item[1], item[0]))
    denominator = len(ordered) - 1
    result: dict[str, float] = {}
    position = 0
    while position < len(ordered):
        end = position
        while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[position][1]:
            end += 1
        percentile = ((position + end) / 2.0) / denominator
        if direction < 0:
            percentile = 1.0 - percentile
        for security_id, _ in ordered[position:end + 1]:
            result[security_id] = percentile
        position = end + 1
    return result


def _attach_active_features(
    examples: Sequence[Example], raw: Mapping[tuple[date, str], list[float | None]],
    sectors: Mapping[str, str], active_values: Mapping[tuple[date, str], tuple[float | None, float | None, float | None]],
) -> list[Example]:
    by_formation: dict[date, list[Example]] = defaultdict(list)
    for example in examples:
        liquidity, earnings_yield, return_on_assets = active_values.get(
            (example.formation_date, example.security_id), (None, None, None),
        )
        raw[example.formation_date, example.security_id][3] = liquidity
        raw[example.formation_date, example.security_id][4] = earnings_yield
        raw[example.formation_date, example.security_id][5] = return_on_assets
        by_formation[example.formation_date].append(example)
    active: dict[tuple[date, str], tuple[float, ...] | None] = {}
    for formation, rows in by_formation.items():
        ranks: list[dict[str, float]] = []
        for column_index, direction in enumerate(ACTIVE_DIRECTIONS):
            ranked: dict[str, float] = {}
            sector_values: dict[str, list[tuple[str, float]]] = defaultdict(list)
            for row in rows:
                value = raw[formation, row.security_id][column_index]
                if value is not None:
                    sector_values[sectors[row.security_id]].append((row.security_id, value))
            for values in sector_values.values():
                ranked.update(_tie_percentiles(values, direction))
            ranks.append(ranked)
        for row in rows:
            values = tuple(rank.get(row.security_id) for rank in ranks)
            active[formation, row.security_id] = None if any(value is None for value in values) else tuple(
                float(value) for value in values if value is not None
            )
    return [Example(
        item.formation_date, item.calendar_month, item.security_id, item.target,
        item.relative_return, item.sample_weight, item.family_features,
        item.dataset_row_sha256, active[item.formation_date, item.security_id],
    ) for item in examples]


def _solve(matrix: list[list[float]], values: list[float]) -> tuple[float, ...]:
    size = len(values)
    augmented = [matrix[row][:] + [values[row]] for row in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise DataQualityError("singular Phase 9C model fit")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                current - factor * pivot_value
                for current, pivot_value in zip(augmented[row], augmented[column], strict=True)
            ]
    return tuple(augmented[row][-1] for row in range(size))


def _month_balanced_weights(rows: Sequence[Example]) -> list[float]:
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        totals[row.calendar_month] += row.sample_weight
    return [row.sample_weight / totals[row.calendar_month] for row in rows]


def fit_ridge(
    rows: Sequence[Example], *, penalty: float, feature_getter: Callable[[Example], Sequence[float] | None],
) -> LinearFit:
    selected = [(row, feature_getter(row)) for row in rows]
    selected = [(row, features) for row, features in selected if features is not None]
    if not selected:
        raise DataQualityError("ridge fit has no eligible examples")
    eligible_rows = [item[0] for item in selected]
    matrix = [tuple(float(value) for value in item[1]) for item in selected]
    weights = _month_balanced_weights(eligible_rows)
    total_weight = sum(weights)
    width = len(matrix[0])
    means = tuple(sum(weight * row[index] for weight, row in zip(weights, matrix)) / total_weight for index in range(width))
    variances = tuple(
        sum(weight * (row[index] - means[index]) ** 2 for weight, row in zip(weights, matrix)) / total_weight
        for index in range(width)
    )
    scales = tuple(max(math.sqrt(value), 1e-12) for value in variances)
    standardized = [tuple((value - means[index]) / scales[index] for index, value in enumerate(row)) for row in matrix]
    target_mean = sum(weight * row.target for weight, row in zip(weights, eligible_rows)) / total_weight
    gram = [[0.0] * width for _ in range(width)]
    rhs = [0.0] * width
    for weight, features, row in zip(weights, standardized, eligible_rows):
        centered_target = row.target - target_mean
        for left in range(width):
            rhs[left] += weight * features[left] * centered_target
            for right in range(width):
                gram[left][right] += weight * features[left] * features[right]
    for index in range(width):
        gram[index][index] += penalty
    return LinearFit(means, scales, target_mean, _solve(gram, rhs))


def _pair_rows(rows: Sequence[Example], getter: Callable[[Example], Sequence[float] | None]):
    by_formation: dict[date, list[tuple[Example, Sequence[float]]]] = defaultdict(list)
    for row in rows:
        features = getter(row)
        if features is not None:
            by_formation[row.formation_date].append((row, features))
    month_formations: dict[str, set[date]] = defaultdict(set)
    for formation, values in by_formation.items():
        month_formations[values[0][0].calendar_month].add(formation)
    for formation in sorted(by_formation):
        values = sorted(by_formation[formation], key=lambda item: (item[0].target, item[0].security_id))
        count = min(PAIR_COUNT_PER_FORMATION, len(values) // 2)
        if count == 0:
            continue
        month = values[0][0].calendar_month
        pair_weight = 1.0 / len(month_formations[month]) / count
        lower_size = len(values) // 2
        for index in range(count):
            lower_index = min(lower_size - 1, int(index * lower_size / count))
            upper_index = len(values) - 1 - lower_index
            yield values[upper_index][1], values[lower_index][1], pair_weight


def fit_pairwise(
    rows: Sequence[Example], *, penalty: float,
    feature_getter: Callable[[Example], Sequence[float] | None] = lambda row: row.family_features,
) -> LinearFit:
    selected = [row for row in rows if feature_getter(row) is not None]
    base = fit_ridge(selected, penalty=1.0, feature_getter=feature_getter)
    pairs = list(_pair_rows(selected, feature_getter))
    if not pairs:
        raise DataQualityError("pairwise fit has no eligible pairs")
    width = len(base.means)
    standardized_pairs: list[tuple[tuple[float, ...], float]] = []
    for upper, lower, weight in pairs:
        difference = tuple(
            ((upper[index] - base.means[index]) / base.scales[index])
            - ((lower[index] - base.means[index]) / base.scales[index])
            for index in range(width)
        )
        norm = math.sqrt(sum(value * value for value in difference))
        if norm > 1e-12:
            standardized_pairs.append((tuple(value / norm for value in difference), weight))
    coefficients = [0.0] * width
    for _ in range(50):
        gradient = [penalty * value for value in coefficients]
        hessian = [[penalty if left == right else 0.0 for right in range(width)] for left in range(width)]
        for difference, weight in standardized_pairs:
            margin = max(-40.0, min(40.0, sum(a * b for a, b in zip(coefficients, difference))))
            probability_error = 1.0 / (1.0 + math.exp(margin))
            curvature = probability_error * (1.0 - probability_error)
            for left in range(width):
                gradient[left] -= weight * probability_error * difference[left]
                for right in range(width):
                    hessian[left][right] += weight * curvature * difference[left] * difference[right]
        step = _solve(hessian, gradient)
        coefficients = [value - change for value, change in zip(coefficients, step)]
        if max(abs(value) for value in step) < 1e-9:
            break
    return LinearFit(base.means, base.scales, 0.0, tuple(coefficients))


def _ranks(values: Sequence[tuple[str, float]]) -> dict[str, float]:
    return _tie_percentiles(values, 1)


def spearman(rows: Sequence[tuple[str, float, float]]) -> float:
    if len(rows) < 2:
        raise DataQualityError("rank IC requires at least two examples")
    predicted = _ranks([(key, prediction) for key, prediction, _ in rows])
    actual = _ranks([(key, target) for key, _, target in rows])
    left = [predicted[key] for key, _, _ in rows]
    right = [actual[key] for key, _, _ in rows]
    left_mean, right_mean = fmean(left), fmean(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    denominator = math.sqrt(sum((a - left_mean) ** 2 for a in left) * sum((b - right_mean) ** 2 for b in right))
    return numerator / denominator if denominator else 0.0


def monthly_rank_ic(predictions: Sequence[Prediction]) -> tuple[float, dict[str, float]]:
    by_formation: dict[tuple[str, date], list[Prediction]] = defaultdict(list)
    for item in predictions:
        by_formation[item.example.calendar_month, item.example.formation_date].append(item)
    monthly_values: dict[str, list[float]] = defaultdict(list)
    for (month, _), rows in by_formation.items():
        monthly_values[month].append(spearman([
            (row.example.security_id, row.value, row.example.target) for row in rows
        ]))
    monthly = {month: fmean(values) for month, values in sorted(monthly_values.items())}
    return fmean(monthly.values()), monthly


def _rows_for(formations: Iterable[str], index: Mapping[date, list[Example]]) -> list[Example]:
    return [row for value in formations for row in index.get(date.fromisoformat(value), ())]


def _predict(
    model_key: str, outer_fold: int, model: LinearFit, rows: Sequence[Example],
    getter: Callable[[Example], Sequence[float] | None],
) -> list[Prediction]:
    return [
        Prediction(model_key, outer_fold, row, model.predict(features))
        for row in rows if (features := getter(row)) is not None
    ]


def _select_penalty(
    *, model_key: str, outer_fold: int, inner_folds: Sequence[Mapping[str, object]],
    index: Mapping[date, list[Example]], penalties: Sequence[float],
    fitter: Callable[[Sequence[Example], float], LinearFit],
    getter: Callable[[Example], Sequence[float] | None],
) -> tuple[float, list[dict[str, object]]]:
    scores: list[dict[str, object]] = []
    for penalty in penalties:
        inner_predictions: list[Prediction] = []
        fold_details: list[dict[str, object]] = []
        for inner in inner_folds:
            training = _rows_for(inner["training_formations"], index)
            validation = _rows_for(inner["validation_formations"], index)
            fit = fitter(training, penalty)
            predictions = _predict(model_key, outer_fold, fit, validation, getter)
            score, monthly = monthly_rank_ic(predictions)
            fold_details.append({"inner_fold": inner["inner_fold"], "mean_monthly_rank_ic": score, "monthly_rank_ic": monthly})
            inner_predictions.extend(predictions)
        aggregate, monthly = monthly_rank_ic(inner_predictions)
        scores.append({
            "penalty": penalty, "mean_monthly_rank_ic": aggregate,
            "monthly_rank_ic": monthly, "inner_folds": fold_details,
        })
    best = max(float(item["mean_monthly_rank_ic"]) for item in scores)
    selected = max(float(item["penalty"]) for item in scores if float(item["mean_monthly_rank_ic"]) >= best - INNER_TIE_TOLERANCE)
    return selected, scores


def _exact_deployed_fit(model: ActiveModelArtifact) -> LinearFit:
    if model.feature_columns != ACTIVE_MODEL_COLUMNS:
        raise DataQualityError("deployed artifact feature order differs from the frozen active reference")
    return LinearFit(model.feature_means, model.feature_scales, model.target_mean, model.coefficients)


def _active_artifact_hash(database_url: str, model_version: str) -> str:
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT artifact_sha256 FROM quantrade.model_artifacts WHERE model_version=%s",
            (model_version,),
        )
        row = cursor.fetchone()
    if row is None:
        raise DataQualityError("deployed active artifact is absent from its immutable registry")
    return str(row[0])


def _fit_document(fit: LinearFit) -> dict[str, object]:
    return {
        "feature_means": fit.means, "feature_scales": fit.scales,
        "target_mean": fit.target_mean, "coefficients": fit.coefficients,
    }


def run_comparison(
    *, database_url: str, dataset: Path, feature_panel: Path, destination: Path,
) -> dict[str, object]:
    dataset_manifest, folds = _validate_inputs(dataset)
    if _sha256_file(feature_panel) != dataset_manifest.get("source_panel_sha256"):
        raise DataQualityError("Phase 9C feature panel does not match the model-dataset provenance")
    examples, source_rows = _read_dataset(dataset)
    wanted = set(source_rows)
    raw = _load_active_raw_panel(feature_panel, wanted)
    formations = sorted({row.formation_date for row in examples})
    security_ids = sorted({row.security_id for row in examples})
    sectors, active_values, active_source_hash = _load_static_sectors_and_liquidity(
        database_url, security_ids=security_ids, formations=formations,
    )
    examples = _attach_active_features(examples, raw, sectors, active_values)
    active_eligible = sum(row.active_features is not None for row in examples)
    if active_eligible == 0:
        raise DataQualityError("the deployed active reference has no replayable rows")
    by_formation: dict[date, list[Example]] = defaultdict(list)
    for row in examples:
        by_formation[row.formation_date].append(row)

    deployed = load_active_model(database_url)
    deployed_artifact_hash = _active_artifact_hash(database_url, deployed.model_version)
    deployed_fit = _exact_deployed_fit(deployed)
    all_predictions: list[Prediction] = []
    fit_records: list[dict[str, object]] = []
    for outer in folds["outer_folds"]:
        outer_fold = int(outer["outer_fold"])
        training = _rows_for(outer["training_formations"], by_formation)
        validation = _rows_for(outer["validation_formations"], by_formation)
        all_predictions.extend(_predict(
            "deployed_active_exact", outer_fold, deployed_fit, validation,
            lambda row: row.active_features,
        ))

        active_penalty, active_tuning = _select_penalty(
            model_key="active_family_refit", outer_fold=outer_fold,
            inner_folds=outer["inner_folds"], index=by_formation, penalties=RIDGE_PENALTIES,
            fitter=lambda rows, penalty: fit_ridge(rows, penalty=penalty, feature_getter=lambda row: row.active_features),
            getter=lambda row: row.active_features,
        )
        active_fit = fit_ridge(training, penalty=active_penalty, feature_getter=lambda row: row.active_features)
        all_predictions.extend(_predict("active_family_refit", outer_fold, active_fit, validation, lambda row: row.active_features))

        ridge_penalty, ridge_tuning = _select_penalty(
            model_key="phase9c_family_ridge", outer_fold=outer_fold,
            inner_folds=outer["inner_folds"], index=by_formation, penalties=RIDGE_PENALTIES,
            fitter=lambda rows, penalty: fit_ridge(rows, penalty=penalty, feature_getter=lambda row: row.family_features),
            getter=lambda row: row.family_features,
        )
        ridge_fit = fit_ridge(training, penalty=ridge_penalty, feature_getter=lambda row: row.family_features)
        all_predictions.extend(_predict("phase9c_family_ridge", outer_fold, ridge_fit, validation, lambda row: row.family_features))

        pair_penalty, pair_tuning = _select_penalty(
            model_key="phase9c_pairwise_linear", outer_fold=outer_fold,
            inner_folds=outer["inner_folds"], index=by_formation, penalties=PAIRWISE_PENALTIES,
            fitter=lambda rows, penalty: fit_pairwise(rows, penalty=penalty),
            getter=lambda row: row.family_features,
        )
        pair_fit = fit_pairwise(training, penalty=pair_penalty)
        all_predictions.extend(_predict("phase9c_pairwise_linear", outer_fold, pair_fit, validation, lambda row: row.family_features))
        fit_records.append({
            "outer_fold": outer_fold,
            "training_formations": outer["training_formations"],
            "validation_formations": outer["validation_formations"],
            "deployed_active_exact": {"model_version": deployed.model_version, **_fit_document(deployed_fit)},
            "active_family_refit": {"selected_penalty": active_penalty, "tuning": active_tuning, **_fit_document(active_fit)},
            "phase9c_family_ridge": {"selected_penalty": ridge_penalty, "tuning": ridge_tuning, **_fit_document(ridge_fit)},
            "phase9c_pairwise_linear": {"selected_penalty": pair_penalty, "tuning": pair_tuning, **_fit_document(pair_fit)},
        })

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as raw_output:
        with gzip.GzipFile(fileobj=raw_output, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text_output:
                writer = csv.DictWriter(text_output, fieldnames=PREDICTION_COLUMNS, lineterminator="\n")
                writer.writeheader()
                for item in sorted(all_predictions, key=lambda value: (
                    value.model_key, value.outer_fold, value.example.formation_date, value.example.security_id,
                )):
                    writer.writerow({
                        "model_key": item.model_key, "outer_fold": item.outer_fold,
                        "formation_date": item.example.formation_date.isoformat(),
                        "calendar_month": item.example.calendar_month,
                        "security_id": item.example.security_id,
                        "prediction": format(item.value, ".17g"),
                        "label_centered_rank": format(item.example.target, ".17g"),
                        "benchmark_relative_return": format(item.example.relative_return, ".17g"),
                        "dataset_row_sha256": item.example.dataset_row_sha256,
                    })
    _, _, fits_path = _artifact_paths(dataset, destination)
    fits_document = {
        "comparison_key": COMPARISON_KEY, "comparison_version": COMPARISON_VERSION,
        "protocol": {
            "objective": "weekly cross-sectional centered-rank prediction",
            "ridge_penalties": RIDGE_PENALTIES, "pairwise_penalties": PAIRWISE_PENALTIES,
            "pair_count_per_formation": PAIR_COUNT_PER_FORMATION,
            "inner_tie_tolerance": INNER_TIE_TOLERANCE,
            "candidate_configuration_count": len(RIDGE_PENALTIES) + len(PAIRWISE_PENALTIES),
            "optional_additive_model_activated": False,
            "selection_data": "registered nested inner folds only",
            "outer_results_used_for_selection": False,
            "holdout_used": False,
        },
        "active_feature_columns": ACTIVE_MODEL_COLUMNS,
        "phase9c_family_columns": FAMILY_KEYS,
        "fits": fit_records,
    }
    fits_document["fits_sha256"] = _canonical_hash(fits_document)
    fits_path.write_text(json.dumps(fits_document, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    preliminary: dict[str, object] = {}
    for model_key in sorted({item.model_key for item in all_predictions}):
        selected = [item for item in all_predictions if item.model_key == model_key]
        score, monthly = monthly_rank_ic(selected)
        preliminary[model_key] = {
            "prediction_rows": len(selected), "mean_monthly_rank_ic": score,
            "monthly_rank_ic": monthly,
            "outer_fold_mean_monthly_rank_ic": {
                str(fold): monthly_rank_ic([item for item in selected if item.outer_fold == fold])[0]
                for fold in sorted({item.outer_fold for item in selected})
            },
        }
    manifest = {
        "comparison_key": COMPARISON_KEY, "comparison_version": COMPARISON_VERSION,
        "dataset_key": DATASET_KEY, "dataset_version": DATASET_VERSION,
        "dataset_sha256": _sha256_file(dataset), "dataset_manifest_hash": dataset_manifest.get("report_sha256"),
        "fold_sha256": folds["fold_sha256"], "active_model_version": deployed.model_version,
        "active_model_artifact_sha256": deployed_artifact_hash,
        "active_model_feature_registry_hash": deployed.feature_registry_hash,
        "active_reference_source_sha256": active_source_hash,
        "active_reference_limitation": "current sectors are static Tier-B groupings, not historical point-in-time sectors",
        "development_rows": len(examples), "active_reference_eligible_rows": active_eligible,
        "active_reference_coverage": active_eligible / len(examples),
        "prediction_rows": len(all_predictions), "prediction_file_sha256": _sha256_file(destination),
        "fits_file_sha256": _sha256_file(fits_path),
        "configuration_count": len(RIDGE_PENALTIES) + len(PAIRWISE_PENALTIES),
        "configuration_budget": 12, "holdout_used": False,
        "outer_results_used_for_selection": False,
        "status": "fitted_for_attribution_and_gate_evaluation",
        "preliminary_outer_diagnostics_not_for_tuning": preliminary,
    }
    manifest["report_hash"] = _canonical_hash(manifest)
    manifest_path = destination.with_suffix("") if destination.suffix == ".gz" else destination
    manifest_path = manifest_path.with_suffix(".json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit the nested Phase 9C weekly rank comparison")
    parser.add_argument("--dataset", type=Path, default=Path("data/derived/phase_9c_weekly_rank_development_v1.csv.gz"))
    parser.add_argument("--feature-panel", type=Path, default=Path("data/derived/phase_9c_weekly_feature_panel_v1.csv.gz"))
    parser.add_argument("--output", type=Path, default=Path("data/derived/phase_9c_nested_weekly_rank_predictions_v1.csv.gz"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    values = _dotenv_values(arguments.env_file)
    database_url = values.get("DATABASE_URL")
    if not database_url:
        raise DataQualityError("DATABASE_URL is required")
    report = run_comparison(
        database_url=database_url, dataset=arguments.dataset,
        feature_panel=arguments.feature_panel, destination=arguments.output,
    )
    print(
        f"comparison={report['comparison_key']}@{report['comparison_version']}; "
        f"predictions={report['prediction_rows']}; active_coverage={report['active_reference_coverage']:.4%}; "
        f"holdout_used={report['holdout_used']}"
    )


if __name__ == "__main__":
    main()
