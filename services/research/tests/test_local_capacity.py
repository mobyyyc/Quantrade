from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quantrade_research.local_capacity import (
    BackupObservation, GIB, TreeObservation, build_report, measure_backups,
    measure_content_addressed_duplicates, measure_tree,
)


NOW = datetime(2026, 9, 16, tzinfo=timezone.utc)


def trees(raw=8 * GIB, backups=20 * GIB):
    return {
        "raw": TreeObservation("raw", raw, 10),
        "derived": TreeObservation("derived", GIB, 5),
        "backups": TreeObservation("backups", backups, 20),
        "logs": TreeObservation("logs", 1024, 2),
    }


def backup(total=20 * GIB, newest=NOW - timedelta(hours=12)):
    return BackupObservation(16, total, int(1.25 * GIB), newest, NOW - timedelta(days=15), 300_000)


def report(**overrides):
    values = {
        "captured_at": NOW, "drive_total_bytes": 600 * GIB, "drive_free_bytes": 240 * GIB,
        "database_bytes": 12 * GIB, "trees": trees(), "backups": backup(),
        "backup_retention_days": 30, "minimum_backups": 7,
    }
    values.update(overrides)
    return build_report(**values)


class LocalCapacityTests(unittest.TestCase):
    def test_healthy_report_projects_backup_steady_state(self):
        result = report()
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["backups"]["projected_steady_state_count"], 31)
        self.assertGreater(result["drive"]["projected_free_bytes_after_backup_steady_state"], 200 * GIB)

    def test_drive_thresholds_consider_bytes_and_ratio(self):
        warning = report(drive_free_bytes=90 * GIB)
        self.assertEqual(warning["status"], "warning")
        critical = report(drive_free_bytes=45 * GIB)
        self.assertEqual(critical["status"], "critical")

    def test_database_raw_backup_and_freshness_thresholds(self):
        self.assertEqual(report(database_bytes=25 * GIB)["status"], "warning")
        self.assertEqual(report(trees=trees(raw=20 * GIB))["status"], "critical")
        stale = backup(newest=NOW - timedelta(hours=80))
        self.assertEqual(report(backups=stale)["status"], "critical")

    def test_rejects_incomplete_or_invalid_observations(self):
        with self.assertRaisesRegex(ValueError, "requires"):
            report(trees={"raw": TreeObservation("raw", 1, 1)})
        with self.assertRaisesRegex(ValueError, "invalid"):
            report(drive_free_bytes=700 * GIB)

    def test_tree_and_backup_measurements_do_not_follow_symlinks(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "raw").mkdir()
            (root / "raw" / "one.bin").write_bytes(b"1234")
            observation = measure_tree(root / "raw")
            self.assertEqual((observation.bytes, observation.files), (4, 1))
            backup_root = root / "backups"
            backup_root.mkdir()
            first = backup_root / "one.dump"
            second = backup_root / "two.dump"
            first.write_bytes(b"1" * 10)
            second.write_bytes(b"2" * 20)
            measured = measure_backups(backup_root)
            self.assertEqual((measured.count, measured.total_bytes, measured.median_bytes), (2, 30, 15))

    def test_content_addressed_duplicate_measurement_counts_only_hash_names(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "a"
            second = root / "b"
            first.mkdir()
            second.mkdir()
            digest = "a" * 64
            (first / f"{digest}.json").write_bytes(b"same")
            (second / f"{digest}.json").write_bytes(b"same")
            (second / "ordinary.json").write_bytes(b"same")
            measured = measure_content_addressed_duplicates(root)
            self.assertEqual((measured.hash_groups, measured.extra_files, measured.duplicate_bytes), (1, 1, 4))


if __name__ == "__main__":
    unittest.main()
