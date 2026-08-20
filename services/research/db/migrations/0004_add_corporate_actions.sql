BEGIN;

CREATE TABLE quantrade.corporate_actions (
    corporate_action_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    security_id UUID NOT NULL REFERENCES quantrade.securities(security_id),
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
    ingested_at TIMESTAMPTZ NOT NULL,
    raw_artifact_id UUID NOT NULL REFERENCES quantrade.raw_artifacts(raw_artifact_id),
    source_reference TEXT NOT NULL CHECK (length(source_reference) > 0),
    provider_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (ratio_numerator IS NULL OR ratio_numerator > 0),
    CHECK (ratio_denominator IS NULL OR ratio_denominator > 0),
    UNIQUE (provider_action_id)
);

CREATE INDEX corporate_actions_security_effective_idx
    ON quantrade.corporate_actions (security_id, effective_date DESC, process_date DESC);
CREATE INDEX corporate_actions_available_at_idx
    ON quantrade.corporate_actions (available_at);

COMMIT;
