"""Ingest explicitly dated universe-membership source files."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
import io
from typing import Protocol

from .security_master import RawArtifact


class UniverseInputError(ValueError):
    """Raised when a universe source cannot support a dated membership claim."""


def parse_universe_csv(payload: bytes) -> list[str]:
    try:
        reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    except UnicodeDecodeError as error:
        raise UniverseInputError("universe file must be UTF-8 CSV") from error
    if reader.fieldnames is None or "cik" not in {field.lower() for field in reader.fieldnames}:
        raise UniverseInputError("universe CSV requires a cik column")

    cik_column = next(field for field in reader.fieldnames if field.lower() == "cik")
    ciks: set[str] = set()
    for row in reader:
        cik = (row.get(cik_column) or "").strip().zfill(10)
        if not cik.isdigit():
            raise UniverseInputError("universe CSV contains an invalid CIK")
        ciks.add(cik)
    if not ciks:
        raise UniverseInputError("universe CSV contains no constituents")
    return sorted(ciks)


@dataclass(frozen=True, slots=True)
class UniverseIngestionReport:
    universe_code: str
    as_of_date: date
    constituent_count: int
    historical_membership_verified: bool
    data_capability_tier: str
    raw_artifact_uri: str

    def manifest_note(self) -> str:
        return (
            f"universe_code={self.universe_code}; as_of_date={self.as_of_date.isoformat()}; "
            f"constituent_count={self.constituent_count}; "
            f"historical_membership_verified={self.historical_membership_verified}; "
            f"data_capability_tier={self.data_capability_tier}; raw_artifact_uri={self.raw_artifact_uri}"
        )


class UniverseRepository(Protocol):
    def persist_raw_artifact(self, artifact: RawArtifact, source_reference: str) -> str: ...

    def create_universe_snapshot(
        self,
        universe_code: str,
        as_of_date: date,
        historical_membership_verified: bool,
        data_capability_tier: str,
        raw_artifact_id: str,
        source_reference: str,
        ingested_at: datetime,
    ) -> str: ...

    def add_memberships(self, universe_snapshot_id: str, ciks: list[str]) -> int: ...


class PostgresUniverseRepository:
    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
        except ImportError as error:  # pragma: no cover - exercised after dependency installation
            raise RuntimeError("Install quantrade-research dependencies before database ingestion") from error
        self._connection = psycopg.connect(database_url)

    def close(self) -> None:
        self._connection.close()

    def persist_raw_artifact(self, artifact: RawArtifact, source_reference: str) -> str:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO quantrade.raw_artifacts
                    (provider, source_reference, storage_uri, retrieved_at, content_sha256)
                VALUES ('manual', %s, %s, %s, %s)
                ON CONFLICT (storage_uri) DO UPDATE SET storage_uri = EXCLUDED.storage_uri
                RETURNING raw_artifact_id
                """,
                (source_reference, artifact.storage_uri, artifact.retrieved_at, artifact.content_sha256),
            )
            raw_artifact_id = str(cursor.fetchone()[0])
        self._connection.commit()
        return raw_artifact_id

    def create_universe_snapshot(
        self, universe_code: str, as_of_date: date, historical_membership_verified: bool,
        data_capability_tier: str, raw_artifact_id: str, source_reference: str, ingested_at: datetime,
    ) -> str:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO quantrade.universe_snapshots
                    (universe_code, as_of_date, historical_membership_verified, data_capability_tier,
                     raw_artifact_id, source_reference, ingested_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (universe_code, as_of_date, raw_artifact_id)
                DO UPDATE SET source_reference = EXCLUDED.source_reference
                RETURNING universe_snapshot_id
                """,
                (universe_code, as_of_date, historical_membership_verified, data_capability_tier, raw_artifact_id, source_reference, ingested_at),
            )
            snapshot_id = str(cursor.fetchone()[0])
        self._connection.commit()
        return snapshot_id

    def add_memberships(self, universe_snapshot_id: str, ciks: list[str]) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*) FROM quantrade.security_identifiers
                WHERE identifier_type = 'cik' AND identifier_value = ANY(%s) AND valid_to IS NULL
                """,
                (ciks,),
            )
            resolved = cursor.fetchone()[0]
            if resolved != len(ciks):
                raise UniverseInputError("universe contains CIKs absent from the security master")
            cursor.execute(
                """
                INSERT INTO quantrade.universe_memberships (universe_snapshot_id, security_id)
                SELECT %s, i.security_id
                FROM quantrade.security_identifiers AS i
                WHERE i.identifier_type = 'cik' AND i.identifier_value = ANY(%s) AND i.valid_to IS NULL
                ON CONFLICT DO NOTHING
                """,
                (universe_snapshot_id, ciks),
            )
            inserted = cursor.rowcount
        self._connection.commit()
        return inserted


def persist_universe_snapshot(
    repository: UniverseRepository,
    artifact: RawArtifact,
    source_reference: str,
    universe_code: str,
    as_of_date: date,
    ciks: list[str],
    historical_membership_verified: bool,
    data_capability_tier: str,
) -> UniverseIngestionReport:
    if not universe_code.replace("_", "").replace("-", "").isalnum() or universe_code != universe_code.lower():
        raise UniverseInputError("universe_code must use lowercase letters, digits, underscores, or hyphens")
    if data_capability_tier not in {"A", "B", "C"}:
        raise UniverseInputError("data_capability_tier must be A, B, or C")
    if not historical_membership_verified and data_capability_tier == "A":
        raise UniverseInputError("unverified membership snapshots cannot be labeled Tier A")

    ingested_at = datetime.now(timezone.utc)
    raw_artifact_id = repository.persist_raw_artifact(artifact, source_reference)
    snapshot_id = repository.create_universe_snapshot(
        universe_code, as_of_date, historical_membership_verified, data_capability_tier,
        raw_artifact_id, source_reference, ingested_at,
    )
    repository.add_memberships(snapshot_id, ciks)
    return UniverseIngestionReport(
        universe_code, as_of_date, len(ciks), historical_membership_verified,
        data_capability_tier, artifact.storage_uri,
    )
