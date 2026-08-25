-- Historical end-of-day market availability and resumable download chunks.

BEGIN;

INSERT INTO quantrade.availability_rules
    (rule_key, rule_version, provider, data_domain, description, data_capability_tier, point_in_time_verified, rule_hash)
VALUES
    ('alpaca_historical_eod_close', 'v1', 'alpaca', 'market_bar',
     'Historical regular-session bars are modeled as available at 6:00 p.m. America/Toronto on their session date.', 'B', false,
     '8433185ab79c89903688581e0b967dcbb3fc2ba263367303072f3242964ee25f'),
    ('alpaca_historical_eod_close', 'v1-benchmark', 'alpaca', 'benchmark_bar',
     'Historical regular-session benchmark bars are modeled as available at 6:00 p.m. America/Toronto on their session date.', 'B', false,
     '5cefd3031063b210001ef34f9f0ec1a34c7e1d38dc8be71a0bfa4284e5404974');

ALTER TABLE quantrade.daily_price_bars
    ADD COLUMN availability_rule_id UUID REFERENCES quantrade.availability_rules(availability_rule_id);
ALTER TABLE quantrade.benchmark_daily_price_bars
    ADD COLUMN availability_rule_id UUID REFERENCES quantrade.availability_rules(availability_rule_id);

UPDATE quantrade.daily_price_bars
SET availability_rule_id = (
    SELECT availability_rule_id FROM quantrade.availability_rules
    WHERE rule_key = 'alpaca_retrieval' AND rule_version = 'v1' AND data_domain = 'market_bar'
);
UPDATE quantrade.benchmark_daily_price_bars
SET availability_rule_id = (
    SELECT availability_rule_id FROM quantrade.availability_rules
    WHERE rule_key = 'alpaca_retrieval' AND rule_version = 'v1-benchmark' AND data_domain = 'benchmark_bar'
);

ALTER TABLE quantrade.daily_price_bars
    ALTER COLUMN availability_rule_id SET NOT NULL;
ALTER TABLE quantrade.benchmark_daily_price_bars
    ALTER COLUMN availability_rule_id SET NOT NULL;

CREATE TABLE quantrade.historical_backfill_chunks (
    historical_backfill_chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    historical_backfill_run_id UUID NOT NULL REFERENCES quantrade.historical_backfill_runs(historical_backfill_run_id),
    chunk_key TEXT NOT NULL CHECK (length(chunk_key) > 0),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    adjustment_basis TEXT NOT NULL CHECK (adjustment_basis IN ('unadjusted', 'split_adjusted')),
    symbols JSONB NOT NULL CHECK (jsonb_typeof(symbols) = 'array' AND jsonb_array_length(symbols) > 0),
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    raw_document_count INTEGER NOT NULL DEFAULT 0 CHECK (raw_document_count >= 0),
    persisted_count INTEGER NOT NULL DEFAULT 0 CHECK (persisted_count >= 0),
    failure_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (start_date <= end_date),
    UNIQUE (historical_backfill_run_id, chunk_key),
    CHECK (
        (status = 'completed' AND completed_at IS NOT NULL AND failure_reason IS NULL)
        OR (status IN ('failed', 'skipped') AND completed_at IS NOT NULL AND failure_reason IS NOT NULL)
        OR status IN ('pending', 'running')
    )
);

CREATE INDEX historical_backfill_chunks_run_status_idx
    ON quantrade.historical_backfill_chunks (historical_backfill_run_id, status, start_date, end_date);
CREATE INDEX daily_price_bars_availability_rule_idx
    ON quantrade.daily_price_bars (availability_rule_id, session_date DESC);
CREATE INDEX benchmark_daily_price_bars_availability_rule_idx
    ON quantrade.benchmark_daily_price_bars (availability_rule_id, session_date DESC);

CREATE FUNCTION quantrade.prevent_completed_historical_chunk_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' OR OLD.status IN ('completed', 'failed', 'skipped') THEN
        RAISE EXCEPTION 'completed historical backfill chunks are immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER historical_backfill_chunks_terminal_immutable
BEFORE UPDATE OR DELETE ON quantrade.historical_backfill_chunks
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_completed_historical_chunk_mutation();

COMMIT;
