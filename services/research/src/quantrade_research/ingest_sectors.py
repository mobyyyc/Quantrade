"""Ingest dated sector classifications from a UTF-8 CIK/sector CSV."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
from pathlib import Path
from html.parser import HTMLParser

from .config import Settings
from .security_master import FileRawArtifactStore


class _ComponentTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(); self.rows: list[list[str]] = []; self.row: list[str] | None = None; self.cell: list[str] | None = None
    def handle_starttag(self, tag, attrs):
        if tag == "tr": self.row = []
        elif tag == "td" and self.row is not None: self.cell = []
    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self, tag):
        if tag == "td" and self.row is not None and self.cell is not None:
            self.row.append("".join(self.cell).strip()); self.cell = None
        elif tag == "tr" and self.row is not None:
            if len(self.row) >= 7 and self.row[6].strip().zfill(10).isdigit(): self.rows.append(self.row)
            self.row = None


def parse_wikipedia_components(payload: bytes) -> list[tuple[str, str]]:
    parser = _ComponentTableParser(); parser.feed(payload.decode("utf-8"))
    result = [(row[6].strip().zfill(10), row[2].strip()) for row in parser.rows if row[2].strip()]
    if len({cik for cik, _ in result}) < 500: raise ValueError("component table did not yield 500 sector classifications")
    return result


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
    classifications = [(str(row["cik"]).zfill(10), str(row["sector"]).strip()) for row in rows if str(row.get("cik", "")).strip()]
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
