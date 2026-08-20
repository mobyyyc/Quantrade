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
from .market_data import PostgresMarketDataRepository
from .run_manifest import RunManifest, SourceInput
from .security_master import FileRawArtifactStore


def _symbols(value: str) -> list[str]:
    symbols = [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]
    if not symbols:
        raise argparse.ArgumentTypeError("at least one symbol is required")
    return symbols


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Alpaca daily bars and corporate actions")
    parser.add_argument("--symbols", type=_symbols, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--code-revision", required=True)
    arguments = parser.parse_args()

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
    try:
        for adjustment in ("raw", "split"):
            token = None
            while True:
                retrieved_at = datetime.now(timezone.utc)
                payload = client.fetch_daily_bars(arguments.symbols, arguments.start, arguments.end, adjustment, token)
                bars, token = parse_daily_bars(payload)
                artifact = artifact_store.store(payload, retrieved_at, category="market-data")
                artifact_uris.append(artifact.storage_uri)
                artifact_id = repository.persist_raw_artifact(artifact, ALPACA_BARS_URL)
                bar_count += repository.upsert_daily_bars(
                    bars, "unadjusted" if adjustment == "raw" else "split_adjusted",
                    artifact_id, ALPACA_BARS_URL, retrieved_at,
                )
                if token is None:
                    break

        token = None
        while True:
            retrieved_at = datetime.now(timezone.utc)
            payload = client.fetch_corporate_actions(arguments.symbols, arguments.start, arguments.end, token)
            actions, token = parse_corporate_actions(payload)
            artifact = artifact_store.store(payload, retrieved_at, category="corporate-actions")
            artifact_uris.append(artifact.storage_uri)
            artifact_id = repository.persist_raw_artifact(artifact, ALPACA_CORPORATE_ACTIONS_URL)
            action_count += repository.upsert_corporate_actions(actions, artifact_id, ALPACA_CORPORATE_ACTIONS_URL, retrieved_at)
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
        note=f"daily_bars={bar_count}; corporate_actions={action_count}; adjustment_bases=unadjusted,split_adjusted",
    )
    manifest.write(_file_path_from_uri(settings.raw_artifacts_uri) / "manifests" / f"{manifest.run_id}.json")
    print(manifest.note)


if __name__ == "__main__":
    main()
