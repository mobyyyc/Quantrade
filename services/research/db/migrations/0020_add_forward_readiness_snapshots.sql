-- Immutable, compact read model for the Research page's forward-label readiness.

BEGIN;

CREATE TABLE quantrade.forward_outcome_readiness_snapshots (
    forward_outcome_readiness_snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    as_of_date DATE NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE quantrade.forward_outcome_readiness_metrics (
    forward_outcome_readiness_snapshot_id UUID NOT NULL REFERENCES quantrade.forward_outcome_readiness_snapshots(forward_outcome_readiness_snapshot_id),
    horizon_sessions SMALLINT NOT NULL CHECK (horizon_sessions IN (5, 20, 60)),
    completed_labels INTEGER NOT NULL CHECK (completed_labels >= 0),
    withheld_labels INTEGER NOT NULL CHECK (withheld_labels >= 0),
    pending_labels INTEGER NOT NULL CHECK (pending_labels >= 0),
    completed_score_dates INTEGER NOT NULL CHECK (completed_score_dates >= 0),
    latest_outcome_date DATE,
    PRIMARY KEY (forward_outcome_readiness_snapshot_id, horizon_sessions)
);

CREATE FUNCTION quantrade.prevent_forward_readiness_snapshot_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'forward-readiness snapshots are immutable';
END;
$$;

CREATE TRIGGER forward_outcome_readiness_snapshots_immutable
BEFORE UPDATE OR DELETE ON quantrade.forward_outcome_readiness_snapshots
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_forward_readiness_snapshot_mutation();

CREATE TRIGGER forward_outcome_readiness_metrics_immutable
BEFORE UPDATE OR DELETE ON quantrade.forward_outcome_readiness_metrics
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_forward_readiness_snapshot_mutation();

COMMIT;
