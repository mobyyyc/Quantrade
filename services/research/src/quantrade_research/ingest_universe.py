"""Command-line entry point for explicitly dated universe membership files."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from pathlib import Path

from .config import Settings
from .ingest_security_master import _file_path_from_uri
from .run_manifest import RunManifest, SourceInput
from .security_master import FileRawArtifactStore
from .universe import PostgresUniverseRepository, parse_universe_csv, persist_universe_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a dated universe-membership CSV")
    parser.add_argument("--input", type=Path, required=True, help="UTF-8 CSV with a cik column")
    parser.add_argument("--universe-code", required=True)
    parser.add_argument("--as-of-date", type=date.fromisoformat, required=True)
    parser.add_argument("--source-reference", required=True)
    parser.add_argument("--code-revision", required=True, help="Current lowercase Git SHA")
    parser.add_argument("--historical-membership-verified", action="store_true")
    parser.add_argument("--data-capability-tier", choices=("A", "B", "C"), default="B")
    arguments = parser.parse_args()

    settings = Settings.from_environment()
    settings.require_runtime_storage()
    assert settings.database_url is not None
    assert settings.raw_artifacts_uri is not None
    payload = arguments.input.read_bytes()
    ciks = parse_universe_csv(payload)
    artifact = FileRawArtifactStore(settings.raw_artifacts_uri).store(
        payload, datetime.now(timezone.utc), category="universe"
    )

    repository = PostgresUniverseRepository(settings.database_url)
    try:
        report = persist_universe_snapshot(
            repository, artifact, arguments.source_reference, arguments.universe_code,
            arguments.as_of_date, ciks, arguments.historical_membership_verified,
            arguments.data_capability_tier,
        )
    finally:
        repository.close()

    manifest = RunManifest.create(
        settings=settings,
        run_kind="ingestion",
        code_revision=arguments.code_revision,
        data_capability_tier=arguments.data_capability_tier,
        source_inputs=(
            SourceInput(
                provider="manual",
                source_reference=arguments.source_reference,
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
