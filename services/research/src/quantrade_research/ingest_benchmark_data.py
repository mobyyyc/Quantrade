"""Fetch and persist benchmark bars without misclassifying an ETF as a stock."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from pathlib import Path

from .alpaca import ALPACA_BARS_URL, AlpacaClient, parse_daily_bars
from .config import Settings
from .ingest_security_master import _file_path_from_uri
from .run_manifest import RunManifest, SourceInput
from .security_master import FileRawArtifactStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest split-adjusted and raw benchmark daily bars")
    parser.add_argument("--ticker", default="SPY")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--env-file", default=".env")
    arguments = parser.parse_args()
    if arguments.start > arguments.end:
        parser.error("--start must be on or before --end")
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
    import psycopg
    with psycopg.connect(settings.database_url) as connection, connection.cursor() as cursor:
        for adjustment, basis in (("raw", "unadjusted"), ("split", "split_adjusted")):
            token = None
            while True:
                retrieved_at = datetime.now(timezone.utc)
                payload = client.fetch_daily_bars([ticker], arguments.start, arguments.end, adjustment, token)
                bars, token = parse_daily_bars(payload)
                artifact = store.store(payload, retrieved_at, category="benchmark-market-data")
                artifact_uris.append(artifact.storage_uri)
                cursor.execute(
                    """INSERT INTO quantrade.raw_artifacts
                       (provider, source_reference, storage_uri, retrieved_at, content_sha256)
                       VALUES ('alpaca', %s, %s, %s, %s)
                       ON CONFLICT (storage_uri) DO UPDATE SET storage_uri = EXCLUDED.storage_uri
                       RETURNING raw_artifact_id""",
                    (ALPACA_BARS_URL, artifact.storage_uri, artifact.retrieved_at, artifact.content_sha256),
                )
                artifact_id = cursor.fetchone()[0]
                for bar in bars:
                    cursor.execute(
                        """INSERT INTO quantrade.benchmark_daily_price_bars
                           (benchmark_ticker, session_date, session, currency, open_price, high_price, low_price,
                            close_price, volume, adjustment_basis, observed_at, available_at, ingested_at,
                            raw_artifact_id, source_reference)
                           VALUES (%s, %s, 'regular', 'USD', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (benchmark_ticker, session_date, session, adjustment_basis)
                           DO UPDATE SET open_price = EXCLUDED.open_price, high_price = EXCLUDED.high_price,
                               low_price = EXCLUDED.low_price, close_price = EXCLUDED.close_price,
                               volume = EXCLUDED.volume, observed_at = EXCLUDED.observed_at,
                               available_at = EXCLUDED.available_at, ingested_at = EXCLUDED.ingested_at,
                               raw_artifact_id = EXCLUDED.raw_artifact_id, source_reference = EXCLUDED.source_reference""",
                        (ticker, bar.session_date, bar.open_price, bar.high_price, bar.low_price, bar.close_price,
                         bar.volume, basis, bar.observed_at, retrieved_at, datetime.now(timezone.utc), artifact_id,
                         ALPACA_BARS_URL),
                    )
                    count += 1
                if token is None:
                    break
        connection.commit()
    manifest = RunManifest.create(settings=settings, run_kind="ingestion", code_revision=arguments.code_revision, data_capability_tier="B", status="completed", source_inputs=(SourceInput(provider="alpaca", source_reference=ALPACA_BARS_URL, raw_artifact_uris=tuple(artifact_uris)),), note=f"benchmark={ticker}; daily_bars={count}; adjustment_bases=unadjusted,split_adjusted")
    manifest.write(_file_path_from_uri(settings.raw_artifacts_uri) / "manifests" / f"{manifest.run_id}.json")
    print(manifest.note)


if __name__ == "__main__":
    main()
