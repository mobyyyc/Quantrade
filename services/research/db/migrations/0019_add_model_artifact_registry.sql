-- Immutable local registry for research-only model inference artifacts.

BEGIN;

CREATE TABLE quantrade.model_artifacts (
    model_artifact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_card_id UUID NOT NULL UNIQUE REFERENCES quantrade.model_cards(model_card_id),
    model_version TEXT NOT NULL UNIQUE CHECK (length(model_version) > 0),
    artifact_uri TEXT NOT NULL CHECK (length(artifact_uri) > 0),
    artifact_sha256 CHAR(64) NOT NULL CHECK (artifact_sha256 ~ '^[0-9a-f]{64}$'),
    source_experiment_uri TEXT NOT NULL CHECK (length(source_experiment_uri) > 0),
    source_experiment_sha256 CHAR(64) NOT NULL CHECK (source_experiment_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE FUNCTION quantrade.prevent_model_artifact_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'model artifacts are immutable';
END;
$$;

CREATE TRIGGER model_artifacts_immutable
BEFORE UPDATE OR DELETE ON quantrade.model_artifacts
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_model_artifact_mutation();

COMMIT;
