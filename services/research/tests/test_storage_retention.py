from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quantrade_research.quality import DataQualityError
from quantrade_research.storage_retention import plan_retention, quarantine


NOW = datetime(2026, 9, 3, tzinfo=timezone.utc)


def age(path: Path, days: int) -> None:
    timestamp = (NOW - timedelta(days=days)).timestamp()
    os.utime(path, (timestamp, timestamp))


class StorageRetentionTests(unittest.TestCase):
    def test_preserves_referenced_raw_and_manifests_but_finds_old_orphan(self):
        with TemporaryDirectory() as temporary:
            data = Path(temporary)
            raw = data / "raw"
            referenced = raw / "market-data" / "kept.json"
            orphan = raw / "market-data" / "orphan.json"
            manifest = raw / "manifests" / "old.json"
            for path in (referenced, orphan, manifest):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}")
                age(path, 100)
            result = plan_retention(data_root=data, referenced_artifacts={referenced}, now=NOW)
            self.assertEqual([Path(item.path).name for item in result], ["orphan.json"])
            self.assertEqual(result[0].category, "orphan_raw_artifact")

    def test_retains_minimum_completed_reports_and_finds_stale_incomplete(self):
        with TemporaryDirectory() as temporary:
            data = Path(temporary)
            root = data / "derived" / "sec-coverage"
            for number in range(14):
                report = root / f"{number:02d}"
                report.mkdir(parents=True)
                (report / "manifest.json").write_text(json.dumps({"status": "completed"}))
                age(report, 400)
            incomplete = root / "incomplete"
            incomplete.mkdir()
            age(incomplete, 8)
            result = plan_retention(data_root=data, referenced_artifacts=set(), now=NOW)
            self.assertEqual(sum(item.category == "aged_operational_report" for item in result), 2)
            self.assertEqual(sum(item.category == "incomplete_report" for item in result), 1)

    def test_recent_logs_and_orphans_are_preserved(self):
        with TemporaryDirectory() as temporary:
            data = Path(temporary)
            log = data / "logs" / "current.log"
            raw = data / "raw" / "market-data" / "current.json"
            for path in (log, raw):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("x")
            self.assertEqual(plan_retention(data_root=data, referenced_artifacts=set(), now=NOW), [])

    def test_apply_quarantines_and_writes_recovery_ledger(self):
        with TemporaryDirectory() as temporary:
            data = Path(temporary) / "data"
            source = data / "logs" / "old.log"
            source.parent.mkdir(parents=True)
            source.write_text("evidence")
            age(source, 31)
            candidates = plan_retention(data_root=data, referenced_artifacts=set(), now=NOW)
            destination = data / "quarantine" / "run"
            moved = quarantine(candidates=candidates, data_root=data.resolve(), destination=destination)
            self.assertFalse(source.exists())
            self.assertTrue((destination / "logs" / "old.log").is_file())
            self.assertEqual(moved[0]["bytes"], 8)
            self.assertTrue((destination / "ledger.json").is_file())

    def test_refuses_root_or_outside_targets(self):
        with TemporaryDirectory() as temporary:
            data = Path(temporary) / "data"
            data.mkdir()
            with self.assertRaisesRegex(DataQualityError, "escapes or equals"):
                quarantine(candidates=[], data_root=data, destination=data / "outside")


if __name__ == "__main__":
    unittest.main()
