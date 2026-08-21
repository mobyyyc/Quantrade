-- Reference-index bars are stored separately from the common-stock universe.

BEGIN;

CREATE TABLE quantrade.benchmark_daily_price_bars (
    benchmark_ticker TEXT NOT NULL CHECK (benchmark_ticker ~ '^[A-Z][A-Z. -]{0,14}$'),
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
    available_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    raw_artifact_id UUID NOT NULL REFERENCES quantrade.raw_artifacts(raw_artifact_id),
    source_reference TEXT NOT NULL CHECK (length(source_reference) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (high_price >= low_price),
    CHECK (high_price >= open_price AND high_price >= close_price),
    CHECK (low_price <= open_price AND low_price <= close_price),
    CHECK (available_at >= COALESCE(observed_at, available_at)),
    PRIMARY KEY (benchmark_ticker, session_date, session, adjustment_basis)
);

CREATE INDEX benchmark_daily_price_bars_ticker_date_idx
    ON quantrade.benchmark_daily_price_bars (benchmark_ticker, session_date DESC);

COMMIT;
