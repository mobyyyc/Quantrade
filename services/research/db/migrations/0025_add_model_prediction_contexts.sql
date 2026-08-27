BEGIN;

CREATE TABLE quantrade.model_prediction_contexts (
    model_prediction_context_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_version TEXT NOT NULL UNIQUE REFERENCES quantrade.model_cards(model_version),
    context_schema_version TEXT NOT NULL CHECK (context_schema_version = 'development_monthly_calibration_v1'),
    benchmark_ticker TEXT NOT NULL CHECK (benchmark_ticker = 'SPY'),
    horizon_sessions INTEGER NOT NULL CHECK (horizon_sessions = 20),
    portfolio_size INTEGER NOT NULL CHECK (portfolio_size = 20),
    calibration_status TEXT NOT NULL CHECK (calibration_status IN ('supported', 'unsupported_nonpositive_slope')),
    calibration_intercept NUMERIC(18, 12),
    calibration_slope NUMERIC(18, 12),
    residual_lower_quantile NUMERIC(18, 12) NOT NULL,
    residual_upper_quantile NUMERIC(18, 12) NOT NULL,
    development_validation_start DATE NOT NULL,
    development_validation_end DATE NOT NULL,
    validation_example_count INTEGER NOT NULL CHECK (validation_example_count > 0),
    monthly_formation_count INTEGER NOT NULL CHECK (monthly_formation_count >= 10),
    artifact_uri TEXT NOT NULL CHECK (length(artifact_uri) > 0),
    artifact_sha256 CHAR(64) NOT NULL CHECK (artifact_sha256 ~ '^[0-9a-f]{64}$'),
    source_experiment_sha256 CHAR(64) NOT NULL CHECK (source_experiment_sha256 ~ '^[0-9a-f]{64}$'),
    holdout_used BOOLEAN NOT NULL CHECK (holdout_used = FALSE),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (development_validation_start <= development_validation_end),
    CHECK (residual_lower_quantile <= residual_upper_quantile),
    CHECK (
        (calibration_status = 'supported' AND calibration_intercept IS NOT NULL AND calibration_slope > 0)
        OR
        (calibration_status = 'unsupported_nonpositive_slope' AND calibration_intercept IS NULL AND calibration_slope IS NULL)
    )
);

CREATE FUNCTION quantrade.prevent_model_prediction_context_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'model prediction contexts are immutable';
END;
$$;

CREATE TRIGGER model_prediction_contexts_immutable
BEFORE UPDATE OR DELETE ON quantrade.model_prediction_contexts
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_model_prediction_context_mutation();

COMMIT;
