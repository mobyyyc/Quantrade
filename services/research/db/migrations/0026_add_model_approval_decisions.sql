-- Append-only model approval decisions and deployment-time governance enforcement.

BEGIN;

CREATE TABLE quantrade.model_approval_decisions (
    model_approval_decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_version TEXT NOT NULL REFERENCES quantrade.model_cards(model_version),
    approval_scope TEXT NOT NULL CHECK (approval_scope IN ('private_beta', 'public_performance_claim')),
    approved BOOLEAN NOT NULL,
    evidence JSONB NOT NULL CHECK (jsonb_typeof(evidence) = 'object'),
    gate_results JSONB NOT NULL CHECK (jsonb_typeof(gate_results) = 'array'),
    decision_uri TEXT NOT NULL CHECK (length(decision_uri) > 0),
    decision_sha256 CHAR(64) NOT NULL CHECK (decision_sha256 ~ '^[0-9a-f]{64}$'),
    decided_at TIMESTAMPTZ NOT NULL,
    decided_by TEXT NOT NULL CHECK (length(decided_by) > 0),
    UNIQUE (model_version, approval_scope)
);

CREATE TRIGGER model_approval_decisions_immutable
BEFORE UPDATE OR DELETE ON quantrade.model_approval_decisions
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_governance_record_mutation();

ALTER TABLE quantrade.model_deployments
    DROP CONSTRAINT model_deployments_model_version_key;

CREATE FUNCTION quantrade.enforce_approved_model_deployment()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM quantrade.model_approval_decisions decision
        WHERE decision.model_version = NEW.model_version
          AND decision.approval_scope = NEW.approval_scope
          AND decision.approved
          AND decision.decision_uri = NEW.approval_evidence_uri
    ) THEN
        RAISE EXCEPTION 'model deployment requires a matching approved governance decision';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER model_deployments_require_approval
BEFORE INSERT ON quantrade.model_deployments
FOR EACH ROW EXECUTE FUNCTION quantrade.enforce_approved_model_deployment();

COMMIT;
