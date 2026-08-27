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

    def test_benchmark_bars_are_separate_from_common_stock_securities(self) -> None:
        migration = MIGRATION.with_name("0011_add_benchmark_price_bars.sql")
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE quantrade.benchmark_daily_price_bars", sql)
        self.assertIn("PRIMARY KEY (benchmark_ticker, session_date, session, adjustment_basis)", sql)

    def test_paper_portfolio_outcomes_are_immutable_and_horizon_bound(self) -> None:
        migration = MIGRATION.with_name("0013_add_paper_portfolio_outcomes.sql")
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE quantrade.paper_portfolio_outcomes", sql)
        self.assertIn("horizon_sessions IN (5, 20, 60)", sql)
        self.assertIn("REFERENCES quantrade.paper_portfolio_runs", sql)
        self.assertIn("paper_portfolio_outcomes_immutable", sql)

    def test_forward_score_outcomes_are_immutable_training_labels(self) -> None:
        migration = MIGRATION.with_name("0014_add_forward_score_outcomes.sql")
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE quantrade.forward_score_outcomes", sql)
        self.assertIn("REFERENCES quantrade.score_snapshots", sql)
        self.assertIn("horizon_sessions IN (5, 20, 60)", sql)
        self.assertIn("adjustment_basis = 'split_adjusted'", sql)
        self.assertIn("forward_score_outcomes_immutable", sql)

    def test_daily_research_runs_select_one_canonical_publication(self) -> None:
        migration = MIGRATION.with_name("0015_add_daily_research_runs.sql")
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE quantrade.daily_research_runs", sql)
        self.assertIn("score_date DATE PRIMARY KEY", sql)
        self.assertIn("status IN ('running', 'completed', 'failed', 'skipped')", sql)
        self.assertIn("latest_decisions", sql)
        self.assertIn("ORDER BY score_date, decision_at DESC", sql)

    def test_historical_research_foundation_preserves_lineage_and_cohort_limits(self) -> None:
        migration = MIGRATION.with_name("0016_add_historical_research_foundation.sql")
        sql = migration.read_text(encoding="utf-8")
        for table in (
            "raw_documents",
            "raw_document_retrievals",
            "availability_rules",
            "research_cohorts",
            "research_cohort_memberships",
            "historical_backfill_runs",
            "training_dataset_provenance",
        ):
            self.assertIn(f"CREATE TABLE quantrade.{table}", sql)
        self.assertIn("UNIQUE (provider, content_sha256)", sql)
        self.assertIn("current_survivors", sql)
        self.assertIn("survivorship_biased", sql)
        self.assertIn("historical lineage records are immutable", sql)

    def test_historical_market_backfill_records_availability_rules_and_chunks(self) -> None:
        migration = MIGRATION.with_name("0017_add_historical_market_backfill.sql")
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("alpaca_historical_eod_close", sql)
        self.assertIn("availability_rule_id UUID", sql)
        self.assertIn("CREATE TABLE quantrade.historical_backfill_chunks", sql)
        self.assertIn("completed historical backfill chunks are immutable", sql)

    def test_historical_corporate_action_backfill_has_a_separate_tier_b_rule(self) -> None:
        migration = MIGRATION.with_name("0018_add_historical_corporate_action_rule.sql")
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("v1-corporate-action", sql)
        self.assertIn("corporate_action", sql)
        self.assertIn("point_in_time_verified", sql)
        self.assertIn("historical_backfill_runs_data_domain_check", sql)

    def test_model_artifacts_are_immutable_and_linked_to_cards(self) -> None:
        migration = MIGRATION.with_name("0019_add_model_artifact_registry.sql")
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE quantrade.model_artifacts", sql)
        self.assertIn("REFERENCES quantrade.model_cards", sql)
        self.assertIn("model_artifacts_immutable", sql)

    def test_raw_model_predictions_are_immutable_and_horizon_bound(self) -> None:
        migration = MIGRATION.with_name("0023_add_score_predictions.sql")
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE quantrade.score_predictions", sql)
        self.assertIn("REFERENCES quantrade.score_snapshots", sql)
        self.assertIn("horizon_sessions = 20", sql)
        self.assertIn("benchmark_ticker = 'SPY'", sql)
        self.assertIn("score_predictions_immutable", sql)

    def test_paper_portfolios_record_monthly_protocol_and_model(self) -> None:
        migration = MIGRATION.with_name("0024_align_monthly_paper_portfolios.sql")
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("model_version TEXT REFERENCES quantrade.model_cards", sql)
        self.assertIn("monthly_last_session_next_open_v1", sql)
        self.assertIn("paper_portfolio_runs_official_monthly_idx", sql)

    def test_forward_readiness_snapshots_are_compact_and_immutable(self) -> None:
        migration = MIGRATION.with_name("0020_add_forward_readiness_snapshots.sql")
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE quantrade.forward_outcome_readiness_snapshots", sql)
        self.assertIn("CREATE TABLE quantrade.forward_outcome_readiness_metrics", sql)
        self.assertIn("forward_outcome_readiness_metrics_immutable", sql)

    def test_total_return_bars_are_limited_to_holdout_accounting(self) -> None:
        migration = MIGRATION.with_name("0021_add_total_return_holdout_evaluation.sql")
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("total_return_adjusted", sql)
        self.assertIn("not eligible for model features", sql)

    def test_holdout_and_experiment_governance_are_immutable(self) -> None:
        migration = MIGRATION.with_name("0007_add_experiment_governance.sql")
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE quantrade.holdout_periods", sql)
        self.assertIn("CREATE TABLE quantrade.experiment_records", sql)
        self.assertIn("REFERENCES quantrade.holdout_periods", sql)
        self.assertIn("prevent_experiment_governance_mutation", sql)

    def test_model_cards_and_rejected_hypotheses_are_immutable(self) -> None:
        migration = MIGRATION.with_name("0008_add_governance_records.sql")
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE quantrade.model_cards", sql)
        self.assertIn("CREATE TABLE quantrade.rejected_hypotheses", sql)
        self.assertIn("prevent_governance_record_mutation", sql)


if __name__ == "__main__":
    unittest.main()
