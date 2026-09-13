-- Immutable model-input metadata for API, scoring evidence, and UI disclosure.

BEGIN;

CREATE TABLE quantrade.model_input_contracts (
    model_version TEXT NOT NULL
        REFERENCES quantrade.model_artifacts(model_version),
    input_ordinal SMALLINT NOT NULL CHECK (input_ordinal >= 1),
    model_column TEXT NOT NULL CHECK (model_column ~ '^[a-z][a-z0-9_]*_percentile$'),
    feature_key TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    definition_hash CHAR(64) NOT NULL CHECK (definition_hash ~ '^[0-9a-f]{64}$'),
    display_name TEXT NOT NULL CHECK (length(display_name) > 0),
    coefficient DOUBLE PRECISION NOT NULL,
    is_active BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (model_version, input_ordinal),
    UNIQUE (model_version, model_column),
    FOREIGN KEY (feature_key, feature_version)
        REFERENCES quantrade.feature_definitions(feature_key, feature_version),
    CHECK (is_active = (coefficient <> 0.0))
);

CREATE FUNCTION quantrade.prevent_model_input_contract_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'model input contracts are immutable';
END;
$$;

CREATE TRIGGER model_input_contracts_immutable
BEFORE UPDATE OR DELETE ON quantrade.model_input_contracts
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_model_input_contract_mutation();

COMMIT;
