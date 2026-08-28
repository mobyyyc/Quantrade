-- Preserve append-only SEC fact observations and the conservative buffered
-- availability rule used by future monthly accounting research.
--
-- Existing canonical filing_facts remain available to the active baseline.
-- New research must select from filing_fact_observations so later provider
-- responses cannot overwrite its historical input values. The large legacy
-- copy is deliberately a separate resumable operation, not a transaction that
-- can block normal database work during a schema migration.

BEGIN;

INSERT INTO quantrade.availability_rules
    (rule_key, rule_version, provider, data_domain, description, data_capability_tier, point_in_time_verified, rule_hash)
VALUES
    ('sec_filing_acceptance_buffered', 'v1', 'sec_edgar', 'filing_fact',
     'A SEC filing fact becomes eligible five minutes after the EDGAR acceptance timestamp.', 'B', true,
     'b74056cc805f0d39d50576a7e5600e305befa6533171b8e2ad72a9f3d384966f');

ALTER TABLE quantrade.filings
    ADD COLUMN submitted_form TEXT,
    ADD COLUMN is_amendment BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE quantrade.filing_fact_observations (
    filing_fact_observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filing_id UUID NOT NULL REFERENCES quantrade.filings(filing_id),
    security_id UUID NOT NULL REFERENCES quantrade.securities(security_id),
    taxonomy TEXT NOT NULL CHECK (length(taxonomy) > 0),
    concept TEXT NOT NULL CHECK (length(concept) > 0),
    unit TEXT NOT NULL CHECK (length(unit) > 0),
    fact_value NUMERIC(30, 10) NOT NULL,
    period_start DATE,
    period_end DATE NOT NULL,
    fiscal_year SMALLINT CHECK (fiscal_year >= 1900),
    fiscal_period TEXT CHECK (fiscal_period IN ('FY', 'Q1', 'Q2', 'Q3', 'Q4')),
    available_at TIMESTAMPTZ NOT NULL,
    availability_rule_id UUID NOT NULL REFERENCES quantrade.availability_rules(availability_rule_id),
    raw_artifact_id UUID NOT NULL REFERENCES quantrade.raw_artifacts(raw_artifact_id),
    source_reference TEXT NOT NULL CHECK (length(source_reference) > 0),
    source_receipt_id UUID REFERENCES quantrade.source_receipts(source_receipt_id),
    observed_at TIMESTAMPTZ NOT NULL,
    observation_kind TEXT NOT NULL CHECK (observation_kind IN ('legacy_snapshot', 'ingestion')),
    observation_hash CHAR(64) NOT NULL CHECK (observation_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (period_start IS NULL OR period_start <= period_end),
    UNIQUE (observation_hash)
);

CREATE INDEX filing_fact_observations_security_concept_period_idx
    ON quantrade.filing_fact_observations (security_id, taxonomy, concept, period_end DESC, available_at DESC);
CREATE INDEX filing_fact_observations_filing_idx
    ON quantrade.filing_fact_observations (filing_id, available_at);

CREATE FUNCTION quantrade.prevent_filing_fact_observation_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'filing fact observations are immutable';
END;
$$;

CREATE TRIGGER filing_fact_observations_immutable
BEFORE UPDATE OR DELETE ON quantrade.filing_fact_observations
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_filing_fact_observation_mutation();

COMMIT;
