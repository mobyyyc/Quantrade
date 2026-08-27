BEGIN;

ALTER TABLE quantrade.paper_portfolio_runs
    ADD COLUMN model_version TEXT REFERENCES quantrade.model_cards(model_version),
    ADD COLUMN formation_protocol TEXT NOT NULL DEFAULT 'legacy_daily_v1'
        CHECK (formation_protocol IN ('legacy_daily_v1', 'monthly_last_session_next_open_v1'));

CREATE INDEX paper_portfolio_runs_official_monthly_idx
    ON quantrade.paper_portfolio_runs (score_date DESC, model_version)
    WHERE formation_protocol = 'monthly_last_session_next_open_v1';

COMMIT;
