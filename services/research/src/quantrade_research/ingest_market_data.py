"""Fetch and persist canonical daily bars and corporate actions for a symbol set."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone

from .config import Settings
from .ingest_security_master import _file_path_from_uri
from .market_data import PostgresMarketDataRepository, record_market_source
from .market_provider import ADJUSTMENT_BASES
from .market_provider_registry import available_market_providers, create_market_data_provider
from .run_manifest import RunManifest, SourceInput
from .security_master import FileRawArtifactStore


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
    parser = argparse.ArgumentParser(description="Ingest provider-normalized daily bars and corporate actions")
    parser.add_argument("--provider", choices=available_market_providers())
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
    assert settings.database_url is not None
    assert settings.raw_artifacts_uri is not None

    provider = create_market_data_provider(arguments.provider or settings.market_data_provider, settings)
    metadata = provider.metadata
    artifact_store = FileRawArtifactStore(settings.raw_artifacts_uri)
    repository = PostgresMarketDataRepository(settings.database_url)
    bar_artifact_uris: list[str] = []
    action_artifact_uris: list[str] = []
    bar_count = 0
    action_count = 0
    bar_request_symbols = 0
    skipped_existing_symbols = 0
    bar_pages = 0
    action_pages = 0
    action_request_symbols = 0
    try:
        availability_rule_id = repository.availability_rule_id(
            *metadata.equity_bar_availability_rule, "market_bar",
        )
        batches = [
            arguments.symbols[index:index + arguments.batch_size]
            for index in range(0, len(arguments.symbols), arguments.batch_size)
        ]
        for symbols in batches:
            for basis in ADJUSTMENT_BASES:
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
                    page = provider.fetch_daily_bars(
                        request_symbols, arguments.start, arguments.end, basis, token,
                    )
                    token = page.next_page_token
                    bar_pages += 1
                    source = record_market_source(
                        repository, artifact_store, page.raw_payload, retrieved_at,
                        metadata.bars_source_reference,
                        response_category=metadata.bars_response_category,
                        raw_category=f"{metadata.provider_id}-market-data",
                        compact_receipts=arguments.compact_receipts,
                        parser_version=metadata.bars_parser_version, provider=metadata.provider_id,
                    )
                    bar_artifact_uris.append(source.storage_uri)
                    bar_count += repository.upsert_daily_bars(
                        list(page.records), basis,
                        source.raw_artifact_id, metadata.bars_source_reference, retrieved_at, availability_rule_id,
                        source_receipt_id=source.source_receipt_id,
                        skip_existing=arguments.only_missing,
                    )
                    if token is None:
                        break
            token = None
            action_request_symbols += len(symbols)
            while True:
                retrieved_at = datetime.now(timezone.utc)
                page = provider.fetch_corporate_actions(symbols, action_start, arguments.end, token)
                token = page.next_page_token
                action_pages += 1
                source = record_market_source(
                    repository, artifact_store, page.raw_payload, retrieved_at,
                    metadata.actions_source_reference,
                    response_category=metadata.actions_response_category,
                    raw_category=f"{metadata.provider_id}-corporate-actions",
                    compact_receipts=arguments.compact_receipts,
                    parser_version=metadata.actions_parser_version, provider=metadata.provider_id,
                )
                action_artifact_uris.append(source.storage_uri)
                action_count += repository.upsert_corporate_actions(
                    list(page.records), source.raw_artifact_id, metadata.actions_source_reference, retrieved_at,
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
        source_inputs=tuple(
            source for source in (
                SourceInput(provider=metadata.provider_id, source_reference=metadata.bars_source_reference,
                            raw_artifact_uris=tuple(bar_artifact_uris)) if bar_artifact_uris else None,
                SourceInput(provider=metadata.provider_id, source_reference=metadata.actions_source_reference,
                            raw_artifact_uris=tuple(action_artifact_uris)) if action_artifact_uris else None,
            ) if source is not None
        ),
        status="completed",
        note=(
            f"provider={metadata.provider_id}; daily_bars={bar_count}; corporate_actions={action_count}; "
            f"adjustment_bases=unadjusted,split_adjusted,total_return_adjusted; "
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
