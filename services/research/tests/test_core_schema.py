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

    def test_security_master_can_remain_unclassified(self) -> None:
        migration = MIGRATION.with_name("0002_allow_unclassified_security_master.sql")
        self.assertIn("asset_class IN ('common_stock', 'unknown')", migration.read_text(encoding="utf-8"))

    def test_universe_snapshots_require_an_explicit_as_of_date(self) -> None:
        migration = MIGRATION.with_name("0003_add_universe_snapshots.sql")
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE quantrade.universe_snapshots", sql)
        self.assertIn("as_of_date DATE NOT NULL", sql)
        self.assertIn("historical_membership_verified BOOLEAN NOT NULL", sql)

    def test_corporate_actions_are_source_attributed(self) -> None:
        migration = MIGRATION.with_name("0004_add_corporate_actions.sql")
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE quantrade.corporate_actions", sql)
        self.assertIn("raw_artifact_id UUID NOT NULL", sql)
        self.assertIn("available_at TIMESTAMPTZ NOT NULL", sql)

    def test_feature_definitions_are_versioned_and_immutable(self) -> None:
        migration = MIGRATION.with_name("0005_add_feature_definitions.sql")
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE quantrade.feature_definitions", sql)
        self.assertIn("UNIQUE (feature_key, feature_version)", sql)
        self.assertIn("definition_hash CHAR(64) NOT NULL", sql)
        self.assertIn("prevent_feature_definition_mutation", sql)
        self.assertIn("BEFORE UPDATE OR DELETE ON quantrade.feature_definitions", sql)

    def test_score_explanations_are_immutable_and_linked_to_scores(self) -> None:
        migration = MIGRATION.with_name("0006_add_score_explanations.sql")
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE quantrade.score_explanations", sql)
        self.assertIn("REFERENCES quantrade.score_snapshots(score_snapshot_id)", sql)
        self.assertIn("UNIQUE (score_snapshot_id, feature_key, feature_version)", sql)
        self.assertIn("prevent_score_explanation_mutation", sql)

    def test_holdout_and_experiment_governance_are_immutable(self) -> None:
        migration = MIGRATION.with_name("0007_add_experiment_governance.sql")
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE quantrade.holdout_periods", sql)
        self.assertIn("CREATE TABLE quantrade.experiment_records", sql)
        self.assertIn("REFERENCES quantrade.holdout_periods", sql)
        self.assertIn("prevent_experiment_governance_mutation", sql)


if __name__ == "__main__":
    unittest.main()
