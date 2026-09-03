"""Read-only PostgreSQL size snapshots with verified growth comparisons."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from .quality import DataQualityError
from .score_run import _settings


SCHEMA_VERSION = "database_storage_monitor_v1"
THRESHOLD_VERSION = "quantrade_storage_growth_v1"
DATABASE_WARNING = (512 * 1024**2, 0.05)
DATABASE_CRITICAL = (2 * 1024**3, 0.15)
TABLE_WARNING = (128 * 1024**2, 0.10)
TABLE_CRITICAL = (512 * 1024**2, 0.30)


@dataclass(frozen=True)
class RelationSize:
    schema: str
    table: str
    total_bytes: int
    heap_bytes: int
    index_bytes: int
    toast_bytes: int
    estimated_rows: int

    @property
    def key(self) -> str:
        return f"{self.schema}.{self.table}"


def _growth(current: int, previous: int) -> tuple[int, float | None]:
    delta = current - previous
    return delta, (delta / previous if previous else None)


def _exceeds(delta: int, ratio: float | None, threshold: tuple[int, float]) -> bool:
    return delta >= threshold[0] and ratio is not None and ratio >= threshold[1]


def build_report(*, database: str, database_bytes: int, relations: list[RelationSize],
                 captured_at: datetime, code_revision: str, baseline: dict | None = None) -> dict:
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise DataQualityError("storage snapshot timestamp requires a UTC offset")
    if database_bytes < 0 or any(min(item.total_bytes, item.heap_bytes, item.index_bytes,
                                     item.toast_bytes, item.estimated_rows) < 0 for item in relations):
        raise DataQualityError("database size observations cannot be negative")
    if len({item.key for item in relations}) != len(relations):
        raise DataQualityError("duplicate relation in database size observation")
    previous_database = baseline["database_bytes"] if baseline else None
    previous_relations = {item["relation"]: item for item in baseline["relations"]} if baseline else {}
    database_delta, database_ratio = _growth(database_bytes, previous_database) if baseline else (None, None)
    findings = []
    if baseline:
        level = "critical" if _exceeds(database_delta, database_ratio, DATABASE_CRITICAL) else (
            "warning" if _exceeds(database_delta, database_ratio, DATABASE_WARNING) else None)
        if level:
            findings.append({"severity": level, "scope": "database", "name": database,
                             "delta_bytes": database_delta, "growth_ratio": database_ratio})
    rows = []
    for item in sorted(relations, key=lambda value: (-value.total_bytes, value.key)):
        previous = previous_relations.get(item.key)
        delta, ratio = _growth(item.total_bytes, previous["total_bytes"]) if previous else (None, None)
        level = None
        if previous:
            level = "critical" if _exceeds(delta, ratio, TABLE_CRITICAL) else (
                "warning" if _exceeds(delta, ratio, TABLE_WARNING) else None)
        if level:
            findings.append({"severity": level, "scope": "relation", "name": item.key,
                             "delta_bytes": delta, "growth_ratio": ratio})
        values = {key: value for key, value in asdict(item).items() if key not in {"schema", "table"}}
        rows.append({"relation": item.key, **values,
                     "baseline_total_bytes": previous["total_bytes"] if previous else None,
                     "delta_bytes": delta, "growth_ratio": ratio,
                     "comparison_status": level or ("new" if baseline and not previous else
                                                     "baseline" if not baseline else "normal")})
    observed = {item.key for item in relations}
    for name, previous in sorted(previous_relations.items()):
        if name not in observed:
            findings.append({"severity": "information", "scope": "relation", "name": name,
                             "delta_bytes": -previous["total_bytes"], "growth_ratio": -1.0,
                             "reason": "relation absent from current snapshot"})
    severities = {item["severity"] for item in findings}
    status = "critical" if "critical" in severities else "warning" if "warning" in severities else (
        "baseline" if not baseline else "normal")
    return {
        "schema_version": SCHEMA_VERSION, "threshold_version": THRESHOLD_VERSION,
        "captured_at": captured_at.astimezone(timezone.utc).isoformat(), "code_revision": code_revision,
        "database": database, "database_bytes": database_bytes,
        "baseline_captured_at": baseline["captured_at"] if baseline else None,
        "database_delta_bytes": database_delta, "database_growth_ratio": database_ratio,
        "status": status, "finding_count": len(findings), "findings": findings, "relations": rows,
        "thresholds": {
            "database_warning": {"minimum_delta_bytes": DATABASE_WARNING[0], "minimum_growth_ratio": DATABASE_WARNING[1]},
            "database_critical": {"minimum_delta_bytes": DATABASE_CRITICAL[0], "minimum_growth_ratio": DATABASE_CRITICAL[1]},
            "relation_warning": {"minimum_delta_bytes": TABLE_WARNING[0], "minimum_growth_ratio": TABLE_WARNING[1]},
            "relation_critical": {"minimum_delta_bytes": TABLE_CRITICAL[0], "minimum_growth_ratio": TABLE_CRITICAL[1]},
        },
        "notes": [
            "Measurements use PostgreSQL allocated bytes; estimated_rows is statistical, not an exact COUNT(*).",
            "A warning requires both its absolute-byte and relative-growth thresholds.",
            "A first snapshot is a baseline. New and removed relations are informational, not growth warnings.",
            "Reports are monitoring evidence only; they never delete, vacuum, or modify database data.",
        ],
    }


def load_verified_report(directory: Path) -> dict:
    manifest_path, report_path = directory / "manifest.json", directory / "storage.json"
    summary_path = directory / "summary.txt"
    if not manifest_path.is_file() or not report_path.is_file() or not summary_path.is_file():
        raise DataQualityError(f"incomplete storage report: {directory}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = report_path.read_bytes()
    expected = manifest.get("sha256", {})
    if (manifest.get("status") != "completed"
            or expected.get("storage.json") != sha256(payload).hexdigest()
            or expected.get("summary.txt") != sha256(summary_path.read_bytes()).hexdigest()):
        raise DataQualityError(f"storage report checksum failed: {directory}")
    report = json.loads(payload)
    if report.get("schema_version") != SCHEMA_VERSION:
        raise DataQualityError(f"unsupported storage report: {directory}")
    return report


def latest_verified_report(root: Path) -> tuple[Path | None, dict | None]:
    if not root.exists():
        return None, None
    for candidate in sorted((item for item in root.iterdir() if item.is_dir()), reverse=True):
        try:
            return candidate, load_verified_report(candidate)
        except (DataQualityError, OSError, json.JSONDecodeError):
            continue
    return None, None


class PostgresStorageReader:
    def __init__(self, database_url: str) -> None:
        import psycopg
        from psycopg import IsolationLevel
        self.connection = psycopg.connect(database_url)
        self.connection.read_only = True
        self.connection.isolation_level = IsolationLevel.REPEATABLE_READ

    def close(self) -> None:
        self.connection.close()

    def measure(self) -> tuple[str, int, list[RelationSize]]:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), pg_database_size(current_database())")
            database, database_bytes = cursor.fetchone()
            cursor.execute(
                """SELECT schemaname, relname, pg_total_relation_size(relid), pg_relation_size(relid),
                          pg_indexes_size(relid), GREATEST(pg_total_relation_size(relid)-pg_relation_size(relid)-pg_indexes_size(relid),0),
                          GREATEST(COALESCE(n_live_tup,0),0)::bigint
                   FROM pg_stat_user_tables WHERE schemaname='quantrade'
                   ORDER BY schemaname, relname"""
            )
            rows = [RelationSize(str(row[0]), str(row[1]), *(int(value) for value in row[2:]))
                    for row in cursor.fetchall()]
        return str(database), int(database_bytes), rows


def publish(report: dict, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    payload = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    with (directory / "storage.json").open("xb") as handle:
        handle.write(payload)
    summary = (f"Database: {report['database']}\nStatus: {report['status']}\n"
               f"Allocated: {report['database_bytes']:,} bytes\n"
               f"Change: {report['database_delta_bytes'] if report['database_delta_bytes'] is not None else 'baseline'}\n"
               f"Findings: {report['finding_count']}\n")
    summary_payload = summary.encode("utf-8")
    with (directory / "summary.txt").open("xb") as handle:
        handle.write(summary_payload)
    manifest = {"schema_version": SCHEMA_VERSION, "status": "completed",
                "sha256": {"storage.json": sha256(payload).hexdigest(),
                           "summary.txt": sha256(summary_payload).hexdigest()},
                "code_revision": report["code_revision"]}
    with (directory / "manifest.json").open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, sort_keys=True, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--report-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--fail-on-warning", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; storage reports must not be overwritten")
    _, baseline = latest_verified_report(args.report_root)
    settings = _settings(args.env_file)
    if not settings.database_url:
        parser.error("DATABASE_URL is required")
    reader = PostgresStorageReader(settings.database_url)
    try:
        database, size, relations = reader.measure()
    finally:
        reader.close()
    report = build_report(database=database, database_bytes=size, relations=relations,
                          captured_at=datetime.now(timezone.utc), code_revision=args.code_revision, baseline=baseline)
    publish(report, args.output)
    print(json.dumps({"output": str(args.output), "status": report["status"],
                      "database_bytes": size, "findings": report["finding_count"]}, sort_keys=True))
    if args.fail_on_warning and report["status"] in {"warning", "critical"}:
        raise DataQualityError("database storage growth crossed a configured threshold")


if __name__ == "__main__":
    main()
