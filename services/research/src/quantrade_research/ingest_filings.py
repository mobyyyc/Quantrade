"""Command-line entry point for SEC submissions and company-facts ingestion."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, time as wall_time, timezone
from pathlib import Path
import time
from zoneinfo import ZoneInfo

from .filings import PostgresFilingRepository, StoredSource, persist_sec_filings
from .ingest_security_master import _file_path_from_uri
from .run_manifest import RunManifest, SourceInput
from .sec_edgar import (
    COMPANY_FACTS_URL,
    daily_master_index_url,
    parse_daily_master_index,
    SUBMISSIONS_URL,
    SUBMISSION_HISTORY_URL,
    SecEdgarClient,
    SecEdgarError,
    SecEdgarNotFoundError,
    merge_filings,
    parse_company_facts,
    parse_submission_history,
    parse_submissions,
    submission_history_names,
)
from .security_master import FileRawArtifactStore


_SEC_PARSER_VERSION = "sec_edgar_parser_v1"
_MODEL_RELEVANT_FINANCIAL_FORMS = frozenset({"10-K", "10-Q", "20-F", "40-F"})
_TORONTO = ZoneInfo("America/Toronto")
_EXPECTED_DAILY_INDEX_PUBLICATION = wall_time(22, 15)


def _record_source(
    repository: PostgresFilingRepository, store: FileRawArtifactStore, payload: bytes,
    retrieved_at: datetime, source_reference: str, *, response_category: str,
    raw_category: str, compact_receipts: bool,
) -> StoredSource:
    if compact_receipts:
        return repository.persist_compact_receipt(
            payload, source_reference, response_category, retrieved_at,
            parser_version=_SEC_PARSER_VERSION,
        )
    return repository.persist_raw_artifact(
        store.store(payload, retrieved_at, category=raw_category), source_reference,
    )


def _ciks_from_file(path: str) -> list[str]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        if not rows.fieldnames or "cik" not in rows.fieldnames:
            raise argparse.ArgumentTypeError("the CIK CSV must include a cik column")
        values = [str(row.get("cik", "")).strip().zfill(10) for row in rows]
    ciks = sorted(set(value for value in values if value.isdigit() and len(value) == 10))
    if not ciks:
        raise argparse.ArgumentTypeError("the CIK CSV has no valid CIK values")
    return ciks


def _ciks(value: str) -> list[str]:
    values = [item.strip().zfill(10) for item in value.split(",") if item.strip()]
    ciks = sorted(set(value for value in values if value.isdigit() and len(value) == 10))
    if not ciks:
        raise argparse.ArgumentTypeError("at least one valid CIK is required")
    return ciks


def _new_accession_numbers(filings, known_accessions: set[str]) -> list[str]:
    """Return stable new accessions from a submissions response."""
    return sorted({filing.accession_number for filing in filings} - known_accessions)


def _new_filings(filings, known_accessions: set[str]):
    """Return only newly discovered submission records in SEC response order."""
    seen: set[str] = set()
    new_filings = []
    for filing in filings:
        if filing.accession_number in known_accessions or filing.accession_number in seen:
            continue
        seen.add(filing.accession_number)
        new_filings.append(filing)
    return new_filings


def _requires_company_facts(filings) -> bool:
    """Company Facts is useful only for new annual/interim financial filings."""
    return any(filing.form in _MODEL_RELEVANT_FINANCIAL_FORMS for filing in filings)


def _daily_index_candidates(ciks: list[str], index_ciks: set[str]) -> list[str]:
    """Return only current-universe CIKs that appear in the SEC's daily index."""
    return sorted(set(ciks).intersection(index_ciks))


def _fetch_daily_master_index_with_retry(
    client: SecEdgarClient, filing_date: date, *, attempts: int, retry_seconds: float,
    sleep=time.sleep,
) -> bytes:
    """Fetch a daily index with bounded retries, never a cohort-wide fallback."""
    if attempts < 1:
        raise ValueError("daily index attempts must be positive")
    for attempt in range(1, attempts + 1):
        try:
            return client.fetch_daily_master_index(filing_date)
        except SecEdgarNotFoundError:
            raise
        except SecEdgarError as error:
            if attempt == attempts:
                raise SecEdgarError(
                    f"daily index retrieval failed for {filing_date.isoformat()} after {attempts} attempts: {error}"
                ) from error
            sleep(retry_seconds * attempt)
    raise AssertionError("daily index retry loop did not return or raise")  # pragma: no cover


def _daily_index_dates(start_date: date, end_date: date) -> list[date]:
    """Return every calendar date in the inclusive filing-discovery interval."""
    if end_date < start_date:
        raise ValueError("daily index end date must not precede the start date")
    return [date.fromordinal(value) for value in range(start_date.toordinal(), end_date.toordinal() + 1)]


def _is_pending_current_daily_index(
    filing_date: date, error: SecEdgarError, *, observed_at: datetime | None = None,
) -> bool:
    """Identify SEC's pre-publication absence without hiding a later real outage."""
    observed = (observed_at or datetime.now(_TORONTO)).astimezone(_TORONTO)
    return (
        (isinstance(error, SecEdgarNotFoundError) or "HTTP 403" in str(error))
        and filing_date == observed.date()
        and observed.time() < _EXPECTED_DAILY_INDEX_PUBLICATION
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest SEC filing metadata and facts for one CIK")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--cik")
    source.add_argument("--ciks", type=_ciks)
    source.add_argument("--ciks-file")
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--include-history", action="store_true", help="Follow dated SEC submission-history references for historical fact eligibility")
    parser.add_argument("--incremental", action="store_true", help="Fetch Company Facts only when current submissions contain a new accession")
    parser.add_argument("--daily-index-start-date", type=date.fromisoformat, help="Inclusive start date for SEC daily-index filing discovery")
    parser.add_argument("--daily-index-end-date", type=date.fromisoformat, help="Inclusive end date for SEC daily-index filing discovery")
    parser.add_argument("--compact-receipts", action="store_true", help="Store source metadata receipts without routine payload files")
    parser.add_argument("--daily-index-attempts", type=int, default=3, help="Bounded SEC daily-index request attempts")
    parser.add_argument("--daily-index-retry-seconds", type=float, default=0.5, help="Base backoff between SEC daily-index attempts")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--minimum-request-interval", type=float, default=0.12)
    arguments = parser.parse_args()
    if arguments.minimum_request_interval < 0:
        parser.error("--minimum-request-interval must be non-negative")
    if arguments.daily_index_attempts < 1:
        parser.error("--daily-index-attempts must be positive")
    if arguments.daily_index_retry_seconds < 0:
        parser.error("--daily-index-retry-seconds must be non-negative")
    if arguments.incremental and arguments.include_history:
        parser.error("--incremental cannot be combined with --include-history")
    if arguments.compact_receipts and arguments.include_history:
        parser.error("--compact-receipts cannot be combined with --include-history")
    if (arguments.daily_index_start_date or arguments.daily_index_end_date) and not arguments.incremental:
        parser.error("daily-index date bounds require --incremental")
    if bool(arguments.daily_index_start_date) != bool(arguments.daily_index_end_date):
        parser.error("both --daily-index-start-date and --daily-index-end-date are required together")
    ciks = ([arguments.cik.zfill(10)] if arguments.cik else arguments.ciks
            if arguments.ciks else _ciks_from_file(arguments.ciks_file))
    requested_ciks = ciks

    from .score_run import _settings

    settings = _settings(Path(arguments.env_file))
    settings.require_runtime_storage()
    settings.require_sec_access()
    assert settings.database_url is not None and settings.raw_artifacts_uri is not None
    client = SecEdgarClient(settings.sec_user_agent or "")
    store = FileRawArtifactStore(settings.raw_artifacts_uri)
    repository = PostgresFilingRepository(settings.database_url)
    total_filings = 0
    total_facts = 0
    refreshed_ciks = 0
    new_accession_count = 0
    company_facts_requests = 0
    source_inputs: list[SourceInput] = []
    try:
        missing_index_dates: list[date] = []
        if arguments.daily_index_start_date:
            indexed_ciks: set[str] = set()
            for filing_date in _daily_index_dates(arguments.daily_index_start_date, arguments.daily_index_end_date):
                try:
                    index_payload = _fetch_daily_master_index_with_retry(
                        client, filing_date, attempts=arguments.daily_index_attempts,
                        retry_seconds=arguments.daily_index_retry_seconds,
                    )
                    index_records = parse_daily_master_index(index_payload)
                except SecEdgarNotFoundError as error:
                    if _is_pending_current_daily_index(filing_date, error):
                        raise SecEdgarError(
                            f"SEC daily filing index for {filing_date.isoformat()} has not been published yet; "
                            "retry after 10:00 p.m. Toronto time"
                        ) from error
                    missing_index_dates.append(filing_date)
                    continue
                except SecEdgarError as error:
                    if _is_pending_current_daily_index(filing_date, error):
                        raise SecEdgarError(
                            f"SEC daily filing index for {filing_date.isoformat()} has not been published yet; "
                            "retry after 10:00 p.m. Toronto time"
                        ) from error
                    raise SecEdgarError(
                        f"daily index discovery is incomplete for {filing_date.isoformat()}; "
                        "no cohort-wide submissions fallback will run"
                    ) from error
                index_retrieved_at = datetime.now(timezone.utc)
                index_url = daily_master_index_url(filing_date)
                index_source = _record_source(
                    repository, store, index_payload, index_retrieved_at, index_url,
                    response_category="sec_daily_index", raw_category="sec-daily-master-index",
                    compact_receipts=arguments.compact_receipts,
                )
                source_inputs.append(SourceInput(
                    provider="sec_edgar", source_reference=index_url,
                    raw_artifact_uris=(index_source.storage_uri,),
                ))
                indexed_ciks.update(
                    record.cik for record in index_records if record.filed_on == filing_date
                )
            ciks = _daily_index_candidates(ciks, indexed_ciks)
        for index, cik in enumerate(ciks):
            retrieved_at = datetime.now(timezone.utc)
            submissions_payload = client.fetch_submissions(cik)
            filings_groups = [parse_submissions(submissions_payload)]
            submissions_reference = SUBMISSIONS_URL.format(cik=cik)
            submissions_source = _record_source(
                repository, store, submissions_payload, retrieved_at, submissions_reference,
                response_category="sec_submissions", raw_category="sec-submissions",
                compact_receipts=arguments.compact_receipts,
            )
            artifacts: list[StoredSource] = [submissions_source]
            known_accessions = repository.known_accession_numbers(
                cik, [filing.accession_number for filing in filings_groups[0]],
            ) if arguments.incremental else set()
            if arguments.incremental and not _new_accession_numbers(filings_groups[0], known_accessions):
                source_inputs.append(SourceInput(
                    provider="sec_edgar", source_reference=submissions_reference,
                    raw_artifact_uris=(submissions_source.storage_uri,),
                ))
                if index + 1 < len(ciks):
                    time.sleep(arguments.minimum_request_interval)
                continue
            if arguments.include_history:
                for history_name in submission_history_names(submissions_payload):
                    time.sleep(arguments.minimum_request_interval)
                    history_retrieved_at = datetime.now(timezone.utc)
                    history_payload = client.fetch_submission_history(history_name)
                    filings_groups.append(parse_submission_history(history_payload))
                    artifacts.append(_record_source(
                        repository, store, history_payload, history_retrieved_at,
                        SUBMISSION_HISTORY_URL.format(name=history_name),
                        response_category="sec_submissions", raw_category="sec-submission-history",
                        compact_receipts=arguments.compact_receipts,
                    ))
            filings = merge_filings(*filings_groups)
            if arguments.incremental:
                filings = _new_filings(filings, known_accessions)
            new_accession_count += len(filings)
            facts = []
            facts_source = None
            facts_reference = COMPANY_FACTS_URL.format(cik=cik)
            if not arguments.incremental or _requires_company_facts(filings):
                time.sleep(arguments.minimum_request_interval)
                facts_payload = client.fetch_company_facts(cik)
                facts = parse_company_facts(facts_payload, {filing.accession_number: filing for filing in filings})
                facts_source = _record_source(
                    repository, store, facts_payload, retrieved_at, facts_reference,
                    response_category="sec_company_facts", raw_category="sec-company-facts",
                    compact_receipts=arguments.compact_receipts,
                )
                company_facts_requests += 1
            source_by_accession = {
                filing.accession_number: artifacts[group_index]
                for group_index, group in enumerate(filings_groups)
                for filing in group
            }
            report = persist_sec_filings(
                repository, cik, filings, facts, submissions_source, facts_source, source_by_accession,
            )
            total_filings += report.filings
            total_facts += report.facts
            refreshed_ciks += 1
            source_inputs.extend(
                SourceInput(provider="sec_edgar", source_reference=source.source_reference, raw_artifact_uris=(source.storage_uri,))
                for source in artifacts
            )
            if facts_source:
                source_inputs.append(SourceInput(provider="sec_edgar", source_reference=facts_reference, raw_artifact_uris=(facts_source.storage_uri,)))
            if index + 1 < len(ciks):
                time.sleep(arguments.minimum_request_interval)
    finally:
        repository.close()
    manifest = RunManifest.create(
        settings=settings, run_kind="ingestion", code_revision=arguments.code_revision, data_capability_tier="B",
        source_inputs=tuple(source_inputs), status="completed",
        note=(f"ciks_requested={len(requested_ciks)}; ciks_checked={len(ciks)}; filings={total_filings}; facts={total_facts}; "
              f"incremental={arguments.incremental}; refreshed_ciks={refreshed_ciks}; new_accessions={new_accession_count}; "
              f"company_facts_requests={company_facts_requests}; "
              f"daily_index_start_date={arguments.daily_index_start_date.isoformat() if arguments.daily_index_start_date else 'none'}; "
              f"daily_index_end_date={arguments.daily_index_end_date.isoformat() if arguments.daily_index_end_date else 'none'}; "
              f"missing_daily_indexes={','.join(item.isoformat() for item in missing_index_dates) or 'none'}; "
              "daily_index_fallback=none; "
              f"receipt_mode={'compact' if arguments.compact_receipts else 'payload_retained'}; "
              f"history_included={arguments.include_history}; filing_availability=acceptance_timestamp"),
    )
    manifest.write(_file_path_from_uri(settings.raw_artifacts_uri) / "manifests" / f"{manifest.run_id}.json")
    print(manifest.note)


if __name__ == "__main__":
    main()
