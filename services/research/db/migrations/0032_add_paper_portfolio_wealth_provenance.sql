-- Audit fields for explicit corporate-action-aware paper-portfolio wealth accounting.

BEGIN;

ALTER TABLE quantrade.paper_portfolio_outcomes
    ADD COLUMN accounting_rule TEXT,
    ADD COLUMN portfolio_ledger_sha256 CHAR(64),
    ADD COLUMN benchmark_ledger_sha256 CHAR(64),
    ADD COLUMN corporate_action_count INTEGER CHECK (corporate_action_count >= 0),
    ADD COLUMN data_cutoff_at TIMESTAMPTZ;

ALTER TABLE quantrade.paper_portfolio_outcomes
    ADD CONSTRAINT paper_portfolio_outcome_wealth_provenance_complete CHECK (
        (accounting_rule IS NULL
         AND portfolio_ledger_sha256 IS NULL
         AND benchmark_ledger_sha256 IS NULL
         AND corporate_action_count IS NULL
         AND data_cutoff_at IS NULL)
        OR
        (accounting_rule IS NOT NULL
         AND portfolio_ledger_sha256 ~ '^[0-9a-f]{64}$'
         AND benchmark_ledger_sha256 ~ '^[0-9a-f]{64}$'
         AND corporate_action_count IS NOT NULL
         AND data_cutoff_at IS NOT NULL)
    );

COMMIT;
