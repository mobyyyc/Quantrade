"""Resumable, Tier-B historical daily-market-data backfill planning and execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from .alpaca import ALPACA_BARS_URL, AlpacaClient, AlpacaDailyBar, parse_daily_bars
from .historical_cohorts import CURRENT_SURVIVORS_COHORT, HistoricalCohortError
from .market_data import PostgresMarketDataRepository
from .security_master import FileRawArtifactStore


TORONTO = ZoneInfo("America/Toronto")
HISTORICAL_EOD_RULE_KEY = "alpaca_historical_eod_close"
HISTORICAL_MARKET_RULE_VERSION = "v1"
HISTORICAL_BENCHMARK_RULE_VERSION = "v1-benchmark"


@dataclass(frozen=True, slots=True)
class DateRange:
    start_date: date
    end_date: date


@dataclass(frozen=True, slots=True)
class HistoricalMarketChunk:
    start_date: date
    end_date: date
    symbols: tuple[str, ...]
    adjustment_basis: str

    @property
    def alpaca_adjustment(self) -> str:
        return "raw" if self.adjustment_basis == "unadjusted" else "split"

    @property
    def key(self) -> str:
        symbol_hash = sha256(",".join(self.symbols).encode("utf-8")).hexdigest()[:16]
        return f"{self.adjustment_basis}:{self.start_date.isoformat()}:{self.end_date.isoformat()}:{symbol_hash}"


@dataclass(frozen=True, slots=True)
class HistoricalBackfillRun:
    run_id: str
    data_domain: str


def historical_eod_available_at(session_date: date) -> datetime:
    """Use a conservative same-day close cutoff, independent of 2026 retrieval time."""
    return datetime.combine(session_date, time(18, 0), tzinfo=TORONTO).astimezone(timezone.utc)


def calendar_quarters(start_date: date, end_date: date) -> tuple[DateRange, ...]:
    if start_date > end_date:
        raise ValueError("historical backfill start date must not be after end date")
    ranges: list[DateRange] = []
    cursor = start_date
    while cursor <= end_date:
        quarter_end_month = ((cursor.month - 1) // 3 + 1) * 3
        if quarter_end_month == 12:
            quarter_end = date(cursor.year, 12, 31)
        else:
            next_month = date(cursor.year, quarter_end_month + 1, 1)
            quarter_end = date.fromordinal(next_month.toordinal() - 1)
        segment_end = min(quarter_end, end_date)
        ranges.append(DateRange(cursor, segment_end))
        cursor = date.fromordinal(segment_end.toordinal() + 1)
    return tuple(ranges)


def build_historical_market_chunks(
    symbols: Iterable[str], *, start_date: date, end_date: date, batch_size: int = 100,
) -> tuple[HistoricalMarketChunk, ...]:
    cleaned = tuple(sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()}))
    if not cleaned:
        raise ValueError("historical market backfill requires at least one symbol")
    if batch_size < 1 or batch_size > 100:
        raise ValueError("historical market backfill batch size must be between 1 and 100")
    chunks: list[HistoricalMarketChunk] = []
    for period in calendar_quarters(start_date, end_date):
        for index in range(0, len(cleaned), batch_size):
            batch = cleaned[index:index + batch_size]
            for basis in ("unadjusted", "split_adjusted"):
                chunks.append(HistoricalMarketChunk(period.start_date, period.end_date, batch, basis))
    return tuple(chunks)


class HistoricalMarketBackfillRepository:
    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
        except ImportError as error:  # pragma: no cover
            raise RuntimeError("Install quantrade-research dependencies before historical backfills") from error
        self._connection = psycopg.connect(database_url)

    def close(self) -> None:
        self._connection.close()

    def cohort_symbols(self, cohort_code: str) -> tuple[str, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT listing.ticker
                   FROM quantrade.research_cohorts AS cohort
                   JOIN quantrade.research_cohort_memberships AS membership
                     ON membership.research_cohort_id = cohort.research_cohort_id
                   JOIN LATERAL (
                     SELECT ticker FROM quantrade.listings
                     WHERE security_id = membership.security_id AND valid_to IS NULL
                     ORDER BY valid_from DESC LIMIT 1
                   ) AS listing ON true
                   WHERE cohort.cohort_code = %s
                   ORDER BY listing.ticker""",
                (cohort_code,),
            )
            symbols = tuple(str(row[0]) for row in cursor.fetchall())
        if len(symbols) != 500:
            raise HistoricalCohortError(f"{cohort_code} must resolve exactly 500 active listings; found {len(symbols)}")
        return symbols

    def start_or_resume_run(
        self, *, cohort_code: str, availability_rule_id: str, data_domain: str,
        start_date: date, end_date: date, requested_count: int,
    ) -> HistoricalBackfillRun:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT run.historical_backfill_run_id::text
                   FROM quantrade.historical_backfill_runs AS run
                   JOIN quantrade.research_cohorts AS cohort
                     ON cohort.research_cohort_id = run.research_cohort_id
                   WHERE cohort.cohort_code = %s AND run.availability_rule_id = %s
                     AND run.data_domain = %s AND run.start_date = %s AND run.end_date = %s
                     AND run.status = 'running'
                   ORDER BY run.started_at DESC LIMIT 1""",
                (cohort_code, availability_rule_id, data_domain, start_date, end_date),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    """INSERT INTO quantrade.historical_backfill_runs
                           (research_cohort_id, availability_rule_id, data_domain, provider,
                            start_date, end_date, status, requested_count)
                       SELECT research_cohort_id, %s, %s, 'alpaca', %s, %s, 'running', %s
                       FROM quantrade.research_cohorts WHERE cohort_code = %s
                       RETURNING historical_backfill_run_id::text""",
                    (availability_rule_id, data_domain, start_date, end_date, requested_count, cohort_code),
                )
                row = cursor.fetchone()
                if row is None:
                    raise HistoricalCohortError(f"no registered cohort exists for {cohort_code}")
            run_id = str(row[0])
        self._connection.commit()
        return HistoricalBackfillRun(run_id, data_domain)

    def ensure_chunks(self, run: HistoricalBackfillRun, chunks: Iterable[HistoricalMarketChunk]) -> None:
        with self._connection.cursor() as cursor:
            for chunk in chunks:
                cursor.execute(
                    """INSERT INTO quantrade.historical_backfill_chunks
                           (historical_backfill_run_id, chunk_key, start_date, end_date,
                            adjustment_basis, symbols, status)
                       VALUES (%s, %s, %s, %s, %s, %s::jsonb, 'pending')
                       ON CONFLICT (historical_backfill_run_id, chunk_key) DO NOTHING""",
                    (run.run_id, chunk.key, chunk.start_date, chunk.end_date,
                     chunk.adjustment_basis, json.dumps(chunk.symbols)),
                )
        self._connection.commit()

    def claim_chunk(self, run: HistoricalBackfillRun, chunk: HistoricalMarketChunk) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT status FROM quantrade.historical_backfill_chunks
                   WHERE historical_backfill_run_id = %s AND chunk_key = %s""",
                (run.run_id, chunk.key),
            )
            row = cursor.fetchone()
            if row is None:
                raise HistoricalCohortError(f"missing chunk {chunk.key}")
            if row[0] == 'completed':
                return False
            if row[0] in {'failed', 'skipped'}:
                raise HistoricalCohortError(f"historical chunk {chunk.key} has terminal status {row[0]}")
            cursor.execute(
                """UPDATE quantrade.historical_backfill_chunks
                   SET status = 'running', started_at = COALESCE(started_at, now())
                   WHERE historical_backfill_run_id = %s AND chunk_key = %s""",
                (run.run_id, chunk.key),
            )
        self._connection.commit()
        return True

    def complete_chunk(self, run: HistoricalBackfillRun, chunk: HistoricalMarketChunk, *, pages: int, persisted: int) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """UPDATE quantrade.historical_backfill_chunks
                   SET status = 'completed', completed_at = now(), raw_document_count = %s, persisted_count = %s
                   WHERE historical_backfill_run_id = %s AND chunk_key = %s AND status = 'running'""",
                (pages, persisted, run.run_id, chunk.key),
            )
            if cursor.rowcount != 1:
                raise HistoricalCohortError(f"historical chunk {chunk.key} could not be completed")
        self._connection.commit()

    def fail_chunk(self, run: HistoricalBackfillRun, chunk: HistoricalMarketChunk, reason: str) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """UPDATE quantrade.historical_backfill_chunks
                   SET status = 'failed', completed_at = now(), failure_reason = %s
                   WHERE historical_backfill_run_id = %s AND chunk_key = %s AND status = 'running'""",
                (reason[:1000], run.run_id, chunk.key),
            )
            cursor.execute(
                """UPDATE quantrade.historical_backfill_runs
                   SET status = 'failed', completed_at = now(), failure_reason = %s
                   WHERE historical_backfill_run_id = %s AND status = 'running'""",
                (reason[:1000], run.run_id),
            )
        self._connection.commit()

    def complete_run(self, run: HistoricalBackfillRun) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT COUNT(*) FILTER (WHERE status = 'completed'),
                          COUNT(*) FILTER (WHERE status <> 'completed'),
                          COALESCE(SUM(persisted_count), 0)
                   FROM quantrade.historical_backfill_chunks
                   WHERE historical_backfill_run_id = %s""",
                (run.run_id,),
            )
            completed, incomplete, persisted = cursor.fetchone()
            if incomplete:
                raise HistoricalCohortError(f"historical {run.data_domain} run still has {incomplete} incomplete chunks")
            cursor.execute(
                """UPDATE quantrade.historical_backfill_runs
                   SET status = 'completed', completed_at = now(), persisted_count = %s
                   WHERE historical_backfill_run_id = %s AND status = 'running'""",
                (persisted, run.run_id),
            )
        self._connection.commit()


def execute_historical_market_chunks(
    *, database_url: str, raw_artifacts_uri: str, alpaca_key_id: str, alpaca_secret_key: str,
    chunks: Iterable[HistoricalMarketChunk],
) -> tuple[int, int, int]:
    """Persist equity chunks and one matching raw/split SPY benchmark history per quarter."""
    chunk_list = tuple(chunks)
    if not chunk_list:
        return 0, 0, 0
    client = AlpacaClient(alpaca_key_id, alpaca_secret_key)
    store = FileRawArtifactStore(raw_artifacts_uri)
    repository = PostgresMarketDataRepository(database_url)
    ledger = HistoricalMarketBackfillRepository(database_url)
    page_count = 0
    bar_count = 0
    benchmark_count = 0
    try:
        rule_id = repository.availability_rule_id(
            HISTORICAL_EOD_RULE_KEY, HISTORICAL_MARKET_RULE_VERSION, "market_bar",
        )
        market_run = ledger.start_or_resume_run(
            cohort_code=CURRENT_SURVIVORS_COHORT, availability_rule_id=rule_id, data_domain="market_bar",
            start_date=min(chunk.start_date for chunk in chunk_list), end_date=max(chunk.end_date for chunk in chunk_list),
            requested_count=len(chunk_list),
        )
        ledger.ensure_chunks(market_run, chunk_list)
        for chunk in chunk_list:
            if not ledger.claim_chunk(market_run, chunk):
                continue
            token = None
            chunk_pages = 0
            chunk_bars = 0
            try:
                while True:
                    retrieved_at = datetime.now(timezone.utc)
                    payload = client.fetch_daily_bars(
                        list(chunk.symbols), chunk.start_date, chunk.end_date, chunk.alpaca_adjustment, token,
                    )
                    bars, token = parse_daily_bars(payload)
                    artifact = store.store(payload, retrieved_at, category="historical-market-data")
                    artifact_id = repository.persist_raw_artifact(artifact, ALPACA_BARS_URL)
                    persisted = repository.upsert_daily_bars(
                        bars, chunk.adjustment_basis, artifact_id, ALPACA_BARS_URL,
                        lambda bar: historical_eod_available_at(bar.session_date), rule_id,
                    )
                    chunk_bars += persisted
                    chunk_pages += 1
                    if token is None:
                        break
            except Exception as error:
                ledger.fail_chunk(market_run, chunk, str(error))
                raise
            ledger.complete_chunk(market_run, chunk, pages=chunk_pages, persisted=chunk_bars)
            page_count += chunk_pages
            bar_count += chunk_bars
        ledger.complete_run(market_run)
        benchmark_rule_id = repository.availability_rule_id(
            HISTORICAL_EOD_RULE_KEY, HISTORICAL_BENCHMARK_RULE_VERSION, "benchmark_bar",
        )
        benchmark_chunks = tuple(
            HistoricalMarketChunk(period_start, period_end, ("SPY",), basis)
            for period_start, period_end in sorted({(chunk.start_date, chunk.end_date) for chunk in chunk_list})
            for basis in ("unadjusted", "split_adjusted")
        )
        benchmark_run = ledger.start_or_resume_run(
            cohort_code=CURRENT_SURVIVORS_COHORT, availability_rule_id=benchmark_rule_id, data_domain="benchmark_bar",
            start_date=min(chunk.start_date for chunk in benchmark_chunks), end_date=max(chunk.end_date for chunk in benchmark_chunks),
            requested_count=len(benchmark_chunks),
        )
        ledger.ensure_chunks(benchmark_run, benchmark_chunks)
        for chunk in benchmark_chunks:
            if not ledger.claim_chunk(benchmark_run, chunk):
                continue
            token = None
            chunk_pages = 0
            chunk_bars = 0
            try:
                token = None
                while True:
                    retrieved_at = datetime.now(timezone.utc)
                    payload = client.fetch_daily_bars(["SPY"], chunk.start_date, chunk.end_date, chunk.alpaca_adjustment, token)
                    bars, token = parse_daily_bars(payload)
                    artifact = store.store(payload, retrieved_at, category="historical-benchmark-data")
                    artifact_id = repository.persist_raw_artifact(artifact, ALPACA_BARS_URL)
                    persisted = repository.upsert_benchmark_daily_bars(
                        bars, "SPY", chunk.adjustment_basis, artifact_id, ALPACA_BARS_URL,
                        lambda bar: historical_eod_available_at(bar.session_date), benchmark_rule_id,
                    )
                    chunk_bars += persisted
                    chunk_pages += 1
                    if token is None:
                        break
            except Exception as error:
                ledger.fail_chunk(benchmark_run, chunk, str(error))
                raise
            ledger.complete_chunk(benchmark_run, chunk, pages=chunk_pages, persisted=chunk_bars)
            page_count += chunk_pages
            benchmark_count += chunk_bars
        ledger.complete_run(benchmark_run)
    finally:
        repository.close()
        ledger.close()
    return page_count, bar_count, benchmark_count


def main() -> None:
    import argparse
    from .score_run import _settings

    parser = argparse.ArgumentParser(description="Backfill Tier-B historical market bars for the fixed current-survivors cohort")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-chunks", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--env-file", default=".env")
    arguments = parser.parse_args()
    settings = _settings(Path(arguments.env_file))
    settings.require_runtime_storage()
    settings.require_alpaca_access()
    assert settings.database_url and settings.raw_artifacts_uri and settings.alpaca_key_id and settings.alpaca_secret_key
    cohort_repository = HistoricalMarketBackfillRepository(settings.database_url)
    try:
        symbols = cohort_repository.cohort_symbols(CURRENT_SURVIVORS_COHORT)
    finally:
        cohort_repository.close()
    chunks = build_historical_market_chunks(
        symbols, start_date=arguments.start, end_date=arguments.end, batch_size=arguments.batch_size,
    )
    if arguments.max_chunks is not None:
        if arguments.max_chunks < 1:
            parser.error("--max-chunks must be positive")
        chunks = chunks[:arguments.max_chunks]
    if arguments.dry_run:
        print(json.dumps({"cohort": CURRENT_SURVIVORS_COHORT, "symbols": len(symbols), "chunks": len(chunks)}, sort_keys=True))
        return
    pages, bars, benchmark_bars = execute_historical_market_chunks(
        database_url=settings.database_url, raw_artifacts_uri=settings.raw_artifacts_uri,
        alpaca_key_id=settings.alpaca_key_id, alpaca_secret_key=settings.alpaca_secret_key, chunks=chunks,
    )
    print(f"cohort={CURRENT_SURVIVORS_COHORT}; chunks={len(chunks)}; pages={pages}; daily_bars={bars}; benchmark_bars={benchmark_bars}; availability=18:00_Toronto")


if __name__ == "__main__":
    main()
