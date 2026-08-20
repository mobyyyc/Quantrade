-- Immutable final-holdout locks and experiment records.

BEGIN;

CREATE TABLE quantrade.holdout_periods (
    holdout_period_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    protocol_version TEXT NOT NULL UNIQUE CHECK (length(protocol_version) > 0),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    locked_at TIMESTAMPTZ NOT NULL,
    rationale TEXT NOT NULL CHECK (length(rationale) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (start_date <= end_date)
);

CREATE TABLE quantrade.experiment_records (
    experiment_record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_key TEXT NOT NULL UNIQUE CHECK (length(experiment_key) > 0),
    holdout_period_id UUID NOT NULL REFERENCES quantrade.holdout_periods(holdout_period_id),
    created_at TIMESTAMPTZ NOT NULL,
    model_version TEXT NOT NULL CHECK (length(model_version) > 0),
    feature_registry_hash CHAR(64) NOT NULL CHECK (feature_registry_hash ~ '^[0-9a-f]{64}$'),
    training_end_date DATE NOT NULL,
    validation_end_date DATE NOT NULL,
    result_uri TEXT NOT NULL CHECK (length(result_uri) > 0),
    CHECK (training_end_date <= validation_end_date)
);

CREATE FUNCTION quantrade.prevent_experiment_governance_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'holdout periods and experiment records are immutable';
END;
$$;

CREATE TRIGGER holdout_periods_immutable
BEFORE UPDATE OR DELETE ON quantrade.holdout_periods
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_experiment_governance_mutation();

CREATE TRIGGER experiment_records_immutable
BEFORE UPDATE OR DELETE ON quantrade.experiment_records
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_experiment_governance_mutation();

COMMIT;
