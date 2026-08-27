BEGIN;

CREATE TABLE quantrade.model_deployments (
    model_deployment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_version TEXT NOT NULL UNIQUE REFERENCES quantrade.model_cards(model_version),
    approval_scope TEXT NOT NULL CHECK (approval_scope = 'private_beta'),
    approval_evidence_uri TEXT NOT NULL CHECK (length(approval_evidence_uri) > 0),
    deployed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deployed_by TEXT NOT NULL CHECK (length(deployed_by) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX model_deployments_latest_idx
    ON quantrade.model_deployments (deployed_at DESC);

CREATE FUNCTION quantrade.prevent_model_deployment_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'model deployment records are immutable';
END;
$$;

CREATE TRIGGER model_deployments_immutable
BEFORE UPDATE OR DELETE ON quantrade.model_deployments
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_model_deployment_mutation();

COMMIT;
