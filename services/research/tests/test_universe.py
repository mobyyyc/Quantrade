from datetime import date, datetime, timezone
from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.security_master import RawArtifact
from quantrade_research.universe import (
    UniverseInputError,
    parse_universe_csv,
    persist_universe_snapshot,
)


class FakeUniverseRepository:
    def persist_raw_artifact(self, artifact, source_reference):
        self.artifact = artifact
        self.source_reference = source_reference
        return "raw-1"

    def create_universe_snapshot(self, *args):
        self.snapshot_arguments = args
        return "snapshot-1"

    def add_memberships(self, universe_snapshot_id, ciks):
        self.snapshot_id = universe_snapshot_id
        self.ciks = ciks
        return len(ciks)


class UniverseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.artifact = RawArtifact(
            storage_uri="file:///artifacts/universe.csv",
            content_sha256="b" * 64,
            retrieved_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        )

    def test_requires_cik_column_and_deduplicates_members(self) -> None:
        self.assertEqual(
            parse_universe_csv(b"CIK,ticker\n320193,AAPL\n0000320193,AAPL\n1652044,GOOGL\n"),
            ["0000320193", "0001652044"],
        )
        with self.assertRaises(UniverseInputError):
            parse_universe_csv(b"ticker\nAAPL\n")

    def test_current_snapshot_stays_tier_b(self) -> None:
        repository = FakeUniverseRepository()
        report = persist_universe_snapshot(
            repository, self.artifact, "fixture://current-sp500", "sp500",
            date(2026, 8, 20), ["0000320193"], False, "B",
        )
        self.assertEqual(report.constituent_count, 1)
        self.assertFalse(report.historical_membership_verified)
        self.assertEqual(repository.ciks, ["0000320193"])

    def test_unverified_snapshot_cannot_claim_tier_a(self) -> None:
        with self.assertRaises(UniverseInputError):
            persist_universe_snapshot(
                FakeUniverseRepository(), self.artifact, "fixture://current-sp500", "sp500",
                date(2026, 8, 20), ["0000320193"], False, "A",
            )


if __name__ == "__main__":
    unittest.main()
