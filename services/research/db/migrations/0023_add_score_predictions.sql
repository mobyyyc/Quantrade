BEGIN;

CREATE TABLE quantrade.score_predictions (
    score_snapshot_id UUID PRIMARY KEY REFERENCES quantrade.score_snapshots(score_snapshot_id),
    benchmark_ticker TEXT NOT NULL CHECK (benchmark_ticker = 'SPY'),
    horizon_sessions INTEGER NOT NULL CHECK (horizon_sessions = 20),
    predicted_benchmark_relative_return NUMERIC(18, 12) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE FUNCTION quantrade.prevent_score_prediction_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'score predictions are immutable';
END;
$$;

CREATE TRIGGER score_predictions_immutable
BEFORE UPDATE OR DELETE ON quantrade.score_predictions
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_score_prediction_mutation();

COMMIT;
