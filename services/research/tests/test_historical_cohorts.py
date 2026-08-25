from datetime import date
from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.historical_cohorts import (
    CURRENT_SURVIVORS_COHORT,
    HistoricalCohortError,
    SourceUniverseSnapshot,
    register_current_survivors_cohort,
)


class FakeHistoricalCohortRepository:
    def __init__(self, snapshot: SourceUniverseSnapshot) -> None:
        self.snapshot = snapshot
        self.calls: list[tuple[str, object]] = []

    def latest_universe_snapshot(self, universe_code: str) -> SourceUniverseSnapshot:
        self.calls.append(("source", universe_code))
        return self.snapshot

    def register_current_survivors_cohort(self, *, cohort_code: str, source_snapshot: SourceUniverseSnapshot, provenance_note: str) -> None:
        self.calls.append(("register", (cohort_code, source_snapshot, provenance_note)))


class HistoricalCohortTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = SourceUniverseSnapshot(
            "snapshot-1", date(2026, 8, 21), 500, "file:///raw/universe/current-sp500.json",
        )

    def test_registers_a_fixed_tier_b_current_survivors_cohort(self) -> None:
        repository = FakeHistoricalCohortRepository(self.snapshot)

        report = register_current_survivors_cohort(repository)

        self.assertEqual(report.cohort_code, CURRENT_SURVIVORS_COHORT)
        self.assertEqual(report.constituent_count, 500)
        self.assertEqual(report.data_capability_tier, "B")
        self.assertTrue(report.survivorship_biased)
        self.assertFalse(report.sector_classification_point_in_time)
        self.assertEqual(repository.calls[0], ("source", "sp500"))
        self.assertEqual(repository.calls[1][0], "register")

    def test_rejects_non_sp500_sources(self) -> None:
        with self.assertRaisesRegex(HistoricalCohortError, "must be copied from sp500"):
            register_current_survivors_cohort(FakeHistoricalCohortRepository(self.snapshot), source_universe_code="nasdaq100")

    def test_rejects_a_source_snapshot_that_is_not_exactly_500_constituents(self) -> None:
        invalid = SourceUniverseSnapshot("snapshot-2", date(2026, 8, 21), 499, "file:///raw/universe/partial.json")
        with self.assertRaisesRegex(HistoricalCohortError, "exactly 500"):
            register_current_survivors_cohort(FakeHistoricalCohortRepository(invalid))


if __name__ == "__main__":
    unittest.main()
