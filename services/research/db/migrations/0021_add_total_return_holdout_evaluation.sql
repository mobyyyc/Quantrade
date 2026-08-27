BEGIN;

ALTER TABLE quantrade.historical_backfill_chunks
    DROP CONSTRAINT historical_backfill_chunks_adjustment_basis_check;
ALTER TABLE quantrade.historical_backfill_chunks
    ADD CONSTRAINT historical_backfill_chunks_adjustment_basis_check
    CHECK (adjustment_basis IN ('unadjusted', 'split_adjusted', 'total_return_adjusted'));

INSERT INTO quantrade.availability_rules
    (rule_key, rule_version, provider, data_domain, description, data_capability_tier, point_in_time_verified, rule_hash)
VALUES
    ('alpaca_historical_eod_close', 'v1-total-return-holdout', 'alpaca', 'market_bar',
     'Provider adjustment=all bars are retrieved ex post solely for locked-holdout execution return accounting. They are not eligible for model features or decision-time replay.', 'B', false,
     'abc1d275d5403b2d36d5d143bab92f909c58ec2bbcbb16ae0153158f9d118a65'),
    ('alpaca_historical_eod_close', 'v1-total-return-holdout-benchmark', 'alpaca', 'benchmark_bar',
     'Provider adjustment=all SPY bars are retrieved ex post solely for locked-holdout benchmark return accounting. They are not eligible for model features or decision-time replay.', 'B', false,
     '5a4b99f0e9bdc901d8b61d0bc0376125638bc3e7d81c84e90f963b3b1a036a57');

COMMIT;
