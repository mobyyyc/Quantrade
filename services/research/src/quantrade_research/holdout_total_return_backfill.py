"""Backfill provider total-return bars solely for locked-holdout accounting."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path

from .historical_cohorts import CURRENT_SURVIVORS_COHORT
from .historical_market_backfill import (
    FREE_TRACK_HOLDOUT_END_DATE,
    FREE_TRACK_HOLDOUT_START_DATE,
    HistoricalMarketBackfillRepository,
    build_historical_market_chunks,
    execute_historical_market_chunks,
    validate_free_track_backfill_window,
)


EQUITY_RULE_VERSION = "v1-total-return-holdout"
BENCHMARK_RULE_VERSION = "v1-total-return-holdout-benchmark"


def retrieved_ex_post(_: date) -> datetime:
    """Total-return adjustments are evaluation evidence, never decision-time input."""
    return datetime.now(timezone.utc)


def main() -> None:
    from .score_run import _settings

    parser = argparse.ArgumentParser(
        description="Backfill Alpaca adjustment=all bars for frozen holdout execution accounting"
    )
    parser.add_argument("--start", type=date.fromisoformat, default=FREE_TRACK_HOLDOUT_START_DATE)
    parser.add_argument("--end", type=date.fromisoformat, default=FREE_TRACK_HOLDOUT_END_DATE)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--env-file", default=".env")
    arguments = parser.parse_args()
    validate_free_track_backfill_window(arguments.start, arguments.end)
    settings = _settings(Path(arguments.env_file))
    settings.require_runtime_storage()
    settings.require_alpaca_access()
    assert settings.database_url and settings.raw_artifacts_uri and settings.alpaca_key_id and settings.alpaca_secret_key
    repository = HistoricalMarketBackfillRepository(settings.database_url)
    try:
        symbols = repository.cohort_symbols(CURRENT_SURVIVORS_COHORT)
    finally:
        repository.close()
    chunks = build_historical_market_chunks(
        symbols,
        start_date=arguments.start,
        end_date=arguments.end,
        batch_size=arguments.batch_size,
        adjustment_bases=("total_return_adjusted",),
    )
    if arguments.dry_run:
        print(json.dumps({"cohort": CURRENT_SURVIVORS_COHORT, "symbols": len(symbols), "chunks": len(chunks), "adjustment": "all"}, sort_keys=True))
        return
    pages, bars, benchmark_bars = execute_historical_market_chunks(
        database_url=settings.database_url,
        raw_artifacts_uri=settings.raw_artifacts_uri,
        alpaca_key_id=settings.alpaca_key_id,
        alpaca_secret_key=settings.alpaca_secret_key,
        chunks=chunks,
        market_rule_version=EQUITY_RULE_VERSION,
        benchmark_rule_version=BENCHMARK_RULE_VERSION,
        bar_available_at=retrieved_ex_post,
    )
    print(
        f"cohort={CURRENT_SURVIVORS_COHORT}; chunks={len(chunks)}; pages={pages}; "
        f"daily_bars={bars}; benchmark_bars={benchmark_bars}; adjustment=all; usage=holdout_only"
    )


if __name__ == "__main__":
    main()
