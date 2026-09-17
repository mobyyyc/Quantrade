"""Measure the no-cost local operating footprint without mutating data."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
from statistics import median

from .database_storage_monitor import PostgresStorageReader, load_verified_report
from .quality import DataQualityError
from .score_run import _settings


GIB = 1024**3
SCHEMA_VERSION = "quantrade_local_capacity_v1"
THRESHOLD_VERSION = "quantrade_local_capacity_thresholds_v1"

FREE_WARNING_BYTES = 100 * GIB
FREE_CRITICAL_BYTES = 50 * GIB
FREE_WARNING_RATIO = 0.20
FREE_CRITICAL_RATIO = 0.10
DATABASE_WARNING_BYTES = 25 * GIB
DATABASE_CRITICAL_BYTES = 40 * GIB
RAW_WARNING_BYTES = 12 * GIB
RAW_CRITICAL_BYTES = 20 * GIB
BACKUP_WARNING_BYTES = 45 * GIB
BACKUP_CRITICAL_BYTES = 60 * GIB
BACKUP_AGE_WARNING_HOURS = 36.0
BACKUP_AGE_CRITICAL_HOURS = 72.0


@dataclass(frozen=True)
class TreeObservation:
    path: str
    bytes: int
    files: int


@dataclass(frozen=True)
class BackupObservation:
    count: int
    total_bytes: int
    median_bytes: int
    newest_at: datetime | None
    oldest_at: datetime | None
    per_copy_growth_bytes_per_day: float | None


@dataclass(frozen=True)
class DuplicateObservation:
    hash_groups: int
    extra_files: int
    duplicate_bytes: int


def measure_tree(path: Path) -> TreeObservation:
    """Measure regular files without following directory or file symlinks."""
    total = 0
    count = 0
    if path.exists():
        for root, directories, files in os.walk(path, followlinks=False):
            directories[:] = [name for name in directories if not (Path(root) / name).is_symlink()]
            for name in files:
                candidate = Path(root) / name
                if candidate.is_symlink():
                    continue
                try:
                    total += candidate.stat().st_size
                    count += 1
                except FileNotFoundError:
                    continue
    return TreeObservation(str(path), total, count)


def measure_backups(path: Path) -> BackupObservation:
    files = sorted(path.glob("*.dump"), key=lambda item: item.stat().st_mtime) if path.exists() else []
    if not files:
        return BackupObservation(0, 0, 0, None, None, None)
    sizes = [item.stat().st_size for item in files]
    times = [datetime.fromtimestamp(item.stat().st_mtime, timezone.utc) for item in files]
    elapsed_days = (times[-1] - times[0]).total_seconds() / 86400
    growth = (sizes[-1] - sizes[0]) / elapsed_days if elapsed_days > 0 else None
    return BackupObservation(
        len(files), sum(sizes), int(median(sizes)), times[-1], times[0], growth,
    )


def measure_content_addressed_duplicates(path: Path) -> DuplicateObservation:
    """Count extra physical files whose 64-hex filename records the same content hash."""
    groups: dict[str, list[int]] = {}
    if path.exists():
        for root, directories, files in os.walk(path, followlinks=False):
            directories[:] = [name for name in directories if not (Path(root) / name).is_symlink()]
            for name in files:
                candidate = Path(root) / name
                if candidate.is_symlink() or not re.fullmatch(r"[0-9a-f]{64}", candidate.stem):
                    continue
                try:
                    groups.setdefault(candidate.stem, []).append(candidate.stat().st_size)
                except FileNotFoundError:
                    continue
    repeated = [sizes for sizes in groups.values() if len(sizes) > 1]
    return DuplicateObservation(
        hash_groups=len(repeated),
        extra_files=sum(len(sizes) - 1 for sizes in repeated),
        duplicate_bytes=sum(sum(sizes) - max(sizes) for sizes in repeated),
    )


def database_growth_per_day(report_root: Path) -> tuple[float | None, str | None, str | None]:
    reports: list[dict] = []
    if report_root.exists():
        for directory in sorted(item for item in report_root.iterdir() if item.is_dir()):
            try:
                reports.append(load_verified_report(directory))
            except (DataQualityError, OSError, json.JSONDecodeError):
                continue
    if len(reports) < 2:
        return None, None, None
    first = reports[0]
    last = reports[-1]
    first_at = datetime.fromisoformat(first["captured_at"])
    last_at = datetime.fromisoformat(last["captured_at"])
    elapsed_days = (last_at - first_at).total_seconds() / 86400
    if elapsed_days <= 0:
        return None, first["captured_at"], last["captured_at"]
    return (
        (int(last["database_bytes"]) - int(first["database_bytes"])) / elapsed_days,
        first["captured_at"], last["captured_at"],
    )


def _finding(findings: list[dict], severity: str, scope: str, message: str) -> None:
    findings.append({"severity": severity, "scope": scope, "message": message})


def build_report(
    *, captured_at: datetime, drive_total_bytes: int, drive_free_bytes: int,
    database_bytes: int, trees: dict[str, TreeObservation], backups: BackupObservation,
    backup_retention_days: int, minimum_backups: int,
    raw_duplicates: DuplicateObservation | None = None,
    database_growth_bytes_per_day: float | None = None,
    database_growth_first_at: str | None = None, database_growth_last_at: str | None = None,
) -> dict:
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise DataQualityError("capacity snapshot timestamp requires a UTC offset")
    values = [drive_total_bytes, drive_free_bytes, database_bytes, backup_retention_days, minimum_backups]
    if any(value < 0 for value in values) or drive_free_bytes > drive_total_bytes:
        raise DataQualityError("capacity observations are invalid")
    required = {"raw", "derived", "backups", "logs"}
    if set(trees) != required:
        raise DataQualityError("capacity report requires raw, derived, backups, and logs observations")

    free_ratio = drive_free_bytes / drive_total_bytes if drive_total_bytes else 0.0
    projected_backup_count = max(minimum_backups, backup_retention_days + 1)
    projected_backup_bytes = backups.median_bytes * projected_backup_count
    projected_extra_backup_bytes = max(0, projected_backup_bytes - backups.total_bytes)
    projected_free_bytes = max(0, drive_free_bytes - projected_extra_backup_bytes)
    projected_free_ratio = projected_free_bytes / drive_total_bytes if drive_total_bytes else 0.0

    findings: list[dict] = []
    if drive_free_bytes <= FREE_CRITICAL_BYTES or free_ratio <= FREE_CRITICAL_RATIO:
        _finding(findings, "critical", "drive", "free disk crossed the critical floor")
    elif drive_free_bytes <= FREE_WARNING_BYTES or free_ratio <= FREE_WARNING_RATIO:
        _finding(findings, "warning", "drive", "free disk crossed the warning floor")
    if projected_free_bytes <= FREE_CRITICAL_BYTES or projected_free_ratio <= FREE_CRITICAL_RATIO:
        _finding(findings, "critical", "backup_projection", "backup steady state crosses the critical free-disk floor")
    elif projected_free_bytes <= FREE_WARNING_BYTES or projected_free_ratio <= FREE_WARNING_RATIO:
        _finding(findings, "warning", "backup_projection", "backup steady state crosses the warning free-disk floor")
    if database_bytes >= DATABASE_CRITICAL_BYTES:
        _finding(findings, "critical", "database", "database crossed the critical size ceiling")
    elif database_bytes >= DATABASE_WARNING_BYTES:
        _finding(findings, "warning", "database", "database crossed the warning size ceiling")
    if trees["raw"].bytes >= RAW_CRITICAL_BYTES:
        _finding(findings, "critical", "raw", "raw artifacts crossed the critical size ceiling")
    elif trees["raw"].bytes >= RAW_WARNING_BYTES:
        _finding(findings, "warning", "raw", "raw artifacts crossed the warning size ceiling")
    if backups.total_bytes >= BACKUP_CRITICAL_BYTES:
        _finding(findings, "critical", "backups", "backups crossed the critical size ceiling")
    elif backups.total_bytes >= BACKUP_WARNING_BYTES:
        _finding(findings, "warning", "backups", "backups crossed the warning size ceiling")
    backup_age_hours = None
    if backups.newest_at:
        backup_age_hours = (captured_at.astimezone(timezone.utc) - backups.newest_at).total_seconds() / 3600
        if backup_age_hours >= BACKUP_AGE_CRITICAL_HOURS:
            _finding(findings, "critical", "backup_freshness", "newest backup is at least 72 hours old")
        elif backup_age_hours >= BACKUP_AGE_WARNING_HOURS:
            _finding(findings, "warning", "backup_freshness", "newest backup is at least 36 hours old")
    else:
        _finding(findings, "critical", "backup_freshness", "no PostgreSQL backup exists")

    severities = {item["severity"] for item in findings}
    status = "critical" if "critical" in severities else "warning" if "warning" in severities else "healthy"
    retained_data_bytes = sum(item.bytes for item in trees.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "threshold_version": THRESHOLD_VERSION,
        "captured_at": captured_at.astimezone(timezone.utc).isoformat(),
        "status": status,
        "finding_count": len(findings),
        "findings": findings,
        "drive": {
            "total_bytes": drive_total_bytes, "free_bytes": drive_free_bytes,
            "free_ratio": free_ratio, "projected_free_bytes_after_backup_steady_state": projected_free_bytes,
            "projected_free_ratio_after_backup_steady_state": projected_free_ratio,
        },
        "database": {
            "bytes": database_bytes,
            "observed_growth_bytes_per_day": database_growth_bytes_per_day,
            "growth_observation_first_at": database_growth_first_at,
            "growth_observation_last_at": database_growth_last_at,
        },
        "retained_data_bytes": retained_data_bytes,
        "trees": {key: asdict(value) for key, value in sorted(trees.items())},
        "raw_content_duplicates": asdict(raw_duplicates) if raw_duplicates else None,
        "backups": {
            **asdict(backups),
            "newest_at": backups.newest_at.isoformat() if backups.newest_at else None,
            "oldest_at": backups.oldest_at.isoformat() if backups.oldest_at else None,
            "newest_age_hours": backup_age_hours,
            "retention_days": backup_retention_days,
            "minimum_backups": minimum_backups,
            "projected_steady_state_count": projected_backup_count,
            "projected_steady_state_bytes": projected_backup_bytes,
        },
        "thresholds": {
            "drive_free_warning_bytes": FREE_WARNING_BYTES,
            "drive_free_critical_bytes": FREE_CRITICAL_BYTES,
            "drive_free_warning_ratio": FREE_WARNING_RATIO,
            "drive_free_critical_ratio": FREE_CRITICAL_RATIO,
            "database_warning_bytes": DATABASE_WARNING_BYTES,
            "database_critical_bytes": DATABASE_CRITICAL_BYTES,
            "raw_warning_bytes": RAW_WARNING_BYTES,
            "raw_critical_bytes": RAW_CRITICAL_BYTES,
            "backup_warning_bytes": BACKUP_WARNING_BYTES,
            "backup_critical_bytes": BACKUP_CRITICAL_BYTES,
            "backup_age_warning_hours": BACKUP_AGE_WARNING_HOURS,
            "backup_age_critical_hours": BACKUP_AGE_CRITICAL_HOURS,
        },
        "notes": [
            "This command is read-only and does not delete, vacuum, back up, or mutate research data.",
            "The backup projection assumes one backup per day and conservatively includes both cutoff endpoints.",
            "Short-window growth is directional evidence, not a long-term forecast; rerun monthly.",
            "Build caches and dependency directories are intentionally outside the retained-data total.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--backup-retention-days", type=int, default=30)
    parser.add_argument("--minimum-backups", type=int, default=7)
    parser.add_argument("--fail-on-warning", action="store_true")
    args = parser.parse_args()
    if args.backup_retention_days < 1 or args.minimum_backups < 1:
        parser.error("backup retention and minimum backup count must be positive")
    workspace = args.workspace.resolve()
    settings = _settings(args.env_file.resolve())
    if not settings.database_url:
        parser.error("DATABASE_URL is required")

    reader = PostgresStorageReader(settings.database_url)
    try:
        _, database_bytes, _ = reader.measure()
    finally:
        reader.close()
    data_root = workspace / "data"
    trees = {
        "raw": measure_tree(data_root / "raw"),
        "derived": measure_tree(data_root / "derived"),
        "backups": measure_tree(data_root / "backups"),
        "logs": measure_tree(data_root / "logs"),
    }
    backups = measure_backups(data_root / "backups" / "postgresql")
    raw_duplicates = measure_content_addressed_duplicates(data_root / "raw")
    usage = shutil.disk_usage(data_root)
    growth, first_at, last_at = database_growth_per_day(data_root / "derived" / "database-storage")
    report = build_report(
        captured_at=datetime.now(timezone.utc), drive_total_bytes=usage.total,
        drive_free_bytes=usage.free, database_bytes=database_bytes, trees=trees,
        backups=backups, backup_retention_days=args.backup_retention_days,
        minimum_backups=args.minimum_backups, raw_duplicates=raw_duplicates,
        database_growth_bytes_per_day=growth,
        database_growth_first_at=first_at, database_growth_last_at=last_at,
    )
    print(json.dumps(report, sort_keys=True, indent=2))
    if args.fail_on_warning and report["status"] != "healthy":
        raise DataQualityError(f"local capacity status is {report['status']}")


if __name__ == "__main__":
    main()
