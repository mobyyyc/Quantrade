-- Retire the unnecessary legacy-copy experiment and freeze the canonical SEC
-- fact store. New facts remain insertable; existing facts cannot be changed or
-- deleted. Future changed provider observations remain append-only in
-- filing_fact_observations.

BEGIN;

DROP TRIGGER filing_fact_observations_immutable
    ON quantrade.filing_fact_observations;

DELETE FROM quantrade.filing_fact_observations
WHERE observation_kind = 'legacy_snapshot';

ALTER TABLE quantrade.filing_fact_observations
    DROP CONSTRAINT filing_fact_observations_observation_kind_check;
ALTER TABLE quantrade.filing_fact_observations
    ADD CONSTRAINT filing_fact_observations_observation_kind_check
    CHECK (observation_kind = 'ingestion');

CREATE TRIGGER filing_fact_observations_immutable
BEFORE UPDATE OR DELETE ON quantrade.filing_fact_observations
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_filing_fact_observation_mutation();

DROP TRIGGER sec_fact_snapshot_runs_terminal_immutable
    ON quantrade.sec_fact_snapshot_runs;
DROP TABLE quantrade.sec_fact_snapshot_runs;
DROP FUNCTION quantrade.prevent_terminal_sec_fact_snapshot_run_mutation();

CREATE FUNCTION quantrade.prevent_filing_fact_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'canonical SEC filing facts are append-only';
END;
$$;

CREATE TRIGGER filing_facts_append_only
BEFORE UPDATE OR DELETE ON quantrade.filing_facts
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_filing_fact_mutation();

COMMIT;
