BEGIN;

ALTER TABLE quantrade.availability_rules
    DROP CONSTRAINT availability_rules_data_domain_check;
ALTER TABLE quantrade.availability_rules
    ADD CONSTRAINT availability_rules_data_domain_check
    CHECK (data_domain IN ('filing_fact', 'market_bar', 'benchmark_bar', 'corporate_action', 'universe', 'sector', 'macro'));

ALTER TABLE quantrade.historical_backfill_runs
    DROP CONSTRAINT historical_backfill_runs_data_domain_check;
ALTER TABLE quantrade.historical_backfill_runs
    ADD CONSTRAINT historical_backfill_runs_data_domain_check
    CHECK (data_domain IN ('filing_fact', 'market_bar', 'benchmark_bar', 'corporate_action', 'universe', 'sector', 'macro'));

INSERT INTO quantrade.availability_rules
    (rule_key, rule_version, provider, data_domain, description, data_capability_tier, point_in_time_verified, rule_hash)
VALUES
    ('alpaca_historical_eod_close', 'v1-corporate-action', 'alpaca', 'corporate_action',
     'Historical corporate actions are conservatively available at 6:00 p.m. America/Toronto on the provider process date; Tier-B and not independently point-in-time verified.', 'B', false,
     '1a1e7cf52eaf8304b54cd7e5bf450167416800567abc33ae23fc740c6d5367e8');

COMMIT;
