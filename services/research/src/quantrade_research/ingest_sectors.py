"""Ingest dated sector classifications from a UTF-8 CIK/sector CSV."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
from pathlib import Path

from .config import Settings
from .security_master import FileRawArtifactStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--as-of-date", type=date.fromisoformat, required=True)
    parser.add_argument("--source-reference", required=True)
    arguments = parser.parse_args()
    settings = Settings.from_environment()
    settings.require_runtime_storage()
    assert settings.database_url and settings.raw_artifacts_uri
    payload = arguments.input.read_bytes()
    rows = list(csv.DictReader(payload.decode("utf-8-sig").splitlines()))
    classifications = [(str(row["cik"]).zfill(10), str(row["sector"]).strip()) for row in rows]
    if not classifications or any(not cik.isdigit() or not sector for cik, sector in classifications):
        raise ValueError("CSV requires non-empty cik and sector columns")
    artifact = FileRawArtifactStore(settings.raw_artifacts_uri).store(payload, datetime.now(timezone.utc), category="sector-classifications")
    import psycopg
    with psycopg.connect(settings.database_url) as connection, connection.cursor() as cursor:
        cursor.execute("INSERT INTO quantrade.raw_artifacts (provider, source_reference, storage_uri, retrieved_at, content_sha256) VALUES ('manual', %s, %s, %s, %s) ON CONFLICT (storage_uri) DO UPDATE SET storage_uri = EXCLUDED.storage_uri RETURNING raw_artifact_id", (arguments.source_reference, artifact.storage_uri, artifact.retrieved_at, artifact.content_sha256))
        artifact_id = cursor.fetchone()[0]
        for cik, sector in classifications:
            cursor.execute("INSERT INTO quantrade.sector_classifications (security_id, sector_code, as_of_date, available_at, raw_artifact_id, source_reference, ingested_at) SELECT security_id, %s, %s, %s, %s, %s, %s FROM quantrade.security_identifiers WHERE identifier_type='cik' AND identifier_value=%s AND valid_to IS NULL ON CONFLICT DO NOTHING", (sector, arguments.as_of_date, artifact.retrieved_at, artifact_id, arguments.source_reference, datetime.now(timezone.utc), cik))
    print(f"classifications={len(classifications)}")


if __name__ == "__main__":
    main()
