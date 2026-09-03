"""Plan and enforce conservative, recoverable retention for local research storage."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
from urllib.parse import unquote, urlparse

from .quality import DataQualityError
from .score_run import _settings


SCHEMA_VERSION = "storage_retention_v1"
INCOMPLETE_REPORT_DAYS = 7
LOG_DAYS = 30
ORPHAN_RAW_DAYS = 90
COMPLETED_REPORT_DAYS = 365
REPORT_MINIMUMS = {"sec-coverage": 12, "database-storage": 52}
PRESERVED_RAW_DIRECTORIES = {"manifests"}


@dataclass(frozen=True)
class Candidate:
    path: str
    category: str
    reason: str
    bytes: int
    modified_ns: int
    is_directory: bool


def _contained(path: Path, root: Path) -> Path:
    resolved, resolved_root = path.resolve(), root.resolve()
    if not resolved.is_relative_to(resolved_root) or resolved == resolved_root:
        raise DataQualityError(f"retention target escapes or equals its protected root: {path}")
    return resolved


def _file_uri_path(uri: str) -> Path | None:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    value = unquote(parsed.path)
    if os.name == "nt" and len(value) >= 3 and value[0] == "/" and value[2] == ":":
        value = value[1:]
    return Path(value).resolve()


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _candidate(path: Path, *, root: Path, category: str, reason: str) -> Candidate:
    resolved = _contained(path, root)
    if path.is_symlink():
        raise DataQualityError(f"retention refuses symbolic links: {path}")
    stat = resolved.stat()
    return Candidate(str(resolved), category, reason, _size(resolved), stat.st_mtime_ns,
                     resolved.is_dir())


def _completed_report(path: Path) -> tuple[bool, str | None]:
    manifest = path / "manifest.json"
    if not manifest.is_file():
        return False, None
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, None
    return payload.get("status") == "completed", payload.get("status")


def plan_retention(*, data_root: Path, referenced_artifacts: set[Path], now: datetime) -> list[Candidate]:
    """Return safe quarantine candidates without mutating storage."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise DataQualityError("retention timestamp requires a UTC offset")
    data_root = data_root.resolve()
    candidates: list[Candidate] = []
    derived = data_root / "derived"
    for family, minimum in REPORT_MINIMUMS.items():
        root = derived / family
        if not root.is_dir():
            continue
        completed: list[Path] = []
        for report in sorted((item for item in root.iterdir() if item.is_dir()), reverse=True):
            is_complete, status = _completed_report(report)
            age = now - datetime.fromtimestamp(report.stat().st_mtime, timezone.utc)
            if not is_complete and age >= timedelta(days=INCOMPLETE_REPORT_DAYS):
                candidates.append(_candidate(report, root=root, category="incomplete_report",
                                             reason=f"{family} report is incomplete for at least {INCOMPLETE_REPORT_DAYS} days"))
            elif is_complete:
                completed.append(report)
        for report in completed[minimum:]:
            age = now - datetime.fromtimestamp(report.stat().st_mtime, timezone.utc)
            if age >= timedelta(days=COMPLETED_REPORT_DAYS):
                candidates.append(_candidate(report, root=root, category="aged_operational_report",
                                             reason=f"older than {COMPLETED_REPORT_DAYS} days; newest {minimum} retained"))

    logs = data_root / "logs"
    if logs.is_dir():
        for item in logs.rglob("*"):
            if item.is_file() and not item.is_symlink():
                age = now - datetime.fromtimestamp(item.stat().st_mtime, timezone.utc)
                if age >= timedelta(days=LOG_DAYS):
                    candidates.append(_candidate(item, root=logs, category="aged_log",
                                                 reason=f"log is at least {LOG_DAYS} days old"))

    raw = data_root / "raw"
    if raw.is_dir():
        references = {path.resolve() for path in referenced_artifacts}
        for item in raw.rglob("*"):
            if not item.is_file() or item.is_symlink():
                continue
            relative = item.relative_to(raw)
            if relative.parts and relative.parts[0] in PRESERVED_RAW_DIRECTORIES:
                continue
            if item.resolve() in references:
                continue
            age = now - datetime.fromtimestamp(item.stat().st_mtime, timezone.utc)
            if age >= timedelta(days=ORPHAN_RAW_DAYS):
                candidates.append(_candidate(item, root=raw, category="orphan_raw_artifact",
                                             reason=f"unreferenced by the database for at least {ORPHAN_RAW_DAYS} days"))
    return sorted(candidates, key=lambda item: (item.category, item.path))


class PostgresArtifactReader:
    """Read the immutable raw-artifact ledger without modifying it."""

    def __init__(self, database_url: str) -> None:
        import psycopg
        self.connection = psycopg.connect(database_url)
        self.connection.read_only = True

    def close(self) -> None:
        self.connection.close()

    def inventory(self) -> tuple[set[Path], dict[str, int]]:
        paths: set[Path] = set()
        schemes: dict[str, int] = {}
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT storage_uri FROM quantrade.raw_artifacts")
            for (uri,) in cursor.fetchall():
                scheme = urlparse(uri).scheme
                schemes[scheme] = schemes.get(scheme, 0) + 1
                path = _file_uri_path(uri)
                if path is not None:
                    paths.add(path)
        return paths, schemes


def _build_plan(*, data_root: Path, candidates: list[Candidate], schemes: dict[str, int],
                now: datetime) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": now.astimezone(timezone.utc).isoformat(),
        "mode": "dry_run",
        "data_root": str(data_root.resolve()),
        "candidate_count": len(candidates),
        "candidate_bytes": sum(item.bytes for item in candidates),
        "database_artifact_schemes": schemes,
        "candidates": [asdict(item) for item in candidates],
        "guarantees": [
            "Database rows, compact receipts, retrieval events, datasets, models, backups, and manifests are never deleted.",
            "Database-referenced file artifacts are never candidates.",
            "Apply moves candidates into recoverable quarantine; it does not permanently delete them.",
        ],
    }


def quarantine(*, candidates: list[Candidate], data_root: Path, destination: Path) -> list[dict]:
    _contained(destination, data_root / "quarantine")
    prepared: list[tuple[Candidate, Path, Path]] = []
    for item in candidates:
        source = Path(item.path)
        _contained(source, data_root)
        stat = source.stat()
        if stat.st_mtime_ns != item.modified_ns or _size(source) != item.bytes:
            raise DataQualityError(f"retention candidate changed after planning: {source}")
        target = destination / source.relative_to(data_root.resolve())
        if target.exists():
            raise DataQualityError(f"quarantine destination already exists: {target}")
        prepared.append((item, source, target))
    destination.mkdir(parents=True, exist_ok=False)
    moved: list[dict] = []
    ledger_path = destination / "ledger.json"
    ledger = {"schema_version": SCHEMA_VERSION, "status": "moving",
              "created_at": datetime.now(timezone.utc).isoformat(), "items": moved}
    ledger_path.write_text(json.dumps(ledger, sort_keys=True, indent=2), encoding="utf-8")
    for item, source, target in prepared:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        moved.append({"source": str(source), "quarantine": str(target), "bytes": item.bytes,
                      "category": item.category})
        ledger["items"] = moved
        ledger_path.write_text(json.dumps(ledger, sort_keys=True, indent=2), encoding="utf-8")
    ledger["status"] = "quarantined"
    ledger_path.write_text(json.dumps(ledger, sort_keys=True, indent=2), encoding="utf-8")
    return moved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Move current candidates into quarantine")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; retention plans are immutable")
    settings = _settings(args.env_file)
    if not settings.database_url:
        parser.error("DATABASE_URL is required")
    reader = PostgresArtifactReader(settings.database_url)
    try:
        referenced, schemes = reader.inventory()
    finally:
        reader.close()
    now = datetime.now(timezone.utc)
    candidates = plan_retention(data_root=args.data_root, referenced_artifacts=referenced, now=now)
    payload = _build_plan(data_root=args.data_root, candidates=candidates, schemes=schemes, now=now)
    if args.apply and candidates:
        quarantine_root = args.data_root / "quarantine" / args.output.stem
        payload["mode"] = "quarantine"
        payload["quarantined"] = quarantine(candidates=candidates, data_root=args.data_root.resolve(),
                                             destination=quarantine_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, indent=2)
    print(json.dumps({"output": str(args.output), "mode": payload["mode"],
                      "candidates": len(candidates), "bytes": payload["candidate_bytes"]}, sort_keys=True))


if __name__ == "__main__":
    main()
