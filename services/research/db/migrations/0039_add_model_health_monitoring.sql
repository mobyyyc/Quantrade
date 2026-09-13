-- Immutable post-publication model-health snapshots and their supporting metrics.

BEGIN;

CREATE TABLE quantrade.model_health_snapshots (
    model_health_snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    score_date DATE NOT NULL UNIQUE,
    decision_at TIMESTAMPTZ NOT NULL,
    model_version TEXT NOT NULL REFERENCES quantrade.model_artifacts(model_version),
    protocol_version TEXT NOT NULL CHECK (length(protocol_version) > 0),
    cohort_size INTEGER NOT NULL CHECK (cohort_size > 0),
    eligible_count INTEGER NOT NULL CHECK (eligible_count >= 0 AND eligible_count <= cohort_size),
    excluded_count INTEGER NOT NULL CHECK (excluded_count = cohort_size - eligible_count),
    coverage_ratio NUMERIC(12, 10) NOT NULL CHECK (coverage_ratio >= 0 AND coverage_ratio <= 1),
    previous_score_date DATE,
    top_20_churn_ratio NUMERIC(12, 10) CHECK (top_20_churn_ratio >= 0 AND top_20_churn_ratio <= 1),
    mean_normalized_rank_change NUMERIC(12, 10) CHECK (mean_normalized_rank_change >= 0 AND mean_normalized_rank_change <= 1),
    forward_outcome_readiness_snapshot_id UUID REFERENCES quantrade.forward_outcome_readiness_snapshots(forward_outcome_readiness_snapshot_id),
    artifact_hash_matches BOOLEAN NOT NULL,
    registry_hash_matches BOOLEAN NOT NULL,
    explanation_lineage_matches BOOLEAN NOT NULL,
    health_status TEXT NOT NULL CHECK (health_status IN ('healthy', 'warning', 'critical')),
    logical_sha256 CHAR(64) NOT NULL CHECK (logical_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (previous_score_date IS NULL OR previous_score_date < score_date),
    UNIQUE (score_date, logical_sha256)
);

CREATE TABLE quantrade.model_health_feature_metrics (
    model_health_snapshot_id UUID NOT NULL REFERENCES quantrade.model_health_snapshots(model_health_snapshot_id),
    feature_key TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    definition_hash CHAR(64) NOT NULL CHECK (definition_hash ~ '^[0-9a-f]{64}$'),
    available_count INTEGER NOT NULL CHECK (available_count >= 0),
    unavailable_count INTEGER NOT NULL CHECK (unavailable_count >= 0),
    missing_ratio NUMERIC(12, 10) NOT NULL CHECK (missing_ratio >= 0 AND missing_ratio <= 1),
    mean_percentile NUMERIC(20, 16),
    reference_mean_percentile NUMERIC(20, 16),
    population_stability_index NUMERIC(20, 16) CHECK (population_stability_index >= 0),
    reference_observation_count INTEGER NOT NULL CHECK (reference_observation_count >= 0),
    status TEXT NOT NULL CHECK (status IN ('healthy', 'warning', 'critical', 'insufficient_reference')),
    PRIMARY KEY (model_health_snapshot_id, feature_key, feature_version)
);

CREATE TABLE quantrade.model_health_exclusion_metrics (
    model_health_snapshot_id UUID NOT NULL REFERENCES quantrade.model_health_snapshots(model_health_snapshot_id),
    reason_code TEXT NOT NULL CHECK (reason_code ~ '^[a-z][a-z0-9_]*$'),
    excluded_count INTEGER NOT NULL CHECK (excluded_count > 0),
    PRIMARY KEY (model_health_snapshot_id, reason_code)
);

CREATE TABLE quantrade.model_health_alerts (
    model_health_snapshot_id UUID NOT NULL REFERENCES quantrade.model_health_snapshots(model_health_snapshot_id),
    alert_code TEXT NOT NULL CHECK (alert_code ~ '^[a-z][a-z0-9_]*$'),
    severity TEXT NOT NULL CHECK (severity IN ('warning', 'critical')),
    metric_key TEXT NOT NULL CHECK (length(metric_key) > 0),
    observed_value TEXT NOT NULL CHECK (length(observed_value) > 0),
    threshold_value TEXT NOT NULL CHECK (length(threshold_value) > 0),
    detail TEXT NOT NULL CHECK (length(detail) > 0),
    PRIMARY KEY (model_health_snapshot_id, alert_code, metric_key)
);

CREATE INDEX model_health_snapshots_date_idx
    ON quantrade.model_health_snapshots (score_date DESC);

CREATE FUNCTION quantrade.prevent_model_health_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'model-health records are immutable';
END;
$$;

CREATE TRIGGER model_health_snapshots_immutable
BEFORE UPDATE OR DELETE ON quantrade.model_health_snapshots
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_model_health_mutation();

CREATE TRIGGER model_health_feature_metrics_immutable
BEFORE UPDATE OR DELETE ON quantrade.model_health_feature_metrics
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_model_health_mutation();

CREATE TRIGGER model_health_exclusion_metrics_immutable
BEFORE UPDATE OR DELETE ON quantrade.model_health_exclusion_metrics
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_model_health_mutation();

CREATE TRIGGER model_health_alerts_immutable
BEFORE UPDATE OR DELETE ON quantrade.model_health_alerts
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_model_health_mutation();

COMMIT;
