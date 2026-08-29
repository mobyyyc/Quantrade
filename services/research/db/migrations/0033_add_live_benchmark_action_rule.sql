-- Live SPY actions use retrieval time, separately from historical Tier-B rules.

BEGIN;

INSERT INTO quantrade.availability_rules
    (rule_key, rule_version, provider, data_domain, description,
     data_capability_tier, point_in_time_verified, rule_hash)
VALUES
    ('alpaca_retrieval', 'v1-benchmark-corporate-action', 'alpaca', 'corporate_action',
     'Live benchmark corporate actions become eligible when retrieved by the documented update pipeline.',
     'B', false, 'd4417b89a193cd5c6edc55e4874f636507898de6d72e6a664ed2c1e296292c2c');

COMMIT;
