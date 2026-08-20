-- Quantrade core normalized store (PostgreSQL 15+).
-- Apply once, in order, using `psql -v ON_ERROR_STOP=1 -f`.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS quantrade;

CREATE TABLE quantrade.raw_artifacts (
    raw_artifact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider TEXT NOT NULL CHECK (provider IN ('sec_edgar', 'alpaca', 'fred', 'alfred', 'manual')),
    source_reference TEXT NOT NULL CHECK (length(source_reference) > 0),
    storage_uri TEXT NOT NULL UNIQUE CHECK (length(storage_uri) > 0),
    retrieved_at TIMESTAMPTZ NOT NULL,
    content_sha256 CHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE quantrade.securities (
    security_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issuer_name TEXT NOT NULL CHECK (length(issuer_name) > 0),
    asset_class TEXT NOT NULL CHECK (asset_class = 'common_stock'),
    country_code CHAR(2) NOT NULL CHECK (country_code = 'US'),
    valid_from DATE NOT NULL,
    valid_to DATE,
    raw_artifact_id UUID NOT NULL REFERENCES quantrade.raw_artifacts(raw_artifact_id),
    source_reference TEXT NOT NULL CHECK (length(source_reference) > 0),
    ingested_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE TABLE quantrade.security_identifiers (
    security_identifier_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    security_id UUID NOT NULL REFERENCES quantrade.securities(security_id),
    identifier_type TEXT NOT NULL CHECK (identifier_type IN ('ticker', 'cik', 'figi', 'isin')),
    identifier_value TEXT NOT NULL CHECK (length(identifier_value) > 0),
    valid_from DATE NOT NULL,
    valid_to DATE,
    raw_artifact_id UUID NOT NULL REFERENCES quantrade.raw_artifacts(raw_artifact_id),
    source_reference TEXT NOT NULL CHECK (length(source_reference) > 0),
    ingested_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    UNIQUE (security_id, identifier_type, identifier_value, valid_from)
);

CREATE TABLE quantrade.listings (
    listing_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    security_id UUID NOT NULL REFERENCES quantrade.securities(security_id),
    ticker TEXT NOT NULL CHECK (ticker ~ '^[A-Z][A-Z. -]{0,14}$'),
    exchange_mic CHAR(4) NOT NULL CHECK (exchange_mic ~ '^[A-Z]{4}$'),
    currency CHAR(3) NOT NULL CHECK (currency = 'USD'),
    valid_from DATE NOT NULL,
    valid_to DATE,
    raw_artifact_id UUID NOT NULL REFERENCES quantrade.raw_artifacts(raw_artifact_id),
    source_reference TEXT NOT NULL CHECK (length(source_reference) > 0),
    ingested_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    UNIQUE (security_id, exchange_mic, ticker, valid_from)
);

CREATE TABLE quantrade.daily_price_bars (
    daily_price_bar_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    security_id UUID NOT NULL REFERENCES quantrade.securities(security_id),
    session_date DATE NOT NULL,
    session TEXT NOT NULL CHECK (session = 'regular'),
    currency CHAR(3) NOT NULL CHECK (currency = 'USD'),
    open_price NUMERIC(20, 8) NOT NULL CHECK (open_price >= 0),
    high_price NUMERIC(20, 8) NOT NULL CHECK (high_price >= 0),
    low_price NUMERIC(20, 8) NOT NULL CHECK (low_price >= 0),
    close_price NUMERIC(20, 8) NOT NULL CHECK (close_price >= 0),
    volume NUMERIC(24, 6) NOT NULL CHECK (volume >= 0),
    adjustment_basis TEXT NOT NULL CHECK (adjustment_basis IN ('unadjusted', 'split_adjusted', 'total_return_adjusted')),
    observed_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    available_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    raw_artifact_id UUID NOT NULL REFERENCES quantrade.raw_artifacts(raw_artifact_id),
    source_reference TEXT NOT NULL CHECK (length(source_reference) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (high_price >= low_price),
    CHECK (high_price >= open_price AND high_price >= close_price),
    CHECK (low_price <= open_price AND low_price <= close_price),
    CHECK (available_at >= COALESCE(published_at, observed_at, available_at)),
    UNIQUE (security_id, session_date, session, adjustment_basis)
);

CREATE TABLE quantrade.filings (
    filing_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    security_id UUID NOT NULL REFERENCES quantrade.securities(security_id),
    accession_number TEXT NOT NULL UNIQUE CHECK (accession_number ~ '^[0-9]{10}-[0-9]{2}-[0-9]{6}$'),
    form TEXT NOT NULL CHECK (form IN ('10-K', '10-Q', '8-K', '20-F', '40-F', 'other')),
    filed_at TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ NOT NULL,
    period_end DATE,
    published_at TIMESTAMPTZ,
    available_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    raw_artifact_id UUID NOT NULL REFERENCES quantrade.raw_artifacts(raw_artifact_id),
    source_reference TEXT NOT NULL CHECK (length(source_reference) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (available_at >= accepted_at),
    CHECK (filed_at >= accepted_at)
);

CREATE TABLE quantrade.filing_facts (
    filing_fact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
    observed_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    available_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    raw_artifact_id UUID NOT NULL REFERENCES quantrade.raw_artifacts(raw_artifact_id),
    source_reference TEXT NOT NULL CHECK (length(source_reference) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (period_start IS NULL OR period_start <= period_end),
    CHECK (available_at >= COALESCE(published_at, observed_at, available_at)),
    UNIQUE (filing_id, taxonomy, concept, unit, period_start, period_end)
);

CREATE TABLE quantrade.score_snapshots (
    score_snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    security_id UUID NOT NULL REFERENCES quantrade.securities(security_id),
    score_date DATE NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ,
    score NUMERIC(5, 2) NOT NULL CHECK (score >= 0 AND score <= 100),
    rank INTEGER CHECK (rank >= 1),
    eligible BOOLEAN NOT NULL,
    signal TEXT NOT NULL CHECK (signal IN ('positive', 'neutral', 'negative', 'unavailable')),
    model_version TEXT NOT NULL CHECK (length(model_version) > 0),
    feature_version TEXT NOT NULL CHECK (length(feature_version) > 0),
    protocol_version TEXT NOT NULL CHECK (length(protocol_version) > 0),
    data_cutoff_at TIMESTAMPTZ NOT NULL,
    data_capability_tier CHAR(1) NOT NULL CHECK (data_capability_tier IN ('A', 'B', 'C')),
    unavailable_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (data_cutoff_at <= decision_at),
    CHECK (
        (eligible AND signal <> 'unavailable' AND unavailable_reason IS NULL)
        OR (NOT eligible AND signal = 'unavailable' AND unavailable_reason IS NOT NULL)
    ),
    UNIQUE (security_id, decision_at, model_version, feature_version, protocol_version)
);

CREATE INDEX listings_security_validity_idx
    ON quantrade.listings (security_id, valid_from, valid_to);
CREATE INDEX listings_ticker_validity_idx
    ON quantrade.listings (ticker, exchange_mic, valid_from, valid_to);
CREATE INDEX daily_price_bars_security_date_idx
    ON quantrade.daily_price_bars (security_id, session_date DESC);
CREATE INDEX daily_price_bars_available_at_idx
    ON quantrade.daily_price_bars (available_at);
CREATE INDEX filings_security_available_at_idx
    ON quantrade.filings (security_id, available_at DESC);
CREATE INDEX filing_facts_security_concept_period_idx
    ON quantrade.filing_facts (security_id, taxonomy, concept, period_end DESC);
CREATE INDEX filing_facts_available_at_idx
    ON quantrade.filing_facts (available_at);
CREATE INDEX score_snapshots_score_date_rank_idx
    ON quantrade.score_snapshots (score_date DESC, rank ASC) WHERE eligible;
CREATE INDEX score_snapshots_security_decision_idx
    ON quantrade.score_snapshots (security_id, decision_at DESC);

CREATE FUNCTION quantrade.prevent_score_snapshot_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'score snapshots are immutable';
END;
$$;

CREATE TRIGGER score_snapshots_immutable
BEFORE UPDATE OR DELETE ON quantrade.score_snapshots
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_score_snapshot_mutation();

COMMIT;
