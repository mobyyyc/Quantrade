"""Unified point-in-time resolver for frozen and newly observed SEC facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable, Sequence

from .quality import DataQualityError
from .sec_form_scope import RESEARCH_RELEVANT_FORMS


LEGACY_AVAILABILITY_RULE = "sec_acceptance_plus_5m_legacy_tier_b_v1"
OBSERVED_AVAILABILITY_RULE = "max_sec_acceptance_plus_5m_observed_at_v1"


@dataclass(frozen=True, slots=True)
class ResolvedSecFact:
    filing_fact_key: str
    filing_id: str
    security_id: str
    accession_number: str
    submitted_form: str
    is_amendment: bool
    taxonomy: str
    concept: str
    unit: str
    value: Decimal
    period_start: date | None
    period_end: date
    fiscal_year: int | None
    fiscal_period: str | None
    accepted_at: datetime
    observed_at: datetime | None
    available_at: datetime
    availability_rule: str
    source_reference: str
    source_receipt_id: str | None

    @property
    def lineage_key(self) -> str:
        return ":".join((self.accession_number, self.filing_fact_key, self.availability_rule))


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DataQualityError(f"{label} must include a UTC offset")
    return value.astimezone(timezone.utc)


def resolve_facts_as_of(
    facts: Iterable[ResolvedSecFact], *, decision_at: datetime,
) -> tuple[ResolvedSecFact, ...]:
    """Select the latest eligible observation of every accession-level fact.

    Amendments deliberately remain distinct because their accession numbers differ.
    A later observation can replace an earlier observation only for decisions made
    after that later observation became available.
    """
    decision = _utc(decision_at, "decision_at")
    selected: dict[str, ResolvedSecFact] = {}
    for fact in facts:
        available = _utc(fact.available_at, "fact available_at")
        if available > decision:
            continue
        current = selected.get(fact.filing_fact_key)
        if current is None or (
            available,
            _utc(fact.observed_at, "fact observed_at") if fact.observed_at else datetime.min.replace(tzinfo=timezone.utc),
            fact.lineage_key,
        ) > (
            _utc(current.available_at, "fact available_at"),
            _utc(current.observed_at, "fact observed_at") if current.observed_at else datetime.min.replace(tzinfo=timezone.utc),
            current.lineage_key,
        ):
            selected[fact.filing_fact_key] = fact
    return tuple(sorted(selected.values(), key=lambda item: (item.security_id, item.concept, item.period_end, item.lineage_key)))


POINT_IN_TIME_FACT_SQL = """
WITH observed_keys AS (
    SELECT DISTINCT filing_id, taxonomy, concept, unit, period_start, period_end
    FROM quantrade.filing_fact_observations
), candidates AS (
    SELECT
        concat_ws('|', ff.filing_id::text, ff.taxonomy, ff.concept, ff.unit,
                  ff.period_start::text, ff.period_end::text) AS filing_fact_key,
        ff.filing_id::text,
        ff.security_id::text,
        f.accession_number,
        COALESCE(f.submitted_form, f.form) AS submitted_form,
        f.is_amendment,
        ff.taxonomy, ff.concept, ff.unit, ff.fact_value,
        ff.period_start, ff.period_end, ff.fiscal_year, ff.fiscal_period,
        f.accepted_at,
        NULL::timestamptz AS observed_at,
        f.accepted_at + interval '5 minutes' AS effective_available_at,
        'sec_acceptance_plus_5m_legacy_tier_b_v1' AS availability_rule,
        ff.source_reference,
        ff.source_receipt_id::text
    FROM quantrade.filing_facts ff
    JOIN quantrade.filings f ON f.filing_id = ff.filing_id
    LEFT JOIN observed_keys ok
      ON ok.filing_id = ff.filing_id
     AND ok.taxonomy = ff.taxonomy AND ok.concept = ff.concept AND ok.unit = ff.unit
     AND ok.period_start IS NOT DISTINCT FROM ff.period_start AND ok.period_end = ff.period_end
    WHERE ok.filing_id IS NULL
      AND f.form = ANY(%s)

    UNION ALL

    SELECT
        concat_ws('|', o.filing_id::text, o.taxonomy, o.concept, o.unit,
                  o.period_start::text, o.period_end::text) AS filing_fact_key,
        o.filing_id::text,
        o.security_id::text,
        f.accession_number,
        COALESCE(f.submitted_form, f.form) AS submitted_form,
        f.is_amendment,
        o.taxonomy, o.concept, o.unit, o.fact_value,
        o.period_start, o.period_end, o.fiscal_year, o.fiscal_period,
        f.accepted_at,
        o.observed_at,
        GREATEST(f.accepted_at + interval '5 minutes', o.observed_at) AS effective_available_at,
        'max_sec_acceptance_plus_5m_observed_at_v1' AS availability_rule,
        o.source_reference,
        o.source_receipt_id::text
    FROM quantrade.filing_fact_observations o
    JOIN quantrade.filings f ON f.filing_id = o.filing_id
    WHERE f.form = ANY(%s)
)
SELECT *
FROM candidates
WHERE security_id = ANY(%s)
  AND taxonomy = %s
  AND concept = ANY(%s)
  AND period_end <= %s
  AND effective_available_at <= %s
ORDER BY security_id, concept, period_end, effective_available_at, accession_number
"""


class PostgresSecFactResolver:
    """Read compact, decision-safe SEC fact inputs without rewriting source data."""

    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
        except ImportError as error:  # pragma: no cover
            raise RuntimeError("Install quantrade-research dependencies before resolving SEC facts") from error
        self._connection = psycopg.connect(database_url)

    def close(self) -> None:
        self._connection.close()

    def load_candidates(
        self, *, security_ids: Sequence[str], taxonomy: str, concepts: Sequence[str],
        formation_date: date, decision_at: datetime,
    ) -> tuple[ResolvedSecFact, ...]:
        if not security_ids or not concepts:
            return ()
        decision = _utc(decision_at, "decision_at")
        with self._connection.cursor() as cursor:
            cursor.execute(
                POINT_IN_TIME_FACT_SQL,
                (
                    list(sorted(RESEARCH_RELEVANT_FORMS)),
                    list(sorted(RESEARCH_RELEVANT_FORMS)),
                    list(security_ids), taxonomy, list(concepts), formation_date, decision,
                ),
            )
            rows = cursor.fetchall()
        facts = tuple(
            ResolvedSecFact(
                filing_fact_key=str(row[0]), filing_id=str(row[1]), security_id=str(row[2]),
                accession_number=str(row[3]), submitted_form=str(row[4]), is_amendment=bool(row[5]),
                taxonomy=str(row[6]), concept=str(row[7]), unit=str(row[8]), value=Decimal(row[9]),
                period_start=row[10], period_end=row[11], fiscal_year=row[12], fiscal_period=row[13],
                accepted_at=row[14], observed_at=row[15], available_at=row[16], availability_rule=str(row[17]),
                source_reference=str(row[18]), source_receipt_id=str(row[19]) if row[19] else None,
            )
            for row in rows
        )
        return facts

    def resolve(
        self, *, security_ids: Sequence[str], taxonomy: str, concepts: Sequence[str],
        formation_date: date, decision_at: datetime,
    ) -> tuple[ResolvedSecFact, ...]:
        candidates = self.load_candidates(
            security_ids=security_ids, taxonomy=taxonomy, concepts=concepts,
            formation_date=formation_date, decision_at=decision_at,
        )
        return resolve_facts_as_of(candidates, decision_at=decision_at)
