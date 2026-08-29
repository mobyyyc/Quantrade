"""Run the approved baseline directly from the normalized PostgreSQL store.

This module intentionally fails closed.  A feature with missing or late data is
recorded as unavailable; it is never substituted with a guessed value.  The
result is an immutable score snapshot plus one immutable explanation row for
each required feature.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal
import os
from pathlib import Path
from typing import Callable, Iterable
from zoneinfo import ZoneInfo

from .active_model import load_active_model
from .config import Settings
from .feature_diagnostics import FeatureOutcome
from .features import FeatureRegistry, baseline_feature_registry
from .fundamentals import (
    FundamentalFactObservation,
    calculate_earnings_yield_ttm,
    calculate_return_on_assets_ttm,
)
from .ingest_security_master import _file_path_from_uri
from .momentum import (
    FeaturePriceObservation,
    calculate_momentum_12_1,
    calculate_relative_strength_6m,
)
from .ml_scoring import ModelFeatureContribution, build_model_feature_contributions, build_model_scores
from .quality import DataQualityError
from .ranking import SectorClassification, build_sector_aware_percentile_ranks
from .risk_liquidity import calculate_median_dollar_volume_20d, calculate_trailing_volatility_60d
from .run_manifest import RunManifest, SourceInput
from .sec_form_scope import RESEARCH_RELEVANT_FORMS
from .scoring import PostgresScoreSnapshotRepository, TORONTO, generate_end_of_day_scores
from .score_predictions import persist_score_predictions


def _dotenv_values(path: Path) -> dict[str, str]:
    """Read the local development file without printing any of its values."""
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _settings(env_file: Path | None) -> Settings:
    values = dict(os.environ)
    if env_file is not None:
        values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def _decision_at(score_date: date) -> datetime:
    return datetime.combine(score_date, time(20, 0), tzinfo=TORONTO)


def _outcome(
    security_id: str,
    formation_date: date,
    registry: FeatureRegistry,
    feature_key: str,
    calculator: Callable[[], object],
) -> FeatureOutcome:
    definitions = [definition for definition in registry.definitions() if definition.key == feature_key]
    if len(definitions) != 1:
        raise DataQualityError(f"baseline registry must contain exactly one active definition for {feature_key}")
    definition = definitions[0]
    try:
        value = calculator()
    except (DataQualityError, ArithmeticError, ValueError) as error:
        return FeatureOutcome(
            security_id, formation_date, definition.key, definition.version,
            definition.definition_hash, None, f"data_unavailable:{str(error)}",
        )
    return FeatureOutcome(
        security_id, formation_date, definition.key, definition.version,
        definition.definition_hash, value.value,  # type: ignore[attr-defined]
    )


def _load_universe(connection, universe_code: str, score_date: date, research_cohort_code: str | None = None) -> tuple[str, list[str]]:
    if research_cohort_code is not None:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT cohort.source_universe_snapshot_id::text
                   FROM quantrade.research_cohorts cohort
                   WHERE cohort.cohort_code = %s AND cohort.cohort_kind = 'current_survivors'
                     AND cohort.data_capability_tier = 'B' AND cohort.survivorship_biased
                     AND NOT cohort.historical_membership_verified
                     AND NOT cohort.sector_classification_point_in_time
                     AND cohort.status = 'active'""",
                (research_cohort_code,),
            )
            row = cursor.fetchone()
            if row is None or row[0] is None:
                raise DataQualityError(f"no active Tier-B current-survivors cohort exists for {research_cohort_code}")
            snapshot_id = str(row[0])
            cursor.execute(
                """SELECT membership.security_id::text
                   FROM quantrade.research_cohort_memberships membership
                   JOIN quantrade.research_cohorts cohort ON cohort.research_cohort_id = membership.research_cohort_id
                   WHERE cohort.cohort_code = %s ORDER BY membership.security_id""",
                (research_cohort_code,),
            )
            security_ids = [str(member[0]) for member in cursor.fetchall()]
        if not security_ids:
            raise DataQualityError(f"research cohort {research_cohort_code} has no members")
        return snapshot_id, security_ids
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT universe_snapshot_id FROM quantrade.universe_snapshots
               WHERE universe_code = %s AND as_of_date <= %s
               ORDER BY as_of_date DESC, ingested_at DESC LIMIT 1""",
            (universe_code, score_date),
        )
        row = cursor.fetchone()
        if row is None:
            raise DataQualityError(f"no {universe_code} universe snapshot is dated on or before {score_date}")
        snapshot_id = str(row[0])
        cursor.execute(
            "SELECT security_id::text FROM quantrade.universe_memberships WHERE universe_snapshot_id = %s ORDER BY security_id",
            (snapshot_id,),
        )
        security_ids = [str(row[0]) for row in cursor.fetchall()]
    if not security_ids:
        raise DataQualityError("selected universe has no members")
    return snapshot_id, security_ids


def _load_prices(connection, security_ids: Iterable[str], formation_date: date, decision_at: datetime) -> dict[str, list[FeaturePriceObservation]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT security_id::text, session_date, close_price, adjustment_basis, available_at, volume
               FROM quantrade.daily_price_bars
               WHERE security_id = ANY(%s::uuid[]) AND session = 'regular'
                 AND session_date <= %s AND available_at <= %s
               ORDER BY security_id, session_date""",
            (list(security_ids), formation_date, decision_at),
        )
        rows = cursor.fetchall()
    result: dict[str, list[FeaturePriceObservation]] = defaultdict(list)
    for row in rows:
        result[str(row[0])].append(FeaturePriceObservation(*row))
    return result


def _load_facts(connection, security_ids: Iterable[str], formation_date: date, decision_at: datetime) -> dict[str, list[FundamentalFactObservation]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT ff.security_id::text, ff.filing_id::text, ff.taxonomy, ff.concept, ff.unit, ff.fact_value,
                      ff.period_start, ff.period_end, ff.available_at
               FROM quantrade.filing_facts ff
               JOIN quantrade.filings filing ON filing.filing_id = ff.filing_id
               WHERE ff.security_id = ANY(%s::uuid[]) AND ff.period_end <= %s AND ff.available_at <= %s
                 AND filing.form = ANY(%s)
                 AND (ff.taxonomy, ff.concept, ff.unit) IN (
                    ('us-gaap', 'NetIncomeLoss', 'USD'),
                    ('us-gaap', 'ProfitLoss', 'USD'),
                    ('us-gaap', 'Assets', 'USD'),
                    ('dei', 'EntityCommonStockSharesOutstanding', 'shares')
                 )
               ORDER BY ff.security_id, ff.period_end, ff.available_at""",
            (list(security_ids), formation_date, decision_at, list(sorted(RESEARCH_RELEVANT_FORMS))),
        )
        rows = cursor.fetchall()
    result: dict[str, list[FundamentalFactObservation]] = defaultdict(list)
    for row in rows:
        result[str(row[0])].append(FundamentalFactObservation(*row))
    return result


def _load_sectors(connection, security_ids: Iterable[str], formation_date: date, decision_at: datetime,
                  static_tier_b_grouping: bool = False) -> list[SectorClassification]:
    with connection.cursor() as cursor:
        if static_tier_b_grouping:
            cursor.execute(
                """SELECT DISTINCT ON (security_id) security_id::text, sector_code, as_of_date, available_at
                   FROM quantrade.sector_classifications
                   WHERE security_id = ANY(%s::uuid[])
                   ORDER BY security_id, as_of_date DESC, available_at DESC""",
                (list(security_ids),),
            )
        else:
            cursor.execute(
                """SELECT DISTINCT ON (security_id) security_id::text, sector_code, as_of_date, available_at
                   FROM quantrade.sector_classifications
                   WHERE security_id = ANY(%s::uuid[]) AND as_of_date <= %s AND available_at <= %s
                   ORDER BY security_id, as_of_date DESC, available_at DESC""",
                (list(security_ids), formation_date, decision_at),
            )
        return [SectorClassification(*row) for row in cursor.fetchall()]


def _load_benchmark_prices(connection, ticker: str, formation_date: date, decision_at: datetime) -> list[FeaturePriceObservation]:
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT %s, session_date, close_price, adjustment_basis, available_at, volume
               FROM quantrade.benchmark_daily_price_bars
               WHERE benchmark_ticker = %s AND session = 'regular'
                 AND session_date <= %s AND available_at <= %s
               ORDER BY session_date""",
            (ticker, ticker, formation_date, decision_at),
        )
        return [FeaturePriceObservation(*row) for row in cursor.fetchall()]


def _source_inputs(connection, snapshot_id: str, security_ids: Iterable[str], formation_date: date, decision_at: datetime,
                   benchmark_ticker: str, static_tier_b_grouping: bool = False) -> tuple[SourceInput, ...]:
    """Collect the actual raw artifacts that contributed to this score run."""
    with connection.cursor() as cursor:
        cursor.execute(
            """WITH input_artifacts AS (
                   SELECT raw_artifact_id FROM quantrade.universe_snapshots WHERE universe_snapshot_id = %s
                   UNION
                   SELECT raw_artifact_id FROM quantrade.sector_classifications
                    WHERE security_id = ANY(%s::uuid[])
                      AND (%s OR (as_of_date <= %s AND available_at <= %s))
                   UNION
                   SELECT raw_artifact_id FROM quantrade.daily_price_bars
                    WHERE security_id = ANY(%s::uuid[]) AND session_date <= %s AND available_at <= %s
                   UNION
                   SELECT ff.raw_artifact_id FROM quantrade.filing_facts ff
                    JOIN quantrade.filings filing ON filing.filing_id = ff.filing_id
                    WHERE ff.security_id = ANY(%s::uuid[]) AND ff.period_end <= %s AND ff.available_at <= %s
                      AND filing.form = ANY(%s)
                   UNION
                   SELECT raw_artifact_id FROM quantrade.benchmark_daily_price_bars
                    WHERE benchmark_ticker = %s AND session_date <= %s AND available_at <= %s
               )
               SELECT provider, source_reference, storage_uri
               FROM quantrade.raw_artifacts
               WHERE raw_artifact_id IN (SELECT raw_artifact_id FROM input_artifacts)
               ORDER BY provider, source_reference, storage_uri""",
            (snapshot_id, list(security_ids), static_tier_b_grouping, formation_date, decision_at, list(security_ids), formation_date,
             decision_at, list(security_ids), formation_date, decision_at,
             list(sorted(RESEARCH_RELEVANT_FORMS)), benchmark_ticker, formation_date,
             decision_at),
        )
        rows = cursor.fetchall()
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for provider, source_reference, storage_uri in rows:
        grouped[(str(provider), str(source_reference))].append(str(storage_uri))
    if not grouped:
        raise DataQualityError("score run has no raw-artifact provenance")
    return tuple(
        SourceInput(provider=provider, source_reference=source_reference, raw_artifact_uris=tuple(uris))
        for (provider, source_reference), uris in grouped.items()
    )


def _persist_explanations(database_url: str, snapshots, contributions: Iterable[ModelFeatureContribution]) -> int:
    snapshot_ids = {snapshot.security_id: snapshot for snapshot in snapshots}
    inserted = 0
    import psycopg
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        for contribution in contributions:
            snapshot = snapshot_ids[contribution.security_id]
            cursor.execute(
                """SELECT score_snapshot_id FROM quantrade.score_snapshots
                   WHERE security_id = %s AND decision_at = %s AND model_version = %s
                     AND feature_version = %s AND protocol_version = %s""",
                snapshot.identity(),
            )
            score_snapshot_id = cursor.fetchone()[0]
            cursor.execute(
                """INSERT INTO quantrade.score_explanations
                   (score_snapshot_id, feature_key, feature_version, definition_hash, sector_code,
                    percentile, feature_weight, contribution, unavailable_reason)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (score_snapshot_id, feature_key, feature_version) DO NOTHING""",
                (score_snapshot_id, contribution.feature_key, contribution.feature_version,
                 contribution.definition_hash, contribution.sector_code, contribution.percentile,
                 contribution.weight, contribution.contribution, contribution.unavailable_reason),
            )
            inserted += cursor.rowcount
        connection.commit()
    return inserted


def run_score_generation(*, settings: Settings, score_date: date, universe_code: str, benchmark_ticker: str,
                         code_revision: str, manual: bool = False,
                         decision_at: datetime | None = None,
                         research_cohort_code: str | None = None) -> tuple[int, int]:
    """Calculate, rank, persist, and explain one active end-of-day model run."""
    settings.require_runtime_storage()
    assert settings.database_url is not None and settings.raw_artifacts_uri is not None
    decision_at = decision_at or (datetime.now(TORONTO) if manual else _decision_at(score_date))
    registry = baseline_feature_registry()
    import psycopg
    with psycopg.connect(settings.database_url) as connection:
        snapshot_id, security_ids = _load_universe(connection, universe_code, score_date, research_cohort_code)
        sectors = _load_sectors(connection, security_ids, score_date, decision_at,
                                static_tier_b_grouping=research_cohort_code is not None)
        prices = _load_prices(connection, security_ids, score_date, decision_at)
        facts = _load_facts(connection, security_ids, score_date, decision_at)
        benchmark_prices = _load_benchmark_prices(connection, benchmark_ticker, score_date, decision_at)
        source_inputs = _source_inputs(connection, snapshot_id, security_ids, score_date, decision_at, benchmark_ticker,
                                       static_tier_b_grouping=research_cohort_code is not None)

    outcomes: list[FeatureOutcome] = []
    for security_id in security_ids:
        security_prices = prices.get(security_id, [])
        security_facts = facts.get(security_id, [])
        outcomes.extend((
            _outcome(security_id, score_date, registry, "momentum_12_1", lambda p=security_prices, s=security_id: calculate_momentum_12_1(p, security_id=s, formation_date=score_date, decision_at=decision_at, registry=registry)),
            _outcome(security_id, score_date, registry, "relative_strength_6m", lambda p=security_prices, s=security_id: calculate_relative_strength_6m(p, benchmark_prices, security_id=s, benchmark_security_id=benchmark_ticker, formation_date=score_date, decision_at=decision_at, registry=registry)),
            _outcome(security_id, score_date, registry, "earnings_yield_ttm", lambda p=security_prices, f=security_facts, s=security_id: calculate_earnings_yield_ttm(f, p, security_id=s, formation_date=score_date, decision_at=decision_at, registry=registry)),
            _outcome(security_id, score_date, registry, "return_on_assets_ttm", lambda f=security_facts, s=security_id: calculate_return_on_assets_ttm(f, security_id=s, formation_date=score_date, decision_at=decision_at, registry=registry)),
            _outcome(security_id, score_date, registry, "trailing_volatility_60d", lambda p=security_prices, s=security_id: calculate_trailing_volatility_60d(p, security_id=s, formation_date=score_date, decision_at=decision_at, registry=registry)),
            _outcome(security_id, score_date, registry, "median_dollar_volume_20d", lambda p=security_prices, s=security_id: calculate_median_dollar_volume_20d(p, security_id=s, formation_date=score_date, decision_at=decision_at, registry=registry)),
        ))
    ranks = build_sector_aware_percentile_ranks(
        outcomes, sectors, formation_date=score_date, decision_at=decision_at,
        universe_security_ids=security_ids, registry=registry,
        allow_static_tier_b_grouping=research_cohort_code is not None,
    )
    model = load_active_model(settings.database_url)
    scores = build_model_scores(
        ranks=ranks, formation_date=score_date, universe_security_ids=security_ids,
        registry=registry, model=model,
    )
    repository = PostgresScoreSnapshotRepository(settings.database_url)
    try:
        snapshots = generate_end_of_day_scores(scores, repository, score_date=score_date, decision_at=decision_at,
                                               published_at=decision_at, data_cutoff_at=decision_at,
                                               data_capability_tier="B", manual=manual)
    finally:
        repository.close()
    prediction_count = persist_score_predictions(
        database_url=settings.database_url, snapshots=snapshots, scores=scores,
    )
    contributions = build_model_feature_contributions(
        ranks=ranks, formation_date=score_date, universe_security_ids=security_ids,
        registry=registry, model=model,
    )
    explanation_count = _persist_explanations(settings.database_url, snapshots, contributions)
    cohort_note = f"; research_cohort={research_cohort_code}; survivorship_biased=true; static_sector_grouping=true" if research_cohort_code else ""
    manifest = RunManifest.create(settings=settings, run_kind="score", code_revision=code_revision, data_capability_tier="B", decision_at=decision_at, status="completed", source_inputs=source_inputs, note=f"model={model.model_version}; universe={universe_code}; securities={len(security_ids)}; eligible={sum(score.eligible for score in scores)}; predictions_inserted={prediction_count}; explanations_inserted={explanation_count}; benchmark={benchmark_ticker}{cohort_note}")
    manifest.write(_file_path_from_uri(settings.raw_artifacts_uri) / "manifests" / f"{manifest.run_id}.json")
    return len(snapshots), sum(score.eligible for score in scores)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate one point-in-time active-model score snapshot")
    parser.add_argument("--score-date", type=date.fromisoformat, required=True)
    parser.add_argument("--universe-code", default="sp500")
    parser.add_argument("--benchmark-ticker", default="SPY")
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--manual", action="store_true", help="Use the current post-close timestamp for a private manual run")
    parser.add_argument("--decision-at", type=datetime.fromisoformat,
                        help="Canonical post-close timestamp supplied by the daily-update ledger")
    arguments = parser.parse_args()
    snapshots, eligible = run_score_generation(settings=_settings(arguments.env_file), score_date=arguments.score_date, universe_code=arguments.universe_code, benchmark_ticker=arguments.benchmark_ticker.upper(), code_revision=arguments.code_revision, manual=arguments.manual, decision_at=arguments.decision_at)
    print(f"score_snapshots={snapshots}; eligible={eligible}")


if __name__ == "__main__":
    main()
