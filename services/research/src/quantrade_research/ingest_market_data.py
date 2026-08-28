"""Fetch and persist Alpaca daily bars and corporate actions for a symbol set."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone

from .alpaca import (
    ALPACA_BARS_URL,
    ALPACA_CORPORATE_ACTIONS_URL,
    AlpacaClient,
    parse_corporate_actions,
    parse_daily_bars,
)
from .config import Settings
from .ingest_security_master import _file_path_from_uri
from .market_data import PostgresMarketDataRepository, record_market_source
from .run_manifest import RunManifest, SourceInput
from .security_master import FileRawArtifactStore


_ALPACA_PARSER_VERSION = "alpaca_parser_v1"


def _symbols(value: str) -> list[str]:
    symbols = [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]
    if not symbols:
        raise argparse.ArgumentTypeError("at least one symbol is required")
    return symbols


def _symbols_to_fetch(
    repository: PostgresMarketDataRepository, symbols: list[str], start: date, end: date,
    adjustment_basis: str, only_missing: bool,
) -> list[str]:
    if not only_missing:
        return symbols
    return repository.symbols_missing_daily_bars(symbols, start, end, adjustment_basis)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Alpaca daily bars and corporate actions")
    parser.add_argument("--symbols", type=_symbols, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--corporate-actions-start", type=date.fromisoformat,
        help="Inclusive source-retrieval boundary for corporate actions; defaults to --start",
    )
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument(
        "--compact-receipts", action="store_true",
        help="Store source metadata receipts without routine payload files",
    )
    parser.add_argument(
        "--only-missing", action="store_true",
        help="Request only listings that lack a bar for a known SPY session",
    )
    arguments = parser.parse_args()
    if arguments.batch_size < 1:
        parser.error("--batch-size must be positive")
    action_start = arguments.corporate_actions_start or arguments.start
    if action_start > arguments.end:
        parser.error("--corporate-actions-start must be on or before --end")

    settings = Settings.from_environment()
    settings.require_runtime_storage()
    settings.require_alpaca_access()
    assert settings.database_url is not None
    assert settings.raw_artifacts_uri is not None
    assert settings.alpaca_key_id is not None
    assert settings.alpaca_secret_key is not None

    client = AlpacaClient(settings.alpaca_key_id, settings.alpaca_secret_key)
    artifact_store = FileRawArtifactStore(settings.raw_artifacts_uri)
    repository = PostgresMarketDataRepository(settings.database_url)
    artifact_uris: list[str] = []
    bar_count = 0
    action_count = 0
    bar_request_symbols = 0
    skipped_existing_symbols = 0
    bar_pages = 0
    action_pages = 0
    action_request_symbols = 0
    try:
        availability_rule_id = repository.availability_rule_id("alpaca_retrieval", "v1", "market_bar")
        batches = [
            arguments.symbols[index:index + arguments.batch_size]
            for index in range(0, len(arguments.symbols), arguments.batch_size)
        ]
        for symbols in batches:
            for adjustment, basis in (("raw", "unadjusted"), ("split", "split_adjusted")):
                request_symbols = _symbols_to_fetch(
                    repository, symbols, arguments.start, arguments.end, basis, arguments.only_missing,
                )
                skipped_existing_symbols += len(symbols) - len(request_symbols)
                if not request_symbols:
                    continue
                bar_request_symbols += len(request_symbols)
                token = None
                while True:
                    retrieved_at = datetime.now(timezone.utc)
                    payload = client.fetch_daily_bars(request_symbols, arguments.start, arguments.end, adjustment, token)
                    bars, token = parse_daily_bars(payload)
                    bar_pages += 1
                    source = record_market_source(
                        repository, artifact_store, payload, retrieved_at, ALPACA_BARS_URL,
                        response_category="alpaca_daily_bars", raw_category="market-data",
                        compact_receipts=arguments.compact_receipts, parser_version=_ALPACA_PARSER_VERSION,
                    )
                    artifact_uris.append(source.storage_uri)
                    bar_count += repository.upsert_daily_bars(
                        bars, basis,
                        source.raw_artifact_id, ALPACA_BARS_URL, retrieved_at, availability_rule_id,
                        source_receipt_id=source.source_receipt_id,
                        skip_existing=arguments.only_missing,
                    )
                    if token is None:
                        break
            token = None
            action_request_symbols += len(symbols)
            while True:
                retrieved_at = datetime.now(timezone.utc)
                payload = client.fetch_corporate_actions(symbols, action_start, arguments.end, token)
                actions, token = parse_corporate_actions(payload)
                action_pages += 1
                source = record_market_source(
                    repository, artifact_store, payload, retrieved_at, ALPACA_CORPORATE_ACTIONS_URL,
                    response_category="alpaca_corporate_actions", raw_category="corporate-actions",
                    compact_receipts=arguments.compact_receipts, parser_version=_ALPACA_PARSER_VERSION,
                )
                artifact_uris.append(source.storage_uri)
                action_count += repository.upsert_corporate_actions(
                    actions, source.raw_artifact_id, ALPACA_CORPORATE_ACTIONS_URL, retrieved_at,
                    source_receipt_id=source.source_receipt_id, retain_provider_payload=not arguments.compact_receipts,
                )
                if token is None:
                    break
    finally:
        repository.close()

    manifest = RunManifest.create(
        settings=settings,
        run_kind="ingestion",
        code_revision=arguments.code_revision,
        data_capability_tier="B",
        source_inputs=(
            SourceInput(provider="alpaca", source_reference=ALPACA_BARS_URL, raw_artifact_uris=tuple(artifact_uris)),
        ),
        status="completed",
        note=(
            f"daily_bars={bar_count}; corporate_actions={action_count}; adjustment_bases=unadjusted,split_adjusted; "
            f"request_mode={'missing_only' if arguments.only_missing else 'range'}; "
            f"bar_request_symbols={bar_request_symbols}; skipped_existing_symbols={skipped_existing_symbols}; "
            f"bar_pages={bar_pages}; corporate_action_window={action_start}:{arguments.end}; "
            f"corporate_action_request_symbols={action_request_symbols}; corporate_action_pages={action_pages}; "
            f"receipt_mode={'compact' if arguments.compact_receipts else 'payload_retained'}"
        ),
    )
    manifest.write(_file_path_from_uri(settings.raw_artifacts_uri) / "manifests" / f"{manifest.run_id}.json")
    print(manifest.note)


if __name__ == "__main__":
    main()
