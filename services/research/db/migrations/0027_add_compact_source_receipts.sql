-- Add compact, immutable provider receipts for future metadata-only ingestion.
-- This is additive: existing raw artifacts remain authoritative until a later
-- approved migration moves writers to source_receipt_id.

BEGIN;

CREATE TABLE quantrade.source_receipts (
    source_receipt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider TEXT NOT NULL CHECK (provider IN ('sec_edgar', 'alpaca', 'fred', 'alfred', 'manual')),
    source_reference TEXT NOT NULL CHECK (length(source_reference) > 0),
    response_category TEXT NOT NULL CHECK (response_category IN (
        'sec_daily_index', 'sec_submissions', 'sec_company_facts',
        'alpaca_daily_bars', 'alpaca_corporate_actions', 'manual'
    )),
    content_sha256 CHAR(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    byte_count BIGINT NOT NULL CHECK (byte_count >= 0),
    parser_version TEXT NOT NULL CHECK (length(parser_version) > 0),
    payload_retained BOOLEAN NOT NULL DEFAULT FALSE,
    content_type TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, source_reference, content_sha256, parser_version)
);

CREATE TABLE quantrade.source_receipt_retrievals (
    source_receipt_retrieval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_receipt_id UUID NOT NULL REFERENCES quantrade.source_receipts(source_receipt_id),
    retrieved_at TIMESTAMPTZ NOT NULL,
    http_status SMALLINT CHECK (http_status BETWEEN 100 AND 599),
    provider_request_id TEXT,
    etag TEXT,
    last_modified TEXT,
    retrieval_context JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(retrieval_context) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_receipt_id, retrieved_at)
);

-- New writers can populate these optional links while the historical raw
-- artifact references remain intact. A later, separately approved migration
-- may make them mandatory for compact-ingestion records.
ALTER TABLE quantrade.daily_price_bars
    ADD COLUMN source_receipt_id UUID REFERENCES quantrade.source_receipts(source_receipt_id);
ALTER TABLE quantrade.benchmark_daily_price_bars
    ADD COLUMN source_receipt_id UUID REFERENCES quantrade.source_receipts(source_receipt_id);
ALTER TABLE quantrade.corporate_actions
    ADD COLUMN source_receipt_id UUID REFERENCES quantrade.source_receipts(source_receipt_id);
ALTER TABLE quantrade.filings
    ADD COLUMN source_receipt_id UUID REFERENCES quantrade.source_receipts(source_receipt_id);
ALTER TABLE quantrade.filing_facts
    ADD COLUMN source_receipt_id UUID REFERENCES quantrade.source_receipts(source_receipt_id);

CREATE INDEX source_receipts_provider_reference_idx
    ON quantrade.source_receipts (provider, source_reference, created_at DESC);
CREATE INDEX source_receipt_retrievals_receipt_idx
    ON quantrade.source_receipt_retrievals (source_receipt_id, retrieved_at DESC);
CREATE INDEX daily_price_bars_source_receipt_idx
    ON quantrade.daily_price_bars (source_receipt_id) WHERE source_receipt_id IS NOT NULL;
CREATE INDEX benchmark_daily_price_bars_source_receipt_idx
    ON quantrade.benchmark_daily_price_bars (source_receipt_id) WHERE source_receipt_id IS NOT NULL;
CREATE INDEX corporate_actions_source_receipt_idx
    ON quantrade.corporate_actions (source_receipt_id) WHERE source_receipt_id IS NOT NULL;
CREATE INDEX filings_source_receipt_idx
    ON quantrade.filings (source_receipt_id) WHERE source_receipt_id IS NOT NULL;
CREATE INDEX filing_facts_source_receipt_idx
    ON quantrade.filing_facts (source_receipt_id) WHERE source_receipt_id IS NOT NULL;

CREATE TRIGGER source_receipts_immutable
BEFORE UPDATE OR DELETE ON quantrade.source_receipts
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_historical_lineage_mutation();
CREATE TRIGGER source_receipt_retrievals_immutable
BEFORE UPDATE OR DELETE ON quantrade.source_receipt_retrievals
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_historical_lineage_mutation();

COMMIT;
