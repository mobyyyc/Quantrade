-- Benchmark instruments have their own price table and are deliberately not
-- inserted into the common-stock security master. Preserve their corporate
-- actions in the same separate, append-only manner.

BEGIN;

CREATE TABLE quantrade.benchmark_corporate_actions (
    benchmark_ticker TEXT NOT NULL CHECK (benchmark_ticker ~ '^[A-Z][A-Z. -]{0,14}$'),
    provider_action_id TEXT NOT NULL CHECK (length(provider_action_id) > 0),
    action_type TEXT NOT NULL CHECK (action_type IN (
        'reverse_split', 'forward_split', 'unit_split', 'cash_dividend',
        'stock_dividend', 'spin_off', 'cash_merger', 'stock_merger',
        'stock_and_cash_merger', 'redemption', 'name_change',
        'worthless_removal', 'rights_distribution', 'partial_call', 'reorganization'
    )),
    process_date DATE NOT NULL,
    effective_date DATE,
    cash_amount NUMERIC(20, 8),
    ratio_numerator NUMERIC(20, 8),
    ratio_denominator NUMERIC(20, 8),
    currency CHAR(3) CHECK (currency IS NULL OR currency = 'USD'),
    available_at TIMESTAMPTZ NOT NULL,
    availability_rule_id UUID NOT NULL REFERENCES quantrade.availability_rules(availability_rule_id),
    ingested_at TIMESTAMPTZ NOT NULL,
    raw_artifact_id UUID NOT NULL REFERENCES quantrade.raw_artifacts(raw_artifact_id),
    source_reference TEXT NOT NULL CHECK (length(source_reference) > 0),
    source_receipt_id UUID REFERENCES quantrade.source_receipts(source_receipt_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (ratio_numerator IS NULL OR ratio_numerator > 0),
    CHECK (ratio_denominator IS NULL OR ratio_denominator > 0),
    PRIMARY KEY (benchmark_ticker, provider_action_id)
);

CREATE INDEX benchmark_corporate_actions_ticker_effective_idx
    ON quantrade.benchmark_corporate_actions
    (benchmark_ticker, effective_date DESC, process_date DESC);
CREATE INDEX benchmark_corporate_actions_available_at_idx
    ON quantrade.benchmark_corporate_actions (available_at);

CREATE TRIGGER benchmark_corporate_actions_immutable
BEFORE UPDATE OR DELETE ON quantrade.benchmark_corporate_actions
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_historical_lineage_mutation();

COMMIT;
