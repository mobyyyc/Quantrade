"""CLI for registering the fixed Tier-B historical research cohort."""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import Settings
from .historical_cohorts import PostgresHistoricalCohortRepository, register_current_survivors_cohort
from .ingest_security_master import _file_path_from_uri
from .run_manifest import RunManifest, SourceInput


def main() -> None:
    parser = argparse.ArgumentParser(description="Register the fixed current-survivors historical research cohort")
    parser.add_argument("--source-universe-code", default="sp500")
    parser.add_argument("--code-revision", required=True, help="Current lowercase Git SHA")
    parser.add_argument("--env-file", default=".env")
    arguments = parser.parse_args()

    from .score_run import _settings

    settings = _settings(Path(arguments.env_file))
    settings.require_runtime_storage()
    assert settings.database_url is not None and settings.raw_artifacts_uri is not None
    repository = PostgresHistoricalCohortRepository(settings.database_url)
    try:
        report = register_current_survivors_cohort(
            repository, source_universe_code=arguments.source_universe_code,
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
                provider="manual",
                source_reference=f"cohort:{report.cohort_code}",
                raw_artifact_uris=(report.raw_artifact_uri,),
            ),
        ),
        status="completed",
        note=report.manifest_note(),
    )
    manifest.write(_file_path_from_uri(settings.raw_artifacts_uri) / "manifests" / f"{manifest.run_id}.json")
    print(report.manifest_note())


if __name__ == "__main__":
    main()
