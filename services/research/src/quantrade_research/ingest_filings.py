"""Command-line entry point for SEC submissions and company-facts ingestion."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from .config import Settings
from .filings import PostgresFilingRepository, persist_sec_filings
from .ingest_security_master import _file_path_from_uri
from .run_manifest import RunManifest, SourceInput
from .sec_edgar import COMPANY_FACTS_URL, SUBMISSIONS_URL, SecEdgarClient, parse_company_facts, parse_submissions
from .security_master import FileRawArtifactStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest SEC filing metadata and facts for one CIK")
    parser.add_argument("--cik", required=True)
    parser.add_argument("--code-revision", required=True)
    arguments = parser.parse_args()
    cik = arguments.cik.zfill(10)

    settings = Settings.from_environment()
    settings.require_runtime_storage()
    settings.require_sec_access()
    assert settings.database_url is not None and settings.raw_artifacts_uri is not None
    client = SecEdgarClient(settings.sec_user_agent or "")
    retrieved_at = datetime.now(timezone.utc)
    submissions_payload = client.fetch_submissions(cik)
    facts_payload = client.fetch_company_facts(cik)
    filings = parse_submissions(submissions_payload)
    facts = parse_company_facts(facts_payload, {filing.accession_number: filing for filing in filings})
    store = FileRawArtifactStore(settings.raw_artifacts_uri)
    submissions_artifact = store.store(submissions_payload, retrieved_at, category="sec-submissions")
    facts_artifact = store.store(facts_payload, retrieved_at, category="sec-company-facts")
    submissions_reference = SUBMISSIONS_URL.format(cik=cik)
    facts_reference = COMPANY_FACTS_URL.format(cik=cik)

    repository = PostgresFilingRepository(settings.database_url)
    try:
        report = persist_sec_filings(repository, cik, filings, facts, submissions_artifact, facts_artifact, submissions_reference, facts_reference)
    finally:
        repository.close()
    manifest = RunManifest.create(
        settings=settings, run_kind="ingestion", code_revision=arguments.code_revision, data_capability_tier="B",
        source_inputs=(
            SourceInput(provider="sec_edgar", source_reference=submissions_reference, raw_artifact_uris=(submissions_artifact.storage_uri,)),
            SourceInput(provider="sec_edgar", source_reference=facts_reference, raw_artifact_uris=(facts_artifact.storage_uri,)),
        ), status="completed", note=report.manifest_note(),
    )
    manifest.write(_file_path_from_uri(settings.raw_artifacts_uri) / "manifests" / f"{manifest.run_id}.json")
    print(report.manifest_note())


if __name__ == "__main__":
    main()
