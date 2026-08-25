"""Ingest a small, explicitly sourced manual security-master fallback."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path

from .config import Settings
from .ingest_security_master import _file_path_from_uri
from .run_manifest import RunManifest, SourceInput
from .sec_edgar import EXCHANGE_MIC_BY_SEC_NAME, SecurityMasterRow
from .security_master import FileRawArtifactStore, PostgresSecurityMasterRepository, persist_security_master_snapshot


class ManualSecurityMasterInputError(ValueError):
    """Raised when a fallback file cannot be traced to a current listing."""


def parse_manual_security_master_csv(payload: bytes, snapshot_date: date) -> list[SecurityMasterRow]:
    try:
        reader = csv.DictReader(StringIO(payload.decode("utf-8-sig")))
    except UnicodeDecodeError as error:
        raise ManualSecurityMasterInputError("manual security-master fallback must be UTF-8 CSV") from error
    required = {"ticker", "issuer_name", "cik", "exchange", "source"}
    if reader.fieldnames is None or not required.issubset({name.lower() for name in reader.fieldnames}):
        raise ManualSecurityMasterInputError("fallback CSV requires ticker, issuer_name, cik, exchange, and source columns")
    columns = {name.lower(): name for name in reader.fieldnames}
    rows: list[SecurityMasterRow] = []
    for record in reader:
        ticker = (record.get(columns["ticker"]) or "").strip().upper()
        issuer = (record.get(columns["issuer_name"]) or "").strip()
        cik = (record.get(columns["cik"]) or "").strip().zfill(10)
        exchange = (record.get(columns["exchange"]) or "").strip()
        source = (record.get(columns["source"]) or "").strip()
        exchange_mic = EXCHANGE_MIC_BY_SEC_NAME.get(exchange)
        if not ticker or not issuer or not cik.isdigit() or not source or exchange_mic is None:
            raise ManualSecurityMasterInputError("fallback CSV contains an invalid or unmapped listing")
        rows.append(SecurityMasterRow(cik, issuer, ticker, exchange_mic, snapshot_date))
    if not rows:
        raise ManualSecurityMasterInputError("fallback CSV contains no listings")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest an explicitly sourced manual security-master fallback")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--as-of-date", type=date.fromisoformat, required=True)
    parser.add_argument("--source-reference", required=True)
    parser.add_argument("--code-revision", required=True)
    arguments = parser.parse_args()
    settings = Settings.from_environment()
    settings.require_runtime_storage()
    assert settings.database_url is not None and settings.raw_artifacts_uri is not None
    payload = arguments.input.read_bytes()
    rows = parse_manual_security_master_csv(payload, arguments.as_of_date)
    retrieved_at = datetime.now(timezone.utc)
    artifact = FileRawArtifactStore(settings.raw_artifacts_uri).store(
        payload, retrieved_at, category="security-master-fallback",
    )
    repository = PostgresSecurityMasterRepository(settings.database_url)
    try:
        report = persist_security_master_snapshot(
            repository, artifact, arguments.source_reference, rows, 0,
            provider="manual", close_missing_sec_listings=False,
        )
    finally:
        repository.close()
    manifest = RunManifest.create(
        settings=settings, run_kind="ingestion", code_revision=arguments.code_revision,
        data_capability_tier="B",
        source_inputs=(SourceInput(provider="manual", source_reference=arguments.source_reference,
                                   raw_artifact_uris=(artifact.storage_uri,)),),
        status="completed", note=f"manual_security_master_fallback=true; {report.manifest_note()}",
    )
    manifest.write(_file_path_from_uri(settings.raw_artifacts_uri) / "manifests" / f"{manifest.run_id}.json")
    print(report.manifest_note())


if __name__ == "__main__":  # pragma: no cover
    main()
