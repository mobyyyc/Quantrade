"""Read-only, as-of inventory of stored SEC metadata and selected accounting facts.

Coverage is not an assertion that every public filing was downloaded, nor that
the covered inputs are sufficient to calculate a model feature.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from .historical_cohorts import CURRENT_SURVIVORS_COHORT
from .phase_9c_feature_panel import DEI_CONCEPTS, US_GAAP_CONCEPTS
from .quality import DataQualityError
from .score_run import _settings
from .sec_fact_resolver import PostgresSecFactResolver, ResolvedSecFact, resolve_facts_as_of
from .sec_form_scope import RESEARCH_RELEVANT_FORMS, canonical_form


SCHEMA_VERSION = "sec_coverage_report_v1"
TORONTO = ZoneInfo("America/Toronto")
SELECTED_CONCEPTS = tuple(
    [("us-gaap", concept, "USD") for concept in US_GAAP_CONCEPTS]
    + [("dei", concept, "shares") for concept in DEI_CONCEPTS]
)


@dataclass(frozen=True)
class Company:
    security_id: str
    name: str
    tickers: tuple[str, ...]
    ciks: tuple[str, ...]


@dataclass(frozen=True)
class Filing:
    filing_id: str
    security_id: str
    accession: str
    submitted_form: str
    accepted_at: datetime
    period_end: date | None


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DataQualityError("coverage cutoff and availability times require a UTC offset")
    return value.astimezone(timezone.utc)


def build_report(
    *, companies: Iterable[Company], filings: Iterable[Filing], facts: Iterable[ResolvedSecFact],
    cutoff: datetime, period_start: date, code_revision: str,
) -> dict:
    cutoff = _aware(cutoff)
    period_end = cutoff.astimezone(TORONTO).date()
    if period_start > period_end:
        raise DataQualityError("reporting-period start must not follow the cutoff date")
    company_map = {item.security_id: item for item in companies}
    if not company_map:
        raise DataQualityError("the fixed research cohort has no companies")
    filing_map: dict[str, Filing] = {}
    excluded = Counter()
    for filing in filings:
        if filing.security_id not in company_map:
            excluded["filings_outside_cohort"] += 1
        elif _aware(filing.accepted_at) > cutoff:
            excluded["filings_accepted_after_cutoff"] += 1
        elif canonical_form(filing.submitted_form) not in RESEARCH_RELEVANT_FORMS:
            excluded["filings_outside_approved_form_scope"] += 1
        elif filing.filing_id in filing_map and filing_map[filing.filing_id] != filing:
            raise DataQualityError("conflicting filing metadata in coverage input")
        else:
            filing_map[filing.filing_id] = filing

    # Exactly the same accession-level latest-eligible-version rule as research.
    resolved = resolve_facts_as_of(facts, decision_at=cutoff)
    concept_counts = Counter()
    concept_periods = defaultdict(set)
    concept_filings = defaultdict(set)
    period_counts = Counter()
    period_filings = defaultdict(set)
    availability_rules = Counter()
    lineage = sha256()
    for fact in resolved:
        filing = filing_map.get(fact.filing_id)
        concept = (fact.taxonomy, fact.concept, fact.unit)
        if not filing or filing.security_id != fact.security_id or filing.accession != fact.accession_number:
            excluded["facts_without_matching_in_scope_filing"] += 1
            continue
        if concept not in SELECTED_CONCEPTS:
            excluded["facts_outside_selected_concepts_or_units"] += 1
            continue
        if not period_start <= fact.period_end <= period_end:
            excluded["facts_outside_reporting_period_window"] += 1
            continue
        earliest_available = _aware(filing.accepted_at) + timedelta(minutes=5)
        if fact.observed_at is not None:
            earliest_available = max(earliest_available, _aware(fact.observed_at))
        if earliest_available > cutoff or _aware(fact.available_at) < earliest_available:
            raise DataQualityError("fact violates buffered/observed SEC availability")
        if fact.period_start is not None and fact.period_start > fact.period_end:
            raise DataQualityError("fact reporting period is inverted")
        key = (fact.security_id, *concept)
        period = (fact.period_start.isoformat() if fact.period_start else "", fact.period_end.isoformat())
        concept_counts[key] += 1
        concept_periods[key].add(period)
        concept_filings[key].add(fact.filing_id)
        period_key = (*key, filing.submitted_form, *period)
        period_counts[period_key] += 1
        period_filings[period_key].add(fact.filing_id)
        availability_rules[fact.availability_rule] += 1
        lineage.update((fact.lineage_key + "\n").encode())

    forms = defaultdict(list)
    for filing in filing_map.values():
        forms[(filing.security_id, canonical_form(filing.submitted_form))].append(filing)
    by_company, by_form, by_concept = [], [], []
    for security_id, company in sorted(company_map.items()):
        company_filings = [item for form in sorted(RESEARCH_RELEVANT_FORMS) for item in forms[(security_id, form)]]
        missing = []
        for taxonomy, concept, unit in SELECTED_CONCEPTS:
            key = (security_id, taxonomy, concept, unit)
            periods = concept_periods[key]
            count = concept_counts[key]
            if not count:
                missing.append(f"{taxonomy}:{concept}:{unit}")
            by_concept.append({
                "security_id": security_id, "taxonomy": taxonomy, "concept": concept, "unit": unit,
                "resolved_fact_count": count, "filing_count": len(concept_filings[key]),
                "distinct_reporting_period_count": len(periods),
                "earliest_period_end": min((p[1] for p in periods), default=None),
                "latest_period_end": max((p[1] for p in periods), default=None),
                "status": "present" if count else "not_observed_in_window",
            })
        for form in sorted(RESEARCH_RELEVANT_FORMS):
            records = forms[(security_id, form)]
            by_form.append({
                "security_id": security_id, "canonical_form": form, "filing_count": len(records),
                "amendment_count": sum(item.submitted_form.endswith("/A") for item in records),
                "submitted_forms": dict(sorted(Counter(item.submitted_form for item in records).items())),
                "latest_accepted_at": max((item.accepted_at for item in records), default=None),
                "without_reporting_period_count": sum(item.period_end is None for item in records),
            })
        by_company.append({
            "security_id": security_id, "company_name": company.name,
            "current_tickers": list(company.tickers), "current_ciks": list(company.ciks),
            "filing_count": len(company_filings),
            "selected_concepts_present": len(SELECTED_CONCEPTS) - len(missing),
            "selected_concepts_not_observed": missing,
        })
    by_period = [
        {
            "security_id": key[0], "taxonomy": key[1], "concept": key[2], "unit": key[3],
            "submitted_form": key[4], "period_start": key[5] or None, "period_end": key[6],
            "resolved_fact_count": count, "filing_count": len(period_filings[key]),
        }
        for key, count in sorted(period_counts.items())
    ]
    concept_summary = [
        {"taxonomy": taxonomy, "concept": concept, "unit": unit,
         "companies_present": sum(concept_counts[(sid, taxonomy, concept, unit)] > 0 for sid in company_map),
         "companies_not_observed": sum(concept_counts[(sid, taxonomy, concept, unit)] == 0 for sid in company_map)}
        for taxonomy, concept, unit in SELECTED_CONCEPTS
    ]
    return {
        "schema_version": SCHEMA_VERSION, "code_revision": code_revision,
        "cohort_code": CURRENT_SURVIVORS_COHORT, "cutoff": cutoff.isoformat(),
        "data_capability_tier": "B", "read_only": True,
        "fact_reporting_period_end_window": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "filing_scope": "All stored approved-form filings accepted on or before cutoff; no lower acceptance-date bound.",
        "summary": {"company_count": len(company_map), "filing_count": len(filing_map),
                    "resolved_selected_fact_count": sum(concept_counts.values()),
                    "companies_without_filings": sum(not row["filing_count"] for row in by_company),
                    "companies_without_selected_facts": sum(not row["selected_concepts_present"] for row in by_company)},
        "selected_concept_coverage": concept_summary,
        "accepted_form_coverage": [
            {"canonical_form": form,
             "filing_count": sum(len(forms[(sid, form)]) for sid in company_map),
             "companies_present": sum(bool(forms[(sid, form)]) for sid in company_map),
             "amendment_count": sum(item.submitted_form.endswith("/A")
                                    for sid in company_map for item in forms[(sid, form)])}
            for form in sorted(RESEARCH_RELEVANT_FORMS)
        ],
        "availability_rule_counts": dict(sorted(availability_rules.items())),
        "selected_fact_lineage_sha256": lineage.hexdigest(),
        "excluded_loaded_record_counts": dict(sorted(excluded.items())),
        "by_company": by_company, "by_company_form": by_form,
        "by_company_concept": by_concept, "by_company_concept_form_period": by_period,
        "limitations": [
            "Local inventory, not independent verification of complete SEC filing coverage or model readiness.",
            "Fixed current-survivors cohort is survivorship-biased; current tickers/CIKs are display identifiers, not historical membership.",
            "Legacy frozen facts retain Tier-B acceptance-plus-five-minutes assumptions; later observations cannot rewrite earlier cutoffs.",
            "Zero observations may reflect alternative tags, foreign reporting, or missing ingestion; no automatic repair is performed.",
            "8-K metadata is counted without expecting accounting facts; amended accessions remain separate filings.",
            "Exact start/end periods are retained; annual and year-to-date figures are not inferred to be standalone quarters.",
            "SQL excludes unavailable facts before loading; excluded_loaded_record_counts is not a whole-database exclusion audit.",
        ],
    }


class PostgresSecCoverageRepository(PostgresSecFactResolver):
    """Reuse research resolution within one database-enforced read-only snapshot."""

    def __init__(self, database_url: str) -> None:
        super().__init__(database_url)
        from psycopg import IsolationLevel
        self._connection.read_only = True
        self._connection.isolation_level = IsolationLevel.REPEATABLE_READ

    def companies(self) -> list[Company]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT s.security_id::text, s.issuer_name,
                     ARRAY(SELECT DISTINCT l.ticker FROM quantrade.listings l
                           WHERE l.security_id=s.security_id AND l.valid_to IS NULL ORDER BY l.ticker),
                     ARRAY(SELECT DISTINCT i.identifier_value FROM quantrade.security_identifiers i
                           WHERE i.security_id=s.security_id AND i.identifier_type='cik'
                             AND i.valid_to IS NULL ORDER BY i.identifier_value)
                   FROM quantrade.research_cohort_memberships m
                   JOIN quantrade.research_cohorts c USING (research_cohort_id)
                   JOIN quantrade.securities s USING (security_id)
                   WHERE c.cohort_code=%s ORDER BY s.security_id""", (CURRENT_SURVIVORS_COHORT,),
            )
            return [Company(row[0], row[1], tuple(row[2]), tuple(row[3])) for row in cursor.fetchall()]

    def filings(self, security_ids: list[str], cutoff: datetime) -> list[Filing]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT filing_id::text, security_id::text, accession_number,
                          COALESCE(submitted_form, form), accepted_at, period_end
                   FROM quantrade.filings WHERE security_id=ANY(%s::uuid[]) AND accepted_at<=%s
                   ORDER BY filing_id""", (security_ids, cutoff),
            )
            return [Filing(*row) for row in cursor.fetchall()]

    def facts(self, security_ids: list[str], cutoff: datetime, period_start: date):
        for start in range(0, len(security_ids), 50):
            batch = security_ids[start:start + 50]
            for taxonomy, concepts in (("us-gaap", US_GAAP_CONCEPTS), ("dei", DEI_CONCEPTS)):
                yield from self.resolve(
                    security_ids=batch, taxonomy=taxonomy, concepts=concepts,
                    formation_date=cutoff.astimezone(TORONTO).date(), decision_at=cutoff,
                    earliest_period_end=period_start,
                )
            print(f"SEC coverage: {min(start + 50, len(security_ids))}/{len(security_ids)} companies inspected", flush=True)


def render_summary(report: dict) -> str:
    summary = report["summary"]
    lines = ["# SEC coverage report", "", f"As of: {report['cutoff']}", "",
             f"{summary['company_count']} companies; {summary['filing_count']:,} approved-form filings; "
             f"{summary['resolved_selected_fact_count']:,} resolved selected facts.", "",
             f"Companies without filings: {summary['companies_without_filings']}. "
             f"Companies without selected facts in the window: {summary['companies_without_selected_facts']}.", "",
             f"Fact period-end window: {report['fact_reporting_period_end_window']['start']} to "
             f"{report['fact_reporting_period_end_window']['end']}.", "",
             report["filing_scope"], "", "| Accepted form | Filings | Including amendments | Companies |",
             "| --- | ---: | ---: | ---: |"]
    for row in report["accepted_form_coverage"]:
        lines.append(f"| {row['canonical_form']} | {row['filing_count']:,} | {row['amendment_count']:,} | {row['companies_present']} |")
    lines.extend(["", "| Concept | Present companies | Not observed |", "| --- | ---: | ---: |"])
    for row in report["selected_concept_coverage"]:
        lines.append(f"| {row['taxonomy']}:{row['concept']} ({row['unit']}) | {row['companies_present']} | {row['companies_not_observed']} |")
    lines.extend(["", "Detailed company, form, concept and exact period breakdowns: `coverage.json`.", "", "## Limits", ""])
    lines.extend(f"- {note}" for note in report["limitations"])
    return "\n".join(lines) + "\n"


def publish_report(report: dict, output: Path) -> None:
    # A unique directory and last-written completion manifest avoid overwriting
    # earlier reports or mistaking a partial write for a finished publication.
    output.mkdir(parents=True, exist_ok=False)
    payload = json.dumps(report, default=lambda value: value.isoformat(), sort_keys=True, indent=2) + "\n"
    files = {"coverage.json": payload, "summary.md": render_summary(report)}
    hashes = {}
    for name, content in files.items():
        data = content.encode("utf-8")
        with (output / name).open("xb") as handle:
            handle.write(data)
        hashes[name] = sha256(data).hexdigest()
    manifest = {"schema_version": SCHEMA_VERSION, "status": "completed", "sha256": hashes,
                "generated_at": datetime.now(timezone.utc).isoformat(), "code_revision": report["code_revision"]}
    with (output / "manifest.json").open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, sort_keys=True, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--as-of", type=datetime.fromisoformat)
    parser.add_argument("--period-start", type=date.fromisoformat)
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--output", type=Path, required=True, help="New report directory; must not exist")
    args = parser.parse_args()
    cutoff = _aware(args.as_of or datetime.now(timezone.utc))
    period_start = args.period_start or cutoff.astimezone(TORONTO).date() - timedelta(days=730)
    if period_start > cutoff.astimezone(TORONTO).date():
        parser.error("--period-start must not follow --as-of")
    if args.output.exists():
        parser.error("output already exists; reports must not be overwritten")
    settings = _settings(args.env_file)
    if not settings.database_url:
        parser.error("DATABASE_URL is required")
    repository = PostgresSecCoverageRepository(settings.database_url)
    try:
        companies = repository.companies()
        ids = [item.security_id for item in companies]
        report = build_report(
            companies=companies, filings=repository.filings(ids, cutoff),
            facts=repository.facts(ids, cutoff, period_start), cutoff=cutoff,
            period_start=period_start, code_revision=args.code_revision,
        )
    finally:
        repository.close()
    publish_report(report, args.output)
    print(json.dumps({"output": str(args.output), **report["summary"]}, sort_keys=True))


if __name__ == "__main__":
    main()
