-- Append-only operational history for the canonical daily research workflow.
-- The daily_research_runs row remains the current state; these events preserve
-- attempts, bounded provider retries, duplicate prevention, and terminal outcomes.

BEGIN;

CREATE TABLE quantrade.daily_research_run_events (
    daily_research_run_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    score_date DATE NOT NULL REFERENCES quantrade.daily_research_runs (score_date),
    event_type TEXT NOT NULL CHECK (event_type IN (
        'attempt_started',
        'provider_retry',
        'completed',
        'skipped',
        'failed',
        'duplicate_prevented',
        'post_publication_warning'
    )),
    stage TEXT CHECK (stage IN (
        'initialization',
        'market_data',
        'sec_filings',
        'validation',
        'scoring',
        'portfolio',
        'completion'
    )),
    attempt_number INTEGER CHECK (attempt_number > 0),
    detail TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX daily_research_run_events_recent_idx
    ON quantrade.daily_research_run_events (occurred_at DESC);

CREATE INDEX daily_research_run_events_score_date_idx
    ON quantrade.daily_research_run_events (score_date DESC, occurred_at DESC);

-- Give existing ledger rows an honest minimal history. These records predate
-- event capture, so they represent one known attempt and its last known state.
INSERT INTO quantrade.daily_research_run_events
    (score_date, event_type, stage, attempt_number, detail, occurred_at)
SELECT score_date, 'attempt_started', 'initialization', 1,
       'Legacy run imported when operations history was introduced.', started_at
FROM quantrade.daily_research_runs;

INSERT INTO quantrade.daily_research_run_events
    (score_date, event_type, stage, detail, occurred_at)
SELECT score_date, status, 'completion', failure_reason,
       COALESCE(completed_at, started_at)
FROM quantrade.daily_research_runs
WHERE status IN ('completed', 'skipped', 'failed');

CREATE OR REPLACE FUNCTION quantrade.prevent_daily_research_run_event_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'daily research run events are append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER daily_research_run_events_append_only
BEFORE UPDATE OR DELETE ON quantrade.daily_research_run_events
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_daily_research_run_event_mutation();

COMMIT;
