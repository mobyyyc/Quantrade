"""Command-line entry point for a dated SEC security-master ingestion."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from .config import Settings
from .run_manifest import RunManifest, SourceInput
from .sec_edgar import (
    COMPANY_TICKERS_EXCHANGE_URL,
    SecEdgarClient,
    normalize_security_master,
    parse_company_tickers_exchange,
)
from .security_master import (
    FileRawArtifactStore,
    PostgresSecurityMasterRepository,
    persist_security_master_snapshot,
)


def _file_path_from_uri(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError("P2.1 supports a file:// RAW_ARTIFACTS_URI only")
    path = unquote(parsed.path)
    if len(path) >= 3 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return Path(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest SEC ticker and exchange associations")
    parser.add_argument("--code-revision", required=True, help="Current lowercase Git SHA")
    arguments = parser.parse_args()

    settings = Settings.from_environment()
    settings.require_runtime_storage()
    settings.require_sec_access()
    assert settings.database_url is not None
    assert settings.raw_artifacts_uri is not None
    retrieved_at = datetime.now(timezone.utc)

    payload = SecEdgarClient(settings.sec_user_agent or "").fetch_company_tickers_exchange()
    associations = parse_company_tickers_exchange(payload)
    rows, unmapped = normalize_security_master(associations, retrieved_at.date())
    artifact = FileRawArtifactStore(settings.raw_artifacts_uri).store(payload, retrieved_at)

    repository = PostgresSecurityMasterRepository(settings.database_url)
    try:
        report = persist_security_master_snapshot(
            repository,
            artifact,
            COMPANY_TICKERS_EXCHANGE_URL,
            rows,
            len(unmapped),
        )
    finally:
        repository.close()

    manifest = RunManifest.create(
        settings=settings,
        run_kind="ingestion",
        code_revision=arguments.code_revision,
        data_capability_tier="B",
        source_inputs=(
            SourceInput(
                provider="sec_edgar",
                source_reference=COMPANY_TICKERS_EXCHANGE_URL,
                raw_artifact_uris=(artifact.storage_uri,),
            ),
        ),
        status="completed",
        note=report.manifest_note(),
    )
    manifest.write(_file_path_from_uri(settings.raw_artifacts_uri) / "manifests" / f"{manifest.run_id}.json")
    print(report.manifest_note())


if __name__ == "__main__":
    main()
