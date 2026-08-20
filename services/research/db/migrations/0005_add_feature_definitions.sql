-- Immutable, versioned definitions for research features.

BEGIN;

CREATE TABLE quantrade.feature_definitions (
    feature_definition_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feature_key TEXT NOT NULL CHECK (feature_key ~ '^[a-z][a-z0-9_]*$'),
    feature_version TEXT NOT NULL CHECK (length(feature_version) > 0),
    family TEXT NOT NULL CHECK (family IN ('momentum', 'value', 'profitability', 'risk', 'liquidity')),
    direction TEXT NOT NULL CHECK (direction IN ('higher_is_better', 'lower_is_better')),
    display_name TEXT NOT NULL CHECK (length(display_name) > 0),
    description TEXT NOT NULL CHECK (length(description) > 0),
    formula TEXT NOT NULL CHECK (length(formula) > 0),
    required_inputs JSONB NOT NULL CHECK (jsonb_typeof(required_inputs) = 'array' AND jsonb_array_length(required_inputs) > 0),
    as_of_rule TEXT NOT NULL CHECK (length(as_of_rule) > 0),
    definition_hash CHAR(64) NOT NULL CHECK (definition_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (feature_key, feature_version),
    UNIQUE (definition_hash)
);

CREATE FUNCTION quantrade.prevent_feature_definition_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'feature definitions are immutable; create a new version instead';
END;
$$;

CREATE TRIGGER feature_definitions_immutable
BEFORE UPDATE OR DELETE ON quantrade.feature_definitions
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_feature_definition_mutation();

COMMIT;
