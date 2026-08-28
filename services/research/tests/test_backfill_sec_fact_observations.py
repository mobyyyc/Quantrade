from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.backfill_sec_fact_observations import SnapshotProgress, progress_line


class SecFactSnapshotTests(unittest.TestCase):
    def test_progress_line_reports_committed_work_without_excessive_detail(self) -> None:
        progress = SnapshotProgress(1_000, 250, 230, 20, "00000000-0000-0000-0000-000000000001", False)
        self.assertEqual(
            progress_line(progress, batch=3),
            "progress batch=3; processed=250/1000 (25.0%); persisted=230; duplicates=20",
        )

    def test_zero_source_progress_is_complete_percentage(self) -> None:
        self.assertEqual(SnapshotProgress(0, 0, 0, 0, None, True).percent, 100.0)


if __name__ == "__main__":
    unittest.main()
