"""Persist SEC filing metadata and XBRL facts with acceptance-time availability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from .sec_edgar import SecFilingFact, SecFilingMetadata
from .security_master import RawArtifact


@dataclass(frozen=True, slots=True)
class FilingIngestionReport:
    filings: int
    facts: int
    submissions_artifact_uri: str
    facts_artifact_uri: str

    def manifest_note(self) -> str:
        return f"filings={self.filings}; facts={self.facts}; filing_availability=acceptance_timestamp"


class PostgresFilingRepository:
    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
        except ImportError as error:  # pragma: no cover
            raise RuntimeError("Install quantrade-research dependencies before database ingestion") from error
        self._connection = psycopg.connect(database_url)

    def close(self) -> None:
        self._connection.close()

    def persist_raw_artifact(self, artifact: RawArtifact, source_reference: str) -> str:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO quantrade.raw_artifacts (provider, source_reference, storage_uri, retrieved_at, content_sha256)
                   VALUES ('sec_edgar', %s, %s, %s, %s)
                   ON CONFLICT (storage_uri) DO UPDATE SET storage_uri = EXCLUDED.storage_uri
                   RETURNING raw_artifact_id""",
                (source_reference, artifact.storage_uri, artifact.retrieved_at, artifact.content_sha256),
            )
            value = str(cursor.fetchone()[0])
        self._connection.commit()
        return value

    def _security_id(self, cursor, cik: str) -> object:
        cursor.execute(
            """SELECT security_id FROM quantrade.security_identifiers
               WHERE identifier_type = 'cik' AND identifier_value = %s AND valid_to IS NULL LIMIT 1""",
            (cik.zfill(10),),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"CIK {cik.zfill(10)} is absent from the security master")
        return row[0]

    def known_accession_numbers(self, cik: str, accession_numbers: list[str]) -> set[str]:
        """Return the already-persisted accessions for one security.

        Daily ingestion uses this small metadata lookup before requesting the much
        larger SEC Company Facts document.  Historical ingestion deliberately does
        not use it because it must traverse every dated submission reference.
        """
        if not accession_numbers:
            return set()
        with self._connection.cursor() as cursor:
            security_id = self._security_id(cursor, cik)
            cursor.execute(
                """SELECT accession_number FROM quantrade.filings
                   WHERE security_id = %s AND accession_number = ANY(%s)""",
                (security_id, accession_numbers),
            )
            return {str(row[0]) for row in cursor.fetchall()}

    def upsert_filings(
        self, cik: str, filings: list[SecFilingMetadata], raw_artifact_id: str, source_reference: str,
        ingested_at: datetime, source_by_accession: Mapping[str, tuple[str, str]] | None = None,
    ) -> dict[str, str]:
        identifiers: dict[str, str] = {}
        with self._connection.cursor() as cursor:
            security_id = self._security_id(cursor, cik)
            for filing in filings:
                filing_artifact_id, filing_reference = (
                    source_by_accession.get(filing.accession_number, (raw_artifact_id, source_reference))
                    if source_by_accession else (raw_artifact_id, source_reference)
                )
                cursor.execute(
                    """INSERT INTO quantrade.filings
                       (security_id, accession_number, form, filed_at, accepted_at, period_end, published_at,
                        available_at, ingested_at, raw_artifact_id, source_reference)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (accession_number) DO UPDATE SET ingested_at = EXCLUDED.ingested_at,
                        raw_artifact_id = EXCLUDED.raw_artifact_id, source_reference = EXCLUDED.source_reference
                       RETURNING filing_id""",
                    (security_id, filing.accession_number, filing.form, filing.filed_at, filing.accepted_at,
                     filing.period_end, None, filing.accepted_at, ingested_at, filing_artifact_id, filing_reference),
                )
                identifiers[filing.accession_number] = str(cursor.fetchone()[0])
        self._connection.commit()
        return identifiers

    def upsert_facts(self, cik: str, facts: list[SecFilingFact], filings: dict[str, SecFilingMetadata], filing_ids: dict[str, str], raw_artifact_id: str, source_reference: str, ingested_at: datetime) -> int:
        with self._connection.cursor() as cursor:
            security_id = self._security_id(cursor, cik)
            for fact in facts:
                filing = filings[fact.accession_number]
                cursor.execute(
                    """INSERT INTO quantrade.filing_facts
                       (filing_id, security_id, taxonomy, concept, unit, fact_value, period_start, period_end,
                        fiscal_year, fiscal_period, published_at, available_at, ingested_at, raw_artifact_id, source_reference)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (filing_id, taxonomy, concept, unit, period_start, period_end)
                       DO UPDATE SET fact_value = EXCLUDED.fact_value, ingested_at = EXCLUDED.ingested_at,
                        raw_artifact_id = EXCLUDED.raw_artifact_id, source_reference = EXCLUDED.source_reference
                    """,
                    (filing_ids[fact.accession_number], security_id, fact.taxonomy, fact.concept, fact.unit,
                     fact.value, fact.period_start, fact.period_end, fact.fiscal_year, fact.fiscal_period,
                     None, filing.accepted_at, ingested_at, raw_artifact_id, source_reference),
                )
        self._connection.commit()
        return len(facts)


def persist_sec_filings(
    repository, cik: str, filings: list[SecFilingMetadata], facts: list[SecFilingFact],
    submissions_artifact: RawArtifact, facts_artifact: RawArtifact,
    submissions_reference: str, facts_reference: str,
    submission_sources: Mapping[str, tuple[RawArtifact, str]] | None = None,
) -> FilingIngestionReport:
    ingested_at = datetime.now(timezone.utc)
    submissions_id = repository.persist_raw_artifact(submissions_artifact, submissions_reference)
    facts_id = repository.persist_raw_artifact(facts_artifact, facts_reference)
    source_by_accession = {
        accession: (repository.persist_raw_artifact(artifact, reference), reference)
        for accession, (artifact, reference) in (submission_sources or {}).items()
    }
    filing_map = {filing.accession_number: filing for filing in filings}
    filing_ids = repository.upsert_filings(
        cik, filings, submissions_id, submissions_reference, ingested_at, source_by_accession,
    )
    fact_count = repository.upsert_facts(cik, facts, filing_map, filing_ids, facts_id, facts_reference, ingested_at)
    return FilingIngestionReport(len(filings), fact_count, submissions_artifact.storage_uri, facts_artifact.storage_uri)
