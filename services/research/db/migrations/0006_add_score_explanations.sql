-- Per-feature explanation rows for immutable score snapshots.

BEGIN;

CREATE TABLE quantrade.score_explanations (
    score_explanation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    score_snapshot_id UUID NOT NULL REFERENCES quantrade.score_snapshots(score_snapshot_id),
    feature_key TEXT NOT NULL CHECK (feature_key ~ '^[a-z][a-z0-9_]*$'),
    feature_version TEXT NOT NULL CHECK (length(feature_version) > 0),
    definition_hash CHAR(64) NOT NULL CHECK (definition_hash ~ '^[0-9a-f]{64}$'),
    sector_code TEXT NOT NULL CHECK (length(sector_code) > 0),
    percentile NUMERIC(20, 16),
    feature_weight NUMERIC(20, 16) NOT NULL CHECK (feature_weight > 0 AND feature_weight <= 1),
    contribution NUMERIC(20, 16),
    unavailable_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (percentile IS NOT NULL AND contribution IS NOT NULL AND unavailable_reason IS NULL)
        OR (percentile IS NULL AND contribution IS NULL AND unavailable_reason IS NOT NULL)
    ),
    UNIQUE (score_snapshot_id, feature_key, feature_version)
);

CREATE INDEX score_explanations_snapshot_idx
    ON quantrade.score_explanations (score_snapshot_id, feature_key);

CREATE FUNCTION quantrade.prevent_score_explanation_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'score explanations are immutable';
END;
$$;

CREATE TRIGGER score_explanations_immutable
BEFORE UPDATE OR DELETE ON quantrade.score_explanations
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_score_explanation_mutation();

COMMIT;
