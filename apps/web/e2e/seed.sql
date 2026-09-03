BEGIN;

INSERT INTO quantrade.raw_artifacts
  (raw_artifact_id, provider, source_reference, storage_uri, retrieved_at, content_sha256)
VALUES
  ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'manual', 'e2e fixture', 'memory://e2e/security-master', '2026-08-25T21:00:00Z', repeat('a', 64)),
  ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'alpaca', 'e2e fixture', 'memory://e2e/market', '2026-08-25T22:30:00Z', repeat('b', 64)),
  ('cccccccc-cccc-4ccc-8ccc-cccccccccccc', 'sec_edgar', 'e2e fixture', 'memory://e2e/sec', '2026-08-25T19:00:00Z', repeat('c', 64));

INSERT INTO quantrade.securities
  (security_id, issuer_name, asset_class, country_code, valid_from, raw_artifact_id, source_reference, ingested_at)
VALUES
  ('11111111-1111-4111-8111-111111111111', 'Apple Inc.', 'common_stock', 'US', '2020-01-01', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'e2e fixture', '2026-08-25T21:00:00Z'),
  ('22222222-2222-4222-8222-222222222222', 'Microsoft Corporation', 'common_stock', 'US', '2020-01-01', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'e2e fixture', '2026-08-25T21:00:00Z');

INSERT INTO quantrade.listings
  (security_id, ticker, exchange_mic, currency, valid_from, raw_artifact_id, source_reference, ingested_at)
VALUES
  ('11111111-1111-4111-8111-111111111111', 'AAPL', 'XNAS', 'USD', '2020-01-01', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'e2e fixture', '2026-08-25T21:00:00Z'),
  ('22222222-2222-4222-8222-222222222222', 'MSFT', 'XNAS', 'USD', '2020-01-01', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'e2e fixture', '2026-08-25T21:00:00Z');

INSERT INTO quantrade.daily_price_bars
  (security_id, session_date, session, currency, open_price, high_price, low_price, close_price, volume, adjustment_basis, observed_at, published_at, available_at, ingested_at, raw_artifact_id, source_reference, availability_rule_id)
SELECT security_id, session_date::date, 'regular', 'USD', open_price, high_price, low_price, close_price, volume, 'split_adjusted',
       session_date::date + time '16:00', session_date::date + time '16:05', session_date::date + time '18:00', '2026-08-25T22:30:00Z',
       'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'e2e fixture',
       (SELECT availability_rule_id FROM quantrade.availability_rules WHERE rule_key='alpaca_retrieval' AND rule_version='v1')
FROM (VALUES
  ('11111111-1111-4111-8111-111111111111'::uuid, '2026-08-22', 224, 226, 223, 225, 50000000),
  ('11111111-1111-4111-8111-111111111111'::uuid, '2026-08-25', 226, 229, 225, 228, 52000000),
  ('22222222-2222-4222-8222-222222222222'::uuid, '2026-08-22', 500, 505, 498, 502, 25000000),
  ('22222222-2222-4222-8222-222222222222'::uuid, '2026-08-25', 503, 507, 501, 506, 27000000)
) AS bars(security_id, session_date, open_price, high_price, low_price, close_price, volume);

INSERT INTO quantrade.benchmark_daily_price_bars
  (benchmark_ticker, session_date, session, currency, open_price, high_price, low_price, close_price, volume, adjustment_basis, observed_at, available_at, ingested_at, raw_artifact_id, source_reference, availability_rule_id)
VALUES
  ('SPY', '2026-08-22', 'regular', 'USD', 650, 653, 649, 652, 60000000, 'split_adjusted', '2026-08-22T20:00:00Z', '2026-08-22T22:00:00Z', '2026-08-25T22:30:00Z', 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'e2e fixture', (SELECT availability_rule_id FROM quantrade.availability_rules WHERE rule_key='alpaca_retrieval' AND rule_version='v1-benchmark')),
  ('SPY', '2026-08-25', 'regular', 'USD', 653, 655, 651, 654, 61000000, 'split_adjusted', '2026-08-25T20:00:00Z', '2026-08-25T22:00:00Z', '2026-08-25T22:30:00Z', 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'e2e fixture', (SELECT availability_rule_id FROM quantrade.availability_rules WHERE rule_key='alpaca_retrieval' AND rule_version='v1-benchmark'));

INSERT INTO quantrade.filings
  (filing_id, security_id, accession_number, form, filed_at, accepted_at, period_end, published_at, available_at, ingested_at, raw_artifact_id, source_reference)
VALUES
  ('dddddddd-dddd-4ddd-8ddd-dddddddddddd', '11111111-1111-4111-8111-111111111111', '0000320193-26-000001', '10-Q', '2026-08-25T18:00:00Z', '2026-08-25T18:05:00Z', '2026-06-30', '2026-08-25T18:05:00Z', '2026-08-25T18:05:00Z', '2026-08-25T19:00:00Z', 'cccccccc-cccc-4ccc-8ccc-cccccccccccc', 'e2e fixture');

INSERT INTO quantrade.filing_facts
  (filing_id, security_id, taxonomy, concept, unit, fact_value, period_end, fiscal_year, fiscal_period, observed_at, published_at, available_at, ingested_at, raw_artifact_id, source_reference)
VALUES
  ('dddddddd-dddd-4ddd-8ddd-dddddddddddd', '11111111-1111-4111-8111-111111111111', 'dei', 'EntityCommonStockSharesOutstanding', 'shares', 15000000000, '2026-06-30', 2026, 'Q2', '2026-08-25T18:05:00Z', '2026-08-25T18:05:00Z', '2026-08-25T18:05:00Z', '2026-08-25T19:00:00Z', 'cccccccc-cccc-4ccc-8ccc-cccccccccccc', 'e2e fixture');

INSERT INTO quantrade.model_cards
  (model_version, status, protocol_version, feature_registry_hash, data_capability_tier, created_at, purpose, methodology, limitations, evaluation_uri)
VALUES
  ('tier_b_monthly_elastic_net_sec_clean_v3', 'research_only', 'monthly_last_session_next_open_v1', repeat('d', 64), 'B', '2026-08-01T00:00:00Z', 'E2E research model', 'Regularized cross-sectional ranking.', '["Tier B fixture"]', 'memory://e2e/evaluation');

INSERT INTO quantrade.model_approval_decisions
  (model_version, approval_scope, approved, evidence, gate_results, decision_uri, decision_sha256, decided_at, decided_by)
VALUES
  ('tier_b_monthly_elastic_net_sec_clean_v3', 'private_beta', true, '{}', '[]', 'memory://e2e/approval', repeat('e', 64), '2026-08-01T01:00:00Z', 'e2e');

INSERT INTO quantrade.model_deployments
  (model_version, approval_scope, approval_evidence_uri, deployed_at, deployed_by)
VALUES
  ('tier_b_monthly_elastic_net_sec_clean_v3', 'private_beta', 'memory://e2e/approval', '2026-08-01T02:00:00Z', 'e2e');

INSERT INTO quantrade.daily_research_runs
  (score_date, status, decision_at, started_at, completed_at, score_snapshot_count, eligible_count)
VALUES
  ('2026-08-22', 'completed', '2026-08-23T00:00:00Z', '2026-08-23T00:00:00Z', '2026-08-23T00:05:00Z', 2, 2),
  ('2026-08-25', 'completed', '2026-08-26T00:00:00Z', '2026-08-26T00:00:00Z', '2026-08-26T00:05:00Z', 2, 2);

INSERT INTO quantrade.score_snapshots
  (score_snapshot_id, security_id, score_date, decision_at, published_at, score, rank, eligible, signal, model_version, feature_version, protocol_version, data_cutoff_at, data_capability_tier)
VALUES
  ('31111111-1111-4111-8111-111111111111', '11111111-1111-4111-8111-111111111111', '2026-08-22', '2026-08-23T00:00:00Z', '2026-08-23T00:05:00Z', 78, 2, true, 'positive', 'tier_b_monthly_elastic_net_sec_clean_v3', 'v3', 'monthly_last_session_next_open_v1', '2026-08-23T00:00:00Z', 'B'),
  ('32222222-2222-4222-8222-222222222222', '22222222-2222-4222-8222-222222222222', '2026-08-22', '2026-08-23T00:00:00Z', '2026-08-23T00:05:00Z', 81, 1, true, 'positive', 'tier_b_monthly_elastic_net_sec_clean_v3', 'v3', 'monthly_last_session_next_open_v1', '2026-08-23T00:00:00Z', 'B'),
  ('41111111-1111-4111-8111-111111111111', '11111111-1111-4111-8111-111111111111', '2026-08-25', '2026-08-26T00:00:00Z', '2026-08-26T00:05:00Z', 84, 1, true, 'positive', 'tier_b_monthly_elastic_net_sec_clean_v3', 'v3', 'monthly_last_session_next_open_v1', '2026-08-26T00:00:00Z', 'B'),
  ('42222222-2222-4222-8222-222222222222', '22222222-2222-4222-8222-222222222222', '2026-08-25', '2026-08-26T00:00:00Z', '2026-08-26T00:05:00Z', 80, 2, true, 'positive', 'tier_b_monthly_elastic_net_sec_clean_v3', 'v3', 'monthly_last_session_next_open_v1', '2026-08-26T00:00:00Z', 'B');

INSERT INTO quantrade.score_predictions
  (score_snapshot_id, benchmark_ticker, horizon_sessions, predicted_benchmark_relative_return)
VALUES
  ('41111111-1111-4111-8111-111111111111', 'SPY', 20, 0.035),
  ('42222222-2222-4222-8222-222222222222', 'SPY', 20, 0.021);

INSERT INTO quantrade.feature_definitions
  (feature_key, feature_version, family, direction, display_name, description, formula, required_inputs, as_of_rule, definition_hash)
VALUES
  ('momentum_12_1', 'v3', 'momentum', 'higher_is_better', '12–1 month momentum', 'Prior-year price strength.', 'fixture', '["prices"]', 'point in time', repeat('1', 64)),
  ('trailing_volatility_60d', 'v3', 'risk', 'lower_is_better', '60-day volatility', 'Recent price variability.', 'fixture', '["prices"]', 'point in time', repeat('2', 64));

INSERT INTO quantrade.score_explanations
  (score_snapshot_id, feature_key, feature_version, definition_hash, sector_code, percentile, feature_weight, contribution)
VALUES
  ('41111111-1111-4111-8111-111111111111', 'momentum_12_1', 'v3', repeat('1', 64), 'Information Technology', 0.92, 0.60, 0.25),
  ('41111111-1111-4111-8111-111111111111', 'trailing_volatility_60d', 'v3', repeat('2', 64), 'Information Technology', 0.35, 0.40, -0.08);

INSERT INTO quantrade.paper_portfolio_runs
  (paper_portfolio_run_id, score_date, execution_date, starting_nav, ending_cash, benchmark_ticker, model_version, formation_protocol)
VALUES
  ('51111111-1111-4111-8111-111111111111', '2026-08-22', '2026-08-25', 100000, 0, 'SPY', 'tier_b_monthly_elastic_net_sec_clean_v3', 'monthly_last_session_next_open_v1');

INSERT INTO quantrade.paper_portfolio_positions (paper_portfolio_run_id, security_id, quantity)
VALUES
  ('51111111-1111-4111-8111-111111111111', '11111111-1111-4111-8111-111111111111', 219.298245614035),
  ('51111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222', 98.814229249012);

INSERT INTO quantrade.paper_portfolio_trades
  (paper_portfolio_run_id, security_id, side, quantity, execution_price, notional)
VALUES
  ('51111111-1111-4111-8111-111111111111', '11111111-1111-4111-8111-111111111111', 'buy', 219.298245614035, 228, 50000),
  ('51111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222', 'buy', 98.814229249012, 506, 50000);

INSERT INTO quantrade.paper_portfolio_outcomes
  (paper_portfolio_run_id, horizon_sessions, status, outcome_date, portfolio_return, benchmark_return, benchmark_relative_return)
VALUES
  ('51111111-1111-4111-8111-111111111111', 20, 'completed', '2026-09-22', 0.08, 0.03, 0.05);

COMMIT;
