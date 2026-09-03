"""Fetch and persist benchmark bars without misclassifying an ETF as a stock."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from pathlib import Path

from .config import Settings
from .ingest_security_master import _file_path_from_uri
from .market_data import PostgresMarketDataRepository, record_market_source
from .market_provider import ADJUSTMENT_BASES, MarketProviderMetadata
from .market_provider_registry import available_market_providers, create_market_data_provider
from .run_manifest import RunManifest, SourceInput
from .security_master import FileRawArtifactStore


def _should_fetch_adjustment(
    repository: PostgresMarketDataRepository, ticker: str, end: date,
    adjustment_basis: str, only_missing: bool,
) -> bool:
    return not only_missing or not repository.benchmark_bar_exists(ticker, end, adjustment_basis)


def _source_inputs_for_artifacts(
    bar_artifact_uris: list[str], action_artifact_uris: list[str],
    metadata: MarketProviderMetadata,
) -> tuple[SourceInput, ...]:
    """Return provenance only for data retrieved by this invocation.

    A missing-only retry can legitimately retrieve nothing because an earlier
    attempt already committed every requested benchmark bar. That is a
    successful no-op, not an ingestion run with fabricated source lineage.
    """
    if not bar_artifact_uris and not action_artifact_uris:
        return ()
    return tuple(
        source for source in (
            SourceInput(provider=metadata.provider_id, source_reference=metadata.bars_source_reference,
                        raw_artifact_uris=tuple(bar_artifact_uris)) if bar_artifact_uris else None,
            SourceInput(provider=metadata.provider_id, source_reference=metadata.actions_source_reference,
                        raw_artifact_uris=tuple(action_artifact_uris)) if action_artifact_uris else None,
        ) if source is not None
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest raw, split-adjusted, and total-return benchmark bars")
    parser.add_argument("--provider", choices=available_market_providers())
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
    assert settings.database_url and settings.raw_artifacts_uri
    ticker = arguments.ticker.upper()
    provider = create_market_data_provider(arguments.provider or settings.market_data_provider, settings)
    metadata = provider.metadata
    store = FileRawArtifactStore(settings.raw_artifacts_uri)
    bar_artifact_uris: list[str] = []
    action_artifact_uris: list[str] = []
    count = 0
    fetched_adjustments = 0
    skipped_existing_adjustments = 0
    action_count = 0
    action_pages = 0
    repository = PostgresMarketDataRepository(settings.database_url)
    try:
        availability_rule_id = repository.availability_rule_id(
            *metadata.benchmark_bar_availability_rule, "benchmark_bar",
        )
        for basis in ADJUSTMENT_BASES:
            if not _should_fetch_adjustment(repository, ticker, arguments.end, basis, arguments.only_missing):
                skipped_existing_adjustments += 1
                continue
            fetched_adjustments += 1
            token = None
            while True:
                retrieved_at = datetime.now(timezone.utc)
                page = provider.fetch_daily_bars([ticker], arguments.start, arguments.end, basis, token)
                token = page.next_page_token
                source = record_market_source(
                    repository, store, page.raw_payload, retrieved_at, metadata.bars_source_reference,
                    response_category=metadata.bars_response_category,
                    raw_category=f"{metadata.provider_id}-benchmark-market-data",
                    compact_receipts=arguments.compact_receipts,
                    parser_version=metadata.bars_parser_version, provider=metadata.provider_id,
                )
                bar_artifact_uris.append(source.storage_uri)
                count += repository.upsert_benchmark_daily_bars(
                    list(page.records), ticker, basis, source.raw_artifact_id, metadata.bars_source_reference,
                    retrieved_at, availability_rule_id, source_receipt_id=source.source_receipt_id,
                    skip_existing=arguments.only_missing,
                )
                if token is None:
                    break
        action_rule_id = repository.availability_rule_id(
            *metadata.benchmark_action_availability_rule, "corporate_action",
        )
        token = None
        while True:
            retrieved_at = datetime.now(timezone.utc)
            page = provider.fetch_corporate_actions([ticker], action_start, arguments.end, token)
            token = page.next_page_token
            source = record_market_source(
                repository, store, page.raw_payload, retrieved_at, metadata.actions_source_reference,
                response_category=metadata.actions_response_category,
                raw_category=f"{metadata.provider_id}-benchmark-corporate-actions",
                compact_receipts=arguments.compact_receipts,
                parser_version=metadata.actions_parser_version, provider=metadata.provider_id,
            )
            action_artifact_uris.append(source.storage_uri)
            action_count += repository.insert_benchmark_corporate_actions(
                benchmark_ticker=ticker, actions=list(page.records),
                raw_artifact_id=source.raw_artifact_id,
                source_reference=metadata.actions_source_reference,
                source_receipt_id=source.source_receipt_id,
                availability_rule_id=action_rule_id, available_at=retrieved_at,
            )
            action_pages += 1
            if token is None:
                break
    finally:
        repository.close()
    note = (
        f"provider={metadata.provider_id}; benchmark={ticker}; daily_bars={count}; adjustment_bases=unadjusted,split_adjusted,total_return_adjusted; "
        f"request_mode={'missing_only' if arguments.only_missing else 'range'}; "
        f"fetched_adjustments={fetched_adjustments}; skipped_existing_adjustments={skipped_existing_adjustments}; "
        f"corporate_actions={action_count}; corporate_action_pages={action_pages}; "
        f"corporate_action_window={action_start}:{arguments.end}; "
        f"receipt_mode={'compact' if arguments.compact_receipts else 'payload_retained'}"
    )
    source_inputs = _source_inputs_for_artifacts(bar_artifact_uris, action_artifact_uris, metadata)
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
