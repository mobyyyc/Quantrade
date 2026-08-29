"""Targeted, compact historical corporate-action ingestion for SPY."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from pathlib import Path

from .alpaca import ALPACA_CORPORATE_ACTIONS_URL, AlpacaClient, parse_corporate_actions
from .historical_corporate_action_backfill import HISTORICAL_ACTION_RULE_VERSION
from .historical_market_backfill import (
    FREE_TRACK_HOLDOUT_END_DATE,
    FREE_TRACK_START_DATE,
    HISTORICAL_EOD_RULE_KEY,
    calendar_quarters,
    historical_eod_available_at,
    validate_free_track_backfill_window,
)
from .market_data import PostgresMarketDataRepository


PARSER_VERSION = "alpaca_benchmark_corporate_actions_v1"


def backfill_benchmark_corporate_actions(
    *, database_url: str, alpaca_key_id: str, alpaca_secret_key: str,
    start_date: date, end_date: date, benchmark_ticker: str = "SPY",
) -> tuple[int, int, int]:
    client = AlpacaClient(alpaca_key_id, alpaca_secret_key)
    repository = PostgresMarketDataRepository(database_url)
    pages = fetched = persisted = 0
    try:
        rule_id = repository.availability_rule_id(
            HISTORICAL_EOD_RULE_KEY, HISTORICAL_ACTION_RULE_VERSION, "corporate_action",
        )
        for interval in calendar_quarters(start_date, end_date):
            token = None
            while True:
                retrieved_at = datetime.now(timezone.utc)
                payload = client.fetch_corporate_actions(
                    [benchmark_ticker], interval.start_date, interval.end_date, token,
                )
                actions, token = parse_corporate_actions(payload)
                fetched += len(actions)
                receipt = repository.persist_compact_receipt(
                    payload,
                    f"{ALPACA_CORPORATE_ACTIONS_URL}?symbol={benchmark_ticker}&start={interval.start_date}&end={interval.end_date}",
                    "alpaca_corporate_actions",
                    retrieved_at,
                    parser_version=PARSER_VERSION,
                )
                persisted += repository.insert_benchmark_corporate_actions(
                    benchmark_ticker=benchmark_ticker,
                    actions=actions,
                    raw_artifact_id=receipt.raw_artifact_id,
                    source_reference=ALPACA_CORPORATE_ACTIONS_URL,
                    source_receipt_id=receipt.source_receipt_id,
                    availability_rule_id=rule_id,
                    available_at=lambda action: historical_eod_available_at(action.process_date),
                )
                pages += 1
                if token is None:
                    break
    finally:
        repository.close()
    return pages, fetched, persisted


def main() -> None:
    from .score_run import _settings

    parser = argparse.ArgumentParser(description="Backfill compact SPY corporate-action metadata")
    parser.add_argument("--start", type=date.fromisoformat, default=FREE_TRACK_START_DATE)
    parser.add_argument("--end", type=date.fromisoformat, default=FREE_TRACK_HOLDOUT_END_DATE)
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    validate_free_track_backfill_window(arguments.start, arguments.end)
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    settings.require_alpaca_access()
    assert settings.database_url and settings.alpaca_key_id and settings.alpaca_secret_key
    pages, fetched, persisted = backfill_benchmark_corporate_actions(
        database_url=settings.database_url,
        alpaca_key_id=settings.alpaca_key_id,
        alpaca_secret_key=settings.alpaca_secret_key,
        start_date=arguments.start,
        end_date=arguments.end,
        benchmark_ticker=arguments.benchmark.upper(),
    )
    print(
        f"benchmark={arguments.benchmark.upper()}; pages={pages}; fetched_actions={fetched}; "
        f"persisted_actions={persisted}; payload_retained=false"
    )


if __name__ == "__main__":
    main()
