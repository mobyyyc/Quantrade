"""Command-line entry point for SEC submissions and company-facts ingestion."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
import time

from .config import Settings
from .filings import PostgresFilingRepository, persist_sec_filings
from .ingest_security_master import _file_path_from_uri
from .run_manifest import RunManifest, SourceInput
from .sec_edgar import COMPANY_FACTS_URL, SUBMISSIONS_URL, SecEdgarClient, parse_company_facts, parse_submissions
from .security_master import FileRawArtifactStore


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest SEC filing metadata and facts for one CIK")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--cik")
    source.add_argument("--ciks-file")
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--minimum-request-interval", type=float, default=0.12)
    arguments = parser.parse_args()
    if arguments.minimum_request_interval < 0:
        parser.error("--minimum-request-interval must be non-negative")
    ciks = [arguments.cik.zfill(10)] if arguments.cik else _ciks_from_file(arguments.ciks_file)

    settings = Settings.from_environment()
    settings.require_runtime_storage()
    settings.require_sec_access()
    assert settings.database_url is not None and settings.raw_artifacts_uri is not None
    client = SecEdgarClient(settings.sec_user_agent or "")
    store = FileRawArtifactStore(settings.raw_artifacts_uri)
    repository = PostgresFilingRepository(settings.database_url)
    total_filings = 0
    total_facts = 0
    source_inputs: list[SourceInput] = []
    try:
        for index, cik in enumerate(ciks):
            retrieved_at = datetime.now(timezone.utc)
            submissions_payload = client.fetch_submissions(cik)
            time.sleep(arguments.minimum_request_interval)
            facts_payload = client.fetch_company_facts(cik)
            filings = parse_submissions(submissions_payload)
            facts = parse_company_facts(facts_payload, {filing.accession_number: filing for filing in filings})
            submissions_artifact = store.store(submissions_payload, retrieved_at, category="sec-submissions")
            facts_artifact = store.store(facts_payload, retrieved_at, category="sec-company-facts")
            submissions_reference = SUBMISSIONS_URL.format(cik=cik)
            facts_reference = COMPANY_FACTS_URL.format(cik=cik)
            report = persist_sec_filings(repository, cik, filings, facts, submissions_artifact, facts_artifact, submissions_reference, facts_reference)
            total_filings += report.filings
            total_facts += report.facts
            source_inputs.extend((
                SourceInput(provider="sec_edgar", source_reference=submissions_reference, raw_artifact_uris=(submissions_artifact.storage_uri,)),
                SourceInput(provider="sec_edgar", source_reference=facts_reference, raw_artifact_uris=(facts_artifact.storage_uri,)),
            ))
            if index + 1 < len(ciks):
                time.sleep(arguments.minimum_request_interval)
    finally:
        repository.close()
    manifest = RunManifest.create(
        settings=settings, run_kind="ingestion", code_revision=arguments.code_revision, data_capability_tier="B",
        source_inputs=tuple(source_inputs), status="completed",
        note=f"ciks={len(ciks)}; filings={total_filings}; facts={total_facts}; filing_availability=acceptance_timestamp",
    )
    manifest.write(_file_path_from_uri(settings.raw_artifacts_uri) / "manifests" / f"{manifest.run_id}.json")
    print(manifest.note)


if __name__ == "__main__":
    main()
