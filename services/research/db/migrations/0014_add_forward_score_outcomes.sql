-- Immutable, future-only labels for later model training and validation.

BEGIN;

CREATE TABLE quantrade.forward_score_outcomes (
    score_snapshot_id UUID NOT NULL REFERENCES quantrade.score_snapshots(score_snapshot_id),
    horizon_sessions SMALLINT NOT NULL CHECK (horizon_sessions IN (5, 20, 60)),
    status TEXT NOT NULL CHECK (status IN ('completed', 'withheld')),
    execution_date DATE NOT NULL,
    outcome_date DATE NOT NULL CHECK (outcome_date >= execution_date),
    adjustment_basis TEXT NOT NULL CHECK (adjustment_basis = 'split_adjusted'),
    security_entry_price NUMERIC(20, 8),
    security_exit_price NUMERIC(20, 8),
    benchmark_entry_price NUMERIC(20, 8),
    benchmark_exit_price NUMERIC(20, 8),
    security_return NUMERIC(20, 12),
    benchmark_return NUMERIC(20, 12),
    benchmark_relative_return NUMERIC(20, 12),
    data_cutoff_at TIMESTAMPTZ,
    unavailable_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (score_snapshot_id, horizon_sessions),
    CHECK (
        (status = 'completed'
         AND security_entry_price IS NOT NULL AND security_exit_price IS NOT NULL
         AND benchmark_entry_price IS NOT NULL AND benchmark_exit_price IS NOT NULL
         AND security_return IS NOT NULL AND benchmark_return IS NOT NULL
         AND benchmark_relative_return IS NOT NULL AND data_cutoff_at IS NOT NULL
         AND unavailable_reason IS NULL)
        OR
        (status = 'withheld'
         AND security_entry_price IS NULL AND security_exit_price IS NULL
         AND benchmark_entry_price IS NULL AND benchmark_exit_price IS NULL
         AND security_return IS NULL AND benchmark_return IS NULL
         AND benchmark_relative_return IS NULL AND data_cutoff_at IS NULL
         AND unavailable_reason IS NOT NULL)
    )
);

CREATE INDEX forward_score_outcomes_horizon_date_idx
    ON quantrade.forward_score_outcomes (horizon_sessions, outcome_date DESC);

CREATE TRIGGER forward_score_outcomes_immutable
BEFORE UPDATE OR DELETE ON quantrade.forward_score_outcomes
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_score_snapshot_mutation();

COMMIT;
