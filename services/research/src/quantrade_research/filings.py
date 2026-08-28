"""Persist SEC filing metadata and XBRL facts with acceptance-time availability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Mapping

from .sec_edgar import SecFilingFact, SecFilingMetadata
from .security_master import RawArtifact


@dataclass(frozen=True, slots=True)
class FilingIngestionReport:
    filings: int
    facts: int
    submissions_artifact_uri: str
    facts_artifact_uri: str | None

    def manifest_note(self) -> str:
        return f"filings={self.filings}; facts={self.facts}; filing_availability=acceptance_timestamp"


@dataclass(frozen=True, slots=True)
class StoredSource:
    """A source linked to rows, whether its payload is retained or receipt-only."""

    raw_artifact_id: str
    storage_uri: str
    source_reference: str
    source_receipt_id: str | None = None


SEC_FILING_AVAILABILITY_BUFFER = timedelta(minutes=5)


def buffered_filing_availability(accepted_at: datetime) -> datetime:
    """Apply the versioned, conservative five-minute SEC publication buffer."""
    if accepted_at.tzinfo is None or accepted_at.utcoffset() is None:
        raise ValueError("SEC acceptance timestamp must include a UTC offset")
    return accepted_at.astimezone(timezone.utc) + SEC_FILING_AVAILABILITY_BUFFER


def _fact_observation_hash(fact: SecFilingFact, source: StoredSource) -> str:
    payload = "|".join((
        fact.accession_number, fact.taxonomy, fact.concept, fact.unit,
        fact.period_start.isoformat() if fact.period_start else "", fact.period_end.isoformat(),
        str(fact.value), str(fact.fiscal_year or ""), str(fact.fiscal_period or ""),
        source.source_receipt_id or "", source.raw_artifact_id, "ingestion",
    ))
    return sha256(payload.encode("utf-8")).hexdigest()


class PostgresFilingRepository:
    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
        except ImportError as error:  # pragma: no cover
            raise RuntimeError("Install quantrade-research dependencies before database ingestion") from error
        self._connection = psycopg.connect(database_url)

    def close(self) -> None:
        self._connection.close()

    def persist_raw_artifact(self, artifact: RawArtifact, source_reference: str) -> StoredSource:
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
        return StoredSource(value, artifact.storage_uri, source_reference)

    def persist_compact_receipt(
        self, payload: bytes, source_reference: str, response_category: str,
        retrieved_at: datetime, *, parser_version: str,
    ) -> StoredSource:
        """Record a content-hashed source receipt without writing a payload file."""
        content_sha256 = sha256(payload).hexdigest()
        source_key = sha256(source_reference.encode("utf-8")).hexdigest()
        storage_uri = f"receipt://sec-edgar/{source_key}/{content_sha256}"
        content_type = "text/plain" if response_category == "sec_daily_index" else "application/json"
        with self._connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO quantrade.raw_artifacts (provider, source_reference, storage_uri, retrieved_at, content_sha256)
                   VALUES ('sec_edgar', %s, %s, %s, %s)
                   ON CONFLICT (storage_uri) DO UPDATE SET storage_uri = EXCLUDED.storage_uri
                   RETURNING raw_artifact_id""",
                (source_reference, storage_uri, retrieved_at, content_sha256),
            )
            raw_artifact_id = str(cursor.fetchone()[0])
            cursor.execute(
                """INSERT INTO quantrade.source_receipts
                       (provider, source_reference, response_category, content_sha256, byte_count, parser_version,
                        payload_retained, content_type)
                   VALUES ('sec_edgar', %s, %s, %s, %s, %s, FALSE, %s)
                   ON CONFLICT (provider, source_reference, content_sha256, parser_version) DO NOTHING
                   RETURNING source_receipt_id""",
                (source_reference, response_category, content_sha256, len(payload), parser_version, content_type),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    """SELECT source_receipt_id FROM quantrade.source_receipts
                       WHERE provider = 'sec_edgar' AND source_reference = %s
                         AND content_sha256 = %s AND parser_version = %s""",
                    (source_reference, content_sha256, parser_version),
                )
                row = cursor.fetchone()
            source_receipt_id = str(row[0])
            cursor.execute(
                """INSERT INTO quantrade.source_receipt_retrievals
                       (source_receipt_id, retrieved_at, retrieval_context)
                   VALUES (%s, %s, jsonb_build_object('retention_mode', 'metadata_only'))
                   ON CONFLICT (source_receipt_id, retrieved_at) DO NOTHING""",
                (source_receipt_id, retrieved_at),
            )
        self._connection.commit()
        return StoredSource(raw_artifact_id, storage_uri, source_reference, source_receipt_id)

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
        self, cik: str, filings: list[SecFilingMetadata], source: StoredSource,
        ingested_at: datetime, source_by_accession: Mapping[str, StoredSource] | None = None,
    ) -> dict[str, str]:
        identifiers: dict[str, str] = {}
        with self._connection.cursor() as cursor:
            security_id = self._security_id(cursor, cik)
            for filing in filings:
                filing_source = source_by_accession.get(filing.accession_number, source) if source_by_accession else source
                cursor.execute(
                    """INSERT INTO quantrade.filings
                       (security_id, accession_number, form, submitted_form, is_amendment, filed_at, accepted_at, period_end, published_at,
                        available_at, ingested_at, raw_artifact_id, source_reference, source_receipt_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (accession_number) DO UPDATE SET ingested_at = EXCLUDED.ingested_at,
                        raw_artifact_id = EXCLUDED.raw_artifact_id, source_reference = EXCLUDED.source_reference,
                        submitted_form = COALESCE(quantrade.filings.submitted_form, EXCLUDED.submitted_form),
                        is_amendment = quantrade.filings.is_amendment OR EXCLUDED.is_amendment,
                        source_receipt_id = COALESCE(EXCLUDED.source_receipt_id, quantrade.filings.source_receipt_id)
                       RETURNING filing_id""",
                    (security_id, filing.accession_number, filing.form, filing.submitted_form, filing.is_amendment,
                     filing.filed_at, filing.accepted_at,
                     filing.period_end, None, filing.accepted_at, ingested_at, filing_source.raw_artifact_id,
                     filing_source.source_reference, filing_source.source_receipt_id),
                )
                identifiers[filing.accession_number] = str(cursor.fetchone()[0])
        self._connection.commit()
        return identifiers

    def upsert_facts(self, cik: str, facts: list[SecFilingFact], filings: dict[str, SecFilingMetadata], filing_ids: dict[str, str], source: StoredSource, ingested_at: datetime) -> int:
        with self._connection.cursor() as cursor:
            security_id = self._security_id(cursor, cik)
            cursor.execute(
                """SELECT availability_rule_id FROM quantrade.availability_rules
                   WHERE rule_key = 'sec_filing_acceptance_buffered' AND rule_version = 'v1'
                     AND provider = 'sec_edgar' AND data_domain = 'filing_fact'"""
            )
            availability_rule = cursor.fetchone()
            if availability_rule is None:
                raise ValueError("the SEC buffered filing availability rule has not been migrated")
            availability_rule_id = availability_rule[0]
            for fact in facts:
                filing = filings[fact.accession_number]
                cursor.execute(
                    """INSERT INTO quantrade.filing_facts
                       (filing_id, security_id, taxonomy, concept, unit, fact_value, period_start, period_end,
                        fiscal_year, fiscal_period, published_at, available_at, ingested_at, raw_artifact_id, source_reference,
                        source_receipt_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (filing_id, taxonomy, concept, unit, period_start, period_end) DO NOTHING
                    """,
                    (filing_ids[fact.accession_number], security_id, fact.taxonomy, fact.concept, fact.unit,
                     fact.value, fact.period_start, fact.period_end, fact.fiscal_year, fact.fiscal_period,
                     None, filing.accepted_at, ingested_at, source.raw_artifact_id, source.source_reference,
                     source.source_receipt_id),
                )
                cursor.execute(
                    """INSERT INTO quantrade.filing_fact_observations
                       (filing_id, security_id, taxonomy, concept, unit, fact_value, period_start, period_end,
                        fiscal_year, fiscal_period, available_at, availability_rule_id, raw_artifact_id,
                        source_reference, source_receipt_id, observed_at, observation_kind, observation_hash)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ingestion', %s)
                       ON CONFLICT (observation_hash) DO NOTHING""",
                    (filing_ids[fact.accession_number], security_id, fact.taxonomy, fact.concept, fact.unit,
                     fact.value, fact.period_start, fact.period_end, fact.fiscal_year, fact.fiscal_period,
                     buffered_filing_availability(filing.accepted_at), availability_rule_id,
                     source.raw_artifact_id, source.source_reference, source.source_receipt_id, ingested_at,
                     _fact_observation_hash(fact, source)),
                )
        self._connection.commit()
        return len(facts)


def persist_sec_filings(
    repository, cik: str, filings: list[SecFilingMetadata], facts: list[SecFilingFact],
    submissions_source: StoredSource, facts_source: StoredSource | None,
    submission_sources: Mapping[str, StoredSource] | None = None,
) -> FilingIngestionReport:
    ingested_at = datetime.now(timezone.utc)
    filing_map = {filing.accession_number: filing for filing in filings}
    filing_ids = repository.upsert_filings(
        cik, filings, submissions_source, ingested_at, submission_sources,
    )
    fact_count = 0 if facts_source is None else repository.upsert_facts(
        cik, facts, filing_map, filing_ids, facts_source, ingested_at,
    )
    return FilingIngestionReport(
        len(filings), fact_count, submissions_source.storage_uri,
        facts_source.storage_uri if facts_source else None,
    )
