-- Version live and historical decision-time conventions separately, and retain
-- an immutable record when an official monthly formation window was missed.

BEGIN;

CREATE TABLE quantrade.decision_time_contracts (
    decision_contract_version TEXT PRIMARY KEY,
    context TEXT NOT NULL CHECK (context IN ('historical_replay', 'live_daily')),
    cutoff_rule TEXT NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO quantrade.decision_time_contracts
    (decision_contract_version, context, cutoff_rule, effective_at)
VALUES
    ('historical_replay_2000_toronto_v1', 'historical_replay',
     'Use only observations public by a fixed 20:00 America/Toronto historical decision time.',
     '2017-01-01 20:00:00 America/Toronto'),
    ('live_after_validation_v1', 'live_daily',
     'Capture decision_at after incremental ingestion and validation; a retry without immutable scores receives a new actual cutoff.',
     '2026-09-08 00:00:00 America/Toronto');

ALTER TABLE quantrade.daily_research_runs
    ADD COLUMN decision_contract_version TEXT
        REFERENCES quantrade.decision_time_contracts (decision_contract_version);

CREATE TABLE quantrade.missed_paper_portfolio_formations (
    formation_date DATE PRIMARY KEY,
    expected_execution_date DATE NOT NULL CHECK (expected_execution_date > formation_date),
    reason_code TEXT NOT NULL CHECK (reason_code IN (
        'month_end_score_unavailable',
        'execution_window_missed'
    )),
    decision_contract_version TEXT NOT NULL
        REFERENCES quantrade.decision_time_contracts (decision_contract_version),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION quantrade.prevent_decision_contract_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'decision-time contracts and missed formations are append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER decision_time_contracts_append_only
BEFORE UPDATE OR DELETE ON quantrade.decision_time_contracts
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_decision_contract_mutation();

CREATE TRIGGER missed_paper_portfolio_formations_append_only
BEFORE UPDATE OR DELETE ON quantrade.missed_paper_portfolio_formations
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_decision_contract_mutation();

COMMIT;
