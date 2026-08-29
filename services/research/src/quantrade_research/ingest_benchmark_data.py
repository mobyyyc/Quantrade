"""Fetch and persist benchmark bars without misclassifying an ETF as a stock."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from pathlib import Path

from .alpaca import (
    ALPACA_BARS_URL, ALPACA_CORPORATE_ACTIONS_URL,
    AlpacaClient, parse_corporate_actions, parse_daily_bars,
)
from .config import Settings
from .ingest_security_master import _file_path_from_uri
from .market_data import PostgresMarketDataRepository, record_market_source
from .run_manifest import RunManifest, SourceInput
from .security_master import FileRawArtifactStore


_ALPACA_PARSER_VERSION = "alpaca_parser_v1"
_ALPACA_ACTION_PARSER_VERSION = "alpaca_benchmark_corporate_actions_v1"


def _should_fetch_adjustment(
    repository: PostgresMarketDataRepository, ticker: str, end: date,
    adjustment_basis: str, only_missing: bool,
) -> bool:
    return not only_missing or not repository.benchmark_bar_exists(ticker, end, adjustment_basis)


def _source_inputs_for_artifacts(artifact_uris: list[str]) -> tuple[SourceInput, ...]:
    """Return provenance only for data retrieved by this invocation.

    A missing-only retry can legitimately retrieve nothing because an earlier
    attempt already committed every requested benchmark bar. That is a
    successful no-op, not an ingestion run with fabricated source lineage.
    """
    if not artifact_uris:
        return ()
    return (
        SourceInput(
            provider="alpaca", source_reference=ALPACA_BARS_URL,
            raw_artifact_uris=tuple(artifact_uris),
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest raw, split-adjusted, and total-return benchmark bars")
    parser.add_argument("--ticker", default="SPY")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--corporate-actions-start", type=date.fromisoformat,
        help="Inclusive action catch-up boundary; defaults to --start",
    )
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument(
        "--compact-receipts", action="store_true",
        help="Store source metadata receipts without routine payload files",
    )
    parser.add_argument(
        "--only-missing", action="store_true",
        help="Skip an adjustment basis already recorded for the requested end date",
    )
    arguments = parser.parse_args()
    if arguments.start > arguments.end:
        parser.error("--start must be on or before --end")
    action_start = arguments.corporate_actions_start or arguments.start
    if action_start > arguments.end:
        parser.error("--corporate-actions-start must be on or before --end")
    # Import here to keep the normal command path's settings contract in one place.
    from .score_run import _settings

    settings = _settings(Path(arguments.env_file))
    settings.require_runtime_storage()
    settings.require_alpaca_access()
    assert settings.database_url and settings.raw_artifacts_uri and settings.alpaca_key_id and settings.alpaca_secret_key
    ticker = arguments.ticker.upper()
    client = AlpacaClient(settings.alpaca_key_id, settings.alpaca_secret_key)
    store = FileRawArtifactStore(settings.raw_artifacts_uri)
    artifact_uris: list[str] = []
    count = 0
    fetched_adjustments = 0
    skipped_existing_adjustments = 0
    action_count = 0
    action_pages = 0
    repository = PostgresMarketDataRepository(settings.database_url)
    try:
        availability_rule_id = repository.availability_rule_id(
            "alpaca_retrieval", "v1-benchmark", "benchmark_bar",
        )
        for adjustment, basis in (
            ("raw", "unadjusted"), ("split", "split_adjusted"), ("all", "total_return_adjusted"),
        ):
            if not _should_fetch_adjustment(repository, ticker, arguments.end, basis, arguments.only_missing):
                skipped_existing_adjustments += 1
                continue
            fetched_adjustments += 1
            token = None
            while True:
                retrieved_at = datetime.now(timezone.utc)
                payload = client.fetch_daily_bars([ticker], arguments.start, arguments.end, adjustment, token)
                bars, token = parse_daily_bars(payload)
                source = record_market_source(
                    repository, store, payload, retrieved_at, ALPACA_BARS_URL,
                    response_category="alpaca_daily_bars", raw_category="benchmark-market-data",
                    compact_receipts=arguments.compact_receipts, parser_version=_ALPACA_PARSER_VERSION,
                )
                artifact_uris.append(source.storage_uri)
                count += repository.upsert_benchmark_daily_bars(
                    bars, ticker, basis, source.raw_artifact_id, ALPACA_BARS_URL,
                    retrieved_at, availability_rule_id, source_receipt_id=source.source_receipt_id,
                    skip_existing=arguments.only_missing,
                )
                if token is None:
                    break
        action_rule_id = repository.availability_rule_id(
            "alpaca_retrieval", "v1-benchmark-corporate-action", "corporate_action",
        )
        token = None
        while True:
            retrieved_at = datetime.now(timezone.utc)
            payload = client.fetch_corporate_actions([ticker], action_start, arguments.end, token)
            actions, token = parse_corporate_actions(payload)
            source = record_market_source(
                repository, store, payload, retrieved_at, ALPACA_CORPORATE_ACTIONS_URL,
                response_category="alpaca_corporate_actions", raw_category="benchmark-corporate-actions",
                compact_receipts=arguments.compact_receipts, parser_version=_ALPACA_ACTION_PARSER_VERSION,
            )
            artifact_uris.append(source.storage_uri)
            action_count += repository.insert_benchmark_corporate_actions(
                benchmark_ticker=ticker, actions=actions,
                raw_artifact_id=source.raw_artifact_id,
                source_reference=ALPACA_CORPORATE_ACTIONS_URL,
                source_receipt_id=source.source_receipt_id,
                availability_rule_id=action_rule_id, available_at=retrieved_at,
            )
            action_pages += 1
            if token is None:
                break
    finally:
        repository.close()
    note = (
        f"benchmark={ticker}; daily_bars={count}; adjustment_bases=unadjusted,split_adjusted,total_return_adjusted; "
        f"request_mode={'missing_only' if arguments.only_missing else 'range'}; "
        f"fetched_adjustments={fetched_adjustments}; skipped_existing_adjustments={skipped_existing_adjustments}; "
        f"corporate_actions={action_count}; corporate_action_pages={action_pages}; "
        f"corporate_action_window={action_start}:{arguments.end}; "
        f"receipt_mode={'compact' if arguments.compact_receipts else 'payload_retained'}"
    )
    source_inputs = _source_inputs_for_artifacts(artifact_uris)
    if not source_inputs:
        print(f"{note}; no_op=all_requested_adjustments_already_present")
        return
    manifest = RunManifest.create(
        settings=settings,
        run_kind="ingestion",
        code_revision=arguments.code_revision,
        data_capability_tier="B",
        status="completed",
        source_inputs=source_inputs,
        note=note,
    )
    manifest.write(_file_path_from_uri(settings.raw_artifacts_uri) / "manifests" / f"{manifest.run_id}.json")
    print(manifest.note)


if __name__ == "__main__":
    main()
