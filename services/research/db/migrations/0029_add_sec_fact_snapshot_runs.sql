-- Durable progress ledger for the resumable legacy SEC fact snapshot.

BEGIN;

CREATE TABLE quantrade.sec_fact_snapshot_runs (
    run_key TEXT PRIMARY KEY CHECK (run_key ~ '^[a-z][a-z0-9_]*$'),
    availability_rule_id UUID NOT NULL REFERENCES quantrade.availability_rules(availability_rule_id),
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    last_filing_fact_id UUID,
    source_row_count BIGINT NOT NULL CHECK (source_row_count >= 0),
    processed_row_count BIGINT NOT NULL DEFAULT 0 CHECK (processed_row_count >= 0),
    persisted_observation_count BIGINT NOT NULL DEFAULT 0 CHECK (persisted_observation_count >= 0),
    duplicate_observation_count BIGINT NOT NULL DEFAULT 0 CHECK (duplicate_observation_count >= 0),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    failure_reason TEXT,
    CHECK (processed_row_count <= source_row_count),
    CHECK (
        (status = 'running' AND completed_at IS NULL)
        OR (status IN ('completed', 'failed') AND completed_at IS NOT NULL)
    )
);

CREATE FUNCTION quantrade.prevent_terminal_sec_fact_snapshot_run_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' OR OLD.status IN ('completed', 'failed') THEN
        RAISE EXCEPTION 'terminal SEC fact snapshot runs are immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER sec_fact_snapshot_runs_terminal_immutable
BEFORE UPDATE OR DELETE ON quantrade.sec_fact_snapshot_runs
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_terminal_sec_fact_snapshot_run_mutation();

COMMIT;
