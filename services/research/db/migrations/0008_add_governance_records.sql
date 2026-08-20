-- Immutable model cards and rejected-hypothesis records.

BEGIN;

CREATE TABLE quantrade.model_cards (
    model_card_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_version TEXT NOT NULL UNIQUE CHECK (length(model_version) > 0),
    status TEXT NOT NULL CHECK (status IN ('research_only', 'private_beta_approved', 'rejected')),
    protocol_version TEXT NOT NULL CHECK (length(protocol_version) > 0),
    feature_registry_hash CHAR(64) NOT NULL CHECK (feature_registry_hash ~ '^[0-9a-f]{64}$'),
    data_capability_tier CHAR(1) NOT NULL CHECK (data_capability_tier IN ('A', 'B', 'C')),
    created_at TIMESTAMPTZ NOT NULL,
    purpose TEXT NOT NULL CHECK (length(purpose) > 0),
    methodology TEXT NOT NULL CHECK (length(methodology) > 0),
    limitations JSONB NOT NULL CHECK (jsonb_typeof(limitations) = 'array' AND jsonb_array_length(limitations) > 0),
    evaluation_uri TEXT
);

CREATE TABLE quantrade.rejected_hypotheses (
    rejected_hypothesis_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hypothesis_key TEXT NOT NULL UNIQUE CHECK (length(hypothesis_key) > 0),
    recorded_at TIMESTAMPTZ NOT NULL,
    statement TEXT NOT NULL CHECK (length(statement) > 0),
    rejection_reason TEXT NOT NULL CHECK (length(rejection_reason) > 0),
    evidence_uri TEXT
);

CREATE FUNCTION quantrade.prevent_governance_record_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'governance records are immutable';
END;
$$;

CREATE TRIGGER model_cards_immutable
BEFORE UPDATE OR DELETE ON quantrade.model_cards
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_governance_record_mutation();

CREATE TRIGGER rejected_hypotheses_immutable
BEFORE UPDATE OR DELETE ON quantrade.rejected_hypotheses
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_governance_record_mutation();

COMMIT;
