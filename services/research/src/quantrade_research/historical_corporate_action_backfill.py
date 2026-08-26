"""Resumable Tier-B Alpaca corporate-action backfill for the fixed cohort."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path

from .alpaca import ALPACA_CORPORATE_ACTIONS_URL, AlpacaClient, parse_corporate_actions
from .historical_cohorts import CURRENT_SURVIVORS_COHORT
from .historical_market_backfill import (
    FREE_TRACK_HOLDOUT_END_DATE,
    FREE_TRACK_START_DATE,
    HISTORICAL_EOD_RULE_KEY,
    HistoricalMarketBackfillRepository,
    HistoricalMarketChunk,
    calendar_quarters,
    historical_eod_available_at,
    validate_free_track_backfill_window,
)
from .market_data import PostgresMarketDataRepository
from .security_master import FileRawArtifactStore


HISTORICAL_ACTION_RULE_VERSION = "v1-corporate-action"


def build_historical_corporate_action_chunks(symbols: tuple[str, ...], *, start_date: date, end_date: date, batch_size: int = 100) -> tuple[HistoricalMarketChunk, ...]:
    if batch_size < 1 or batch_size > 100:
        raise ValueError("historical corporate-action batch size must be between 1 and 100")
    chunks: list[HistoricalMarketChunk] = []
    for interval in calendar_quarters(start_date, end_date):
        for index in range(0, len(symbols), batch_size):
            chunks.append(HistoricalMarketChunk(interval.start_date, interval.end_date, symbols[index:index + batch_size], "unadjusted"))
    return tuple(chunks)


def execute_historical_corporate_action_chunks(*, database_url: str, raw_artifacts_uri: str, alpaca_key_id: str, alpaca_secret_key: str, chunks: tuple[HistoricalMarketChunk, ...]) -> tuple[int, int]:
    client = AlpacaClient(alpaca_key_id, alpaca_secret_key)
    store = FileRawArtifactStore(raw_artifacts_uri)
    repository = PostgresMarketDataRepository(database_url)
    ledger = HistoricalMarketBackfillRepository(database_url)
    pages = actions_persisted = 0
    try:
        rule_id = repository.availability_rule_id(HISTORICAL_EOD_RULE_KEY, HISTORICAL_ACTION_RULE_VERSION, "corporate_action")
        run = ledger.start_or_resume_run(
            cohort_code=CURRENT_SURVIVORS_COHORT, availability_rule_id=rule_id, data_domain="corporate_action",
            start_date=min(chunk.start_date for chunk in chunks), end_date=max(chunk.end_date for chunk in chunks), requested_count=len(chunks),
        )
        ledger.ensure_chunks(run, chunks)
        for chunk in chunks:
            if not ledger.claim_chunk(run, chunk):
                continue
            token = None
            chunk_pages = chunk_actions = 0
            try:
                while True:
                    retrieved_at = datetime.now(timezone.utc)
                    payload = client.fetch_corporate_actions(list(chunk.symbols), chunk.start_date, chunk.end_date, token)
                    actions, token = parse_corporate_actions(payload)
                    artifact = store.store(payload, retrieved_at, category="historical-corporate-actions")
                    artifact_id = repository.persist_raw_artifact(artifact, ALPACA_CORPORATE_ACTIONS_URL)
                    chunk_actions += repository.upsert_corporate_actions(
                        actions, artifact_id, ALPACA_CORPORATE_ACTIONS_URL,
                        lambda action: historical_eod_available_at(action.process_date),
                        skip_unmapped=True,
                    )
                    chunk_pages += 1
                    if token is None:
                        break
            except Exception as error:
                ledger.fail_chunk(run, chunk, str(error))
                raise
            ledger.complete_chunk(run, chunk, pages=chunk_pages, persisted=chunk_actions)
            pages += chunk_pages
            actions_persisted += chunk_actions
        ledger.complete_run(run)
    finally:
        repository.close()
        ledger.close()
    return pages, actions_persisted


def main() -> None:
    from .score_run import _settings

    parser = argparse.ArgumentParser(description="Backfill Tier-B historical corporate actions for the fixed current-survivors cohort")
    parser.add_argument("--start", type=date.fromisoformat, default=FREE_TRACK_START_DATE)
    parser.add_argument("--end", type=date.fromisoformat, default=FREE_TRACK_HOLDOUT_END_DATE)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-chunks", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()
    validate_free_track_backfill_window(args.start, args.end)
    settings = _settings(Path(args.env_file))
    settings.require_runtime_storage()
    settings.require_alpaca_access()
    assert settings.database_url and settings.raw_artifacts_uri and settings.alpaca_key_id and settings.alpaca_secret_key
    ledger = HistoricalMarketBackfillRepository(settings.database_url)
    try:
        symbols = ledger.cohort_symbols(CURRENT_SURVIVORS_COHORT)
    finally:
        ledger.close()
    chunks = build_historical_corporate_action_chunks(symbols, start_date=args.start, end_date=args.end, batch_size=args.batch_size)
    if args.max_chunks is not None:
        if args.max_chunks < 1:
            parser.error("--max-chunks must be positive")
        chunks = chunks[:args.max_chunks]
    if args.dry_run:
        print(json.dumps({"cohort": CURRENT_SURVIVORS_COHORT, "symbols": len(symbols), "chunks": len(chunks), "data_domain": "corporate_action"}, sort_keys=True))
        return
    pages, actions = execute_historical_corporate_action_chunks(
        database_url=settings.database_url, raw_artifacts_uri=settings.raw_artifacts_uri,
        alpaca_key_id=settings.alpaca_key_id, alpaca_secret_key=settings.alpaca_secret_key, chunks=chunks,
    )
    print(f"cohort={CURRENT_SURVIVORS_COHORT}; chunks={len(chunks)}; pages={pages}; corporate_actions={actions}; tier=B")


if __name__ == "__main__":
    main()
