from pathlib import Path
import unittest


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "db"
    / "migrations"
    / "0001_core_schema.sql"
)


class CoreSchemaMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sql = MIGRATION.read_text(encoding="utf-8")

    def test_core_tables_are_present(self) -> None:
        for table in (
            "raw_artifacts",
            "securities",
            "security_identifiers",
            "listings",
            "daily_price_bars",
            "filings",
            "filing_facts",
            "score_snapshots",
        ):
            self.assertIn(f"CREATE TABLE quantrade.{table}", self.sql)

    def test_point_in_time_fields_are_required(self) -> None:
        self.assertGreaterEqual(self.sql.count("available_at TIMESTAMPTZ NOT NULL"), 3)
        self.assertGreaterEqual(self.sql.count("ingested_at TIMESTAMPTZ NOT NULL"), 5)
        self.assertIn("CHECK (data_cutoff_at <= decision_at)", self.sql)

    def test_scores_are_immutable(self) -> None:
        self.assertIn("prevent_score_snapshot_mutation", self.sql)
        self.assertIn("BEFORE UPDATE OR DELETE ON quantrade.score_snapshots", self.sql)


if __name__ == "__main__":
    unittest.main()
