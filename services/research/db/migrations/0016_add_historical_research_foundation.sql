-- Durable lineage, availability rules, and cohort governance for historical research.
-- Existing raw artifacts remain the normalized-table foreign-key target. This migration
-- adds an immutable content document and retrieval history above that representation.

BEGIN;

CREATE TABLE quantrade.raw_documents (
    raw_document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider TEXT NOT NULL CHECK (provider IN ('sec_edgar', 'alpaca', 'fred', 'alfred', 'manual')),
    content_sha256 CHAR(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    canonical_storage_uri TEXT NOT NULL CHECK (length(canonical_storage_uri) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, content_sha256)
);

CREATE TABLE quantrade.raw_document_retrievals (
    raw_document_retrieval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_document_id UUID NOT NULL REFERENCES quantrade.raw_documents(raw_document_id),
    raw_artifact_id UUID NOT NULL UNIQUE REFERENCES quantrade.raw_artifacts(raw_artifact_id),
    source_reference TEXT NOT NULL CHECK (length(source_reference) > 0),
    retrieved_at TIMESTAMPTZ NOT NULL,
    retrieval_context JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(retrieval_context) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO quantrade.raw_documents (provider, content_sha256, canonical_storage_uri)
SELECT DISTINCT ON (provider, content_sha256)
       provider, content_sha256, storage_uri
FROM quantrade.raw_artifacts
WHERE content_sha256 IS NOT NULL
ORDER BY provider, content_sha256, created_at ASC;

INSERT INTO quantrade.raw_document_retrievals
    (raw_document_id, raw_artifact_id, source_reference, retrieved_at)
SELECT document.raw_document_id, artifact.raw_artifact_id, artifact.source_reference, artifact.retrieved_at
FROM quantrade.raw_artifacts AS artifact
JOIN quantrade.raw_documents AS document
  ON document.provider = artifact.provider
 AND document.content_sha256 = artifact.content_sha256
WHERE artifact.content_sha256 IS NOT NULL;

CREATE TABLE quantrade.availability_rules (
    availability_rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_key TEXT NOT NULL CHECK (rule_key ~ '^[a-z][a-z0-9_]*$'),
    rule_version TEXT NOT NULL CHECK (length(rule_version) > 0),
    provider TEXT NOT NULL CHECK (provider IN ('sec_edgar', 'alpaca', 'fred', 'alfred', 'manual')),
    data_domain TEXT NOT NULL CHECK (data_domain IN ('filing_fact', 'market_bar', 'benchmark_bar', 'universe', 'sector', 'macro')),
    description TEXT NOT NULL CHECK (length(description) > 0),
    data_capability_tier CHAR(1) NOT NULL CHECK (data_capability_tier IN ('A', 'B', 'C')),
    point_in_time_verified BOOLEAN NOT NULL,
    rule_hash CHAR(64) NOT NULL CHECK (rule_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (rule_key, rule_version),
    UNIQUE (rule_hash)
);

INSERT INTO quantrade.availability_rules
    (rule_key, rule_version, provider, data_domain, description, data_capability_tier, point_in_time_verified, rule_hash)
VALUES
    ('sec_filing_acceptance', 'v1', 'sec_edgar', 'filing_fact',
     'A filing fact becomes eligible at the SEC EDGAR acceptance timestamp.', 'B', true,
     '27eb4e0d0fe6bf352d5d7b4e167f33419fa639d3973f3841f6a7ddb3b68db5bb'),
    ('alpaca_retrieval', 'v1', 'alpaca', 'market_bar',
     'Live market bars become eligible when retrieved by the documented post-close pipeline.', 'B', false,
     '660db4bb5f29bf4dbe7762bd89732a37bf0cefcfcaea172c7750bf7b5247fdbb'),
    ('alpaca_retrieval', 'v1-benchmark', 'alpaca', 'benchmark_bar',
     'Live benchmark bars become eligible when retrieved by the documented post-close pipeline.', 'B', false,
     'fef0f1f70ea2d69003aaf7fe7d05b2e51b595727b0cfecc9c7edfd7436e60612'),
    ('current_static_membership', 'v1', 'manual', 'universe',
     'A fixed current constituent cohort is survivorship-biased and is not historical index membership.', 'B', false,
     '8a45c2ca912ad08a34a92e6e4765d9d24bcbdf93a28b46c74c4f9a86438e6845'),
    ('current_static_sector', 'v1', 'manual', 'sector',
     'A fixed current sector mapping is a Tier B research grouping, not a dated historical classification.', 'B', false,
     '8ed834c523ad4ee1ec1f59c9b825e719f8202184ce6c4a3b35f7cefe4a3f18dc');

CREATE TABLE quantrade.research_cohorts (
    research_cohort_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cohort_code TEXT NOT NULL UNIQUE CHECK (cohort_code ~ '^[a-z][a-z0-9_]*$'),
    cohort_kind TEXT NOT NULL CHECK (cohort_kind IN ('current_survivors', 'verified_pit')),
    source_universe_snapshot_id UUID REFERENCES quantrade.universe_snapshots(universe_snapshot_id),
    data_capability_tier CHAR(1) NOT NULL CHECK (data_capability_tier IN ('A', 'B', 'C')),
    historical_membership_verified BOOLEAN NOT NULL,
    survivorship_biased BOOLEAN NOT NULL,
    sector_classification_point_in_time BOOLEAN NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'deferred', 'retired')),
    provenance_note TEXT NOT NULL CHECK (length(provenance_note) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (cohort_kind = 'current_survivors'
         AND data_capability_tier = 'B'
         AND NOT historical_membership_verified
         AND survivorship_biased)
        OR cohort_kind = 'verified_pit'
    )
);

CREATE TABLE quantrade.research_cohort_memberships (
    research_cohort_id UUID NOT NULL REFERENCES quantrade.research_cohorts(research_cohort_id),
    security_id UUID NOT NULL REFERENCES quantrade.securities(security_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (research_cohort_id, security_id)
);

CREATE TABLE quantrade.historical_backfill_runs (
    historical_backfill_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    research_cohort_id UUID NOT NULL REFERENCES quantrade.research_cohorts(research_cohort_id),
    availability_rule_id UUID NOT NULL REFERENCES quantrade.availability_rules(availability_rule_id),
    data_domain TEXT NOT NULL CHECK (data_domain IN ('filing_fact', 'market_bar', 'benchmark_bar', 'universe', 'sector', 'macro')),
    provider TEXT NOT NULL CHECK (provider IN ('sec_edgar', 'alpaca', 'fred', 'alfred', 'manual')),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'skipped')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    requested_count INTEGER NOT NULL DEFAULT 0 CHECK (requested_count >= 0),
    persisted_count INTEGER NOT NULL DEFAULT 0 CHECK (persisted_count >= 0),
    withheld_count INTEGER NOT NULL DEFAULT 0 CHECK (withheld_count >= 0),
    manifest_uri TEXT CHECK (manifest_uri IS NULL OR length(manifest_uri) > 0),
    failure_reason TEXT,
    CHECK (start_date <= end_date),
    CHECK (
        (status = 'completed' AND completed_at IS NOT NULL AND failure_reason IS NULL)
        OR (status = 'failed' AND completed_at IS NOT NULL AND failure_reason IS NOT NULL)
        OR (status = 'skipped' AND completed_at IS NOT NULL AND failure_reason IS NOT NULL)
        OR status = 'running'
    )
);

CREATE TABLE quantrade.training_dataset_provenance (
    training_dataset_provenance_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_key TEXT NOT NULL CHECK (dataset_key ~ '^[a-z][a-z0-9_]*$'),
    dataset_version TEXT NOT NULL CHECK (length(dataset_version) > 0),
    research_cohort_id UUID NOT NULL REFERENCES quantrade.research_cohorts(research_cohort_id),
    primary_label_horizon_sessions INTEGER NOT NULL CHECK (primary_label_horizon_sessions IN (5, 20, 60)),
    data_capability_tier CHAR(1) NOT NULL CHECK (data_capability_tier IN ('A', 'B', 'C')),
    historical_start_date DATE NOT NULL,
    historical_end_date DATE NOT NULL,
    provenance_status TEXT NOT NULL CHECK (provenance_status IN ('draft', 'ready', 'blocked')),
    limitations JSONB NOT NULL CHECK (jsonb_typeof(limitations) = 'array'),
    manifest_uri TEXT NOT NULL CHECK (length(manifest_uri) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (historical_start_date <= historical_end_date),
    UNIQUE (dataset_key, dataset_version)
);

CREATE INDEX raw_document_retrievals_document_idx
    ON quantrade.raw_document_retrievals (raw_document_id, retrieved_at);
CREATE INDEX research_cohort_memberships_security_idx
    ON quantrade.research_cohort_memberships (security_id);
CREATE INDEX historical_backfill_runs_cohort_status_idx
    ON quantrade.historical_backfill_runs (research_cohort_id, data_domain, status, start_date, end_date);

CREATE FUNCTION quantrade.prevent_historical_lineage_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'historical lineage records are immutable';
END;
$$;

CREATE FUNCTION quantrade.prevent_completed_historical_backfill_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' OR OLD.status IN ('completed', 'failed', 'skipped') THEN
        RAISE EXCEPTION 'completed historical backfill records are immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER raw_documents_immutable
BEFORE UPDATE OR DELETE ON quantrade.raw_documents
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_historical_lineage_mutation();
CREATE TRIGGER raw_document_retrievals_immutable
BEFORE UPDATE OR DELETE ON quantrade.raw_document_retrievals
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_historical_lineage_mutation();
CREATE TRIGGER availability_rules_immutable
BEFORE UPDATE OR DELETE ON quantrade.availability_rules
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_historical_lineage_mutation();
CREATE TRIGGER research_cohorts_immutable
BEFORE UPDATE OR DELETE ON quantrade.research_cohorts
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_historical_lineage_mutation();
CREATE TRIGGER research_cohort_memberships_immutable
BEFORE UPDATE OR DELETE ON quantrade.research_cohort_memberships
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_historical_lineage_mutation();
CREATE TRIGGER training_dataset_provenance_immutable
BEFORE UPDATE OR DELETE ON quantrade.training_dataset_provenance
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_historical_lineage_mutation();
CREATE TRIGGER historical_backfill_runs_terminal_immutable
BEFORE UPDATE OR DELETE ON quantrade.historical_backfill_runs
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_completed_historical_backfill_mutation();

COMMIT;
