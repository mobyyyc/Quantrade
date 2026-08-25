"""Persist dated SEC security-master snapshots and derived ticker history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlparse

from .sec_edgar import SecurityMasterRow


@dataclass(frozen=True, slots=True)
class RawArtifact:
    storage_uri: str
    content_sha256: str
    retrieved_at: datetime


@dataclass(frozen=True, slots=True)
class SecurityMasterIngestionReport:
    normalized_rows: int
    unmapped_exchange_rows: int
    closed_listings: int
    raw_artifact_uri: str

    def manifest_note(self) -> str:
        return (
            f"normalized_rows={self.normalized_rows}; "
            f"unmapped_exchange_rows={self.unmapped_exchange_rows}; "
            f"closed_listings={self.closed_listings}; raw_artifact_uri={self.raw_artifact_uri}"
        )


class SecurityMasterRepository(Protocol):
    def persist_raw_artifact(self, artifact: RawArtifact, source_reference: str, provider: str = "sec_edgar") -> str: ...

    def upsert_security_master_row(
        self, row: SecurityMasterRow, raw_artifact_id: str, source_reference: str, ingested_at: datetime
    ) -> None: ...

    def close_missing_sec_listings(self, active_ciks: list[str], snapshot_date: date) -> int: ...


class FileRawArtifactStore:
    """Local artifact store for private development; object storage is swappable later."""

    def __init__(self, base_uri: str) -> None:
        parsed = urlparse(base_uri)
        if parsed.scheme != "file":
            raise ValueError("P2.1 supports a file:// RAW_ARTIFACTS_URI only")
        path = unquote(parsed.path)
        if len(path) >= 3 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        self._base_path = Path(path)

    def store(self, payload: bytes, retrieved_at: datetime, category: str = "security-master") -> RawArtifact:
        if not category or "/" in category or "\\" in category:
            raise ValueError("artifact category must be a simple path segment")
        digest = sha256(payload).hexdigest()
        relative = Path(category) / retrieved_at.strftime("%Y-%m-%d") / f"{digest}.json"
        destination = self._base_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            destination.write_bytes(payload)
        return RawArtifact(
            storage_uri=destination.as_uri(),
            content_sha256=digest,
            retrieved_at=retrieved_at,
        )


class PostgresSecurityMasterRepository:
    """PostgreSQL writer. Import psycopg lazily so fixture tests stay dependency-free."""

    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
        except ImportError as error:  # pragma: no cover - exercised at runtime installation
            raise RuntimeError("Install quantrade-research dependencies before database ingestion") from error
        self._connection = psycopg.connect(database_url)

    def close(self) -> None:
        self._connection.close()

    def persist_raw_artifact(self, artifact: RawArtifact, source_reference: str, provider: str = "sec_edgar") -> str:
        if provider not in {"sec_edgar", "manual"}:
            raise ValueError("security-master artifacts must use sec_edgar or manual provider lineage")
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO quantrade.raw_artifacts
                    (provider, source_reference, storage_uri, retrieved_at, content_sha256)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (storage_uri) DO UPDATE SET storage_uri = EXCLUDED.storage_uri
                RETURNING raw_artifact_id
                """,
                (provider, source_reference, artifact.storage_uri, artifact.retrieved_at, artifact.content_sha256),
            )
            raw_artifact_id = str(cursor.fetchone()[0])
        self._connection.commit()
        return raw_artifact_id

    def upsert_security_master_row(
        self, row: SecurityMasterRow, raw_artifact_id: str, source_reference: str, ingested_at: datetime
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT security_id FROM quantrade.security_identifiers
                WHERE identifier_type = 'cik' AND identifier_value = %s AND valid_to IS NULL
                LIMIT 1
                """,
                (row.cik,),
            )
            existing = cursor.fetchone()
            if existing is None:
                cursor.execute(
                    """
                    INSERT INTO quantrade.securities
                        (issuer_name, asset_class, country_code, valid_from, raw_artifact_id, source_reference, ingested_at)
                    VALUES (%s, 'unknown', 'US', %s, %s, %s, %s)
                    RETURNING security_id
                    """,
                    (row.issuer_name, row.snapshot_date, raw_artifact_id, source_reference, ingested_at),
                )
                security_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO quantrade.security_identifiers
                        (security_id, identifier_type, identifier_value, valid_from, raw_artifact_id, source_reference, ingested_at)
                    VALUES (%s, 'cik', %s, %s, %s, %s, %s)
                    """,
                    (security_id, row.cik, row.snapshot_date, raw_artifact_id, source_reference, ingested_at),
                )
            else:
                security_id = existing[0]

            cursor.execute(
                """
                SELECT listing_id FROM quantrade.listings
                WHERE security_id = %s AND ticker = %s AND exchange_mic = %s AND valid_to IS NULL
                LIMIT 1
                """,
                (security_id, row.ticker, row.exchange_mic),
            )
            current = cursor.fetchone()
            if current is None:
                self._insert_listing(cursor, security_id, row, raw_artifact_id, source_reference, ingested_at)
        self._connection.commit()

    @staticmethod
    def _insert_listing(cursor: object, security_id: object, row: SecurityMasterRow, raw_artifact_id: str, source_reference: str, ingested_at: datetime) -> None:
        cursor.execute(
            """
            INSERT INTO quantrade.listings
                (security_id, ticker, exchange_mic, currency, valid_from, raw_artifact_id, source_reference, ingested_at)
            VALUES (%s, %s, %s, 'USD', %s, %s, %s, %s)
            """,
            (security_id, row.ticker, row.exchange_mic, row.snapshot_date, raw_artifact_id, source_reference, ingested_at),
        )

    def close_missing_sec_listings(self, active_ciks: list[str], snapshot_date: date) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE quantrade.listings AS l
                SET valid_to = %s
                FROM quantrade.security_identifiers AS i, quantrade.raw_artifacts AS a
                WHERE l.security_id = i.security_id
                  AND i.identifier_type = 'cik'
                  AND i.valid_to IS NULL
                  AND a.raw_artifact_id = l.raw_artifact_id
                  AND a.provider = 'sec_edgar'
                  AND l.valid_to IS NULL
                  AND l.valid_from < %s
                  AND NOT (i.identifier_value = ANY(%s))
                """,
                (snapshot_date, snapshot_date, active_ciks),
            )
            closed = cursor.rowcount
        self._connection.commit()
        return closed


def persist_security_master_snapshot(
    repository: SecurityMasterRepository,
    artifact: RawArtifact,
    source_reference: str,
    rows: list[SecurityMasterRow],
    unmapped_exchange_rows: int, *, provider: str = "sec_edgar", close_missing_sec_listings: bool = True,
) -> SecurityMasterIngestionReport:
    ingested_at = datetime.now(timezone.utc)
    raw_artifact_id = repository.persist_raw_artifact(artifact, source_reference, provider)
    for row in rows:
        repository.upsert_security_master_row(row, raw_artifact_id, source_reference, ingested_at)
    closed = (
        repository.close_missing_sec_listings([row.cik for row in rows], rows[0].snapshot_date)
        if rows and close_missing_sec_listings else 0
    )
    return SecurityMasterIngestionReport(len(rows), unmapped_exchange_rows, closed, artifact.storage_uri)
