# Quantrade Roadmap

Each item is intended to fit a focused development session. A negative research result is complete when it is documented and reproducible.

## Phase 0: charter and data decision

- [x] P0.1: record scope, audience, benchmark, target, costs, and exclusions.
- [x] P0.2: write the decision-time and next-open execution protocol.
- [x] P0.3: implement and run a free-provider audit sample.
- [x] P0.4: record source limitations and capability tier.

## Phase 1: foundations

- [x] P1.1: initialize web, research, and shared-contract boundaries.
- [x] P1.2: define data contracts for securities, prices, filings, and scores.
- [x] P1.3: create the core schema and migrations.
- [x] P1.4: add configuration, secret handling, and run manifests.

## Phase 2: point-in-time data

- [x] P2.1: ingest security master and ticker history.
- [x] P2.2: ingest a date-specific universe when the source supports it.
- [x] P2.3: ingest daily bars and corporate actions.
- [x] P2.4: ingest SEC filing metadata and facts.
- [x] P2.5: implement data-quality and as-of tests.
- [x] P2.6: build the point-in-time panel constructor.

## Phase 3: factor research

- [x] P3.1: implement the feature registry and definitions.
- [x] P3.2: add momentum and relative-strength features.
- [x] P3.3: add value and profitability features.
- [x] P3.4: add risk and liquidity features.
- [x] P3.5: report coverage, correlation, turnover, and missingness.

## Phase 4: baseline model and simulation

- [x] P4.1: create sector-aware percentile ranks.
- [x] P4.2: create a transparent composite baseline.
- [x] P4.3: persist explanation contributions.
- [x] P4.4: implement next-open rebalance ledger.
- [x] P4.5: add costs, liquidity constraints, benchmarks, and metrics.

## Phase 5: validation and governance

- [x] P5.1: implement expanding-window and walk-forward evaluation.
- [x] P5.2: lock a final holdout period and experiment log.
- [x] P5.3: define model-approval gates.
- [x] P5.4: compare regularized linear models only against the approved baseline.
- [x] P5.5: produce model cards and rejected-hypothesis records.

## Phase 6: scoring and private beta

- [x] P6.1: build idempotent end-of-day score generation.
- [x] P6.2: expose dated score, ranking, and model-card APIs.
- [x] P6.3: define product information architecture and UI content rules.
- [x] P6.4: build rankings, search, stock detail, and research dashboard.
- [x] P6.5: add uncertainty, accessibility, and disclaimer reviews.

## Phase 7: operations and expansion

- [x] P7.1: monitor data freshness, failures, and score anomalies.
- [x] P7.2: write recovery and release runbooks.
- [x] P7.3: add private watchlists and paper portfolio only after V1 stability.
- [x] P7.4: research sentiment or paid data as isolated, gated additions.

## Phase 8: current-model evidence and product alignment

- [x] P8.1: report frozen-model predictions versus actual 2025–2026 holdout outcomes without tuning.
- [x] P8.2: align the visible model basket with the documented monthly formation and next-open execution protocol.
- [x] P8.3: add development-derived prediction uncertainty and calibration context without using the consumed holdout for fitting.
- [x] P8.3a: replace user-facing basket forecasts with the preceding official basket's realized 20-session return beside SPY.
- [x] P8.4: synchronize model cards and governance records with the active private-beta deployment.

## Phase 9: next-generation model research

- [x] P9.1: pre-register ranking, spread, stability, turnover, cost, MAE, and RMSE comparison measures.
- [x] P9.2: add free-data momentum, risk, liquidity, and fundamental-change candidates behind versioned feature definitions.
- [x] P9.3: run missingness, redundancy, stability, and point-in-time diagnostics; reject weak features explicitly.
- [x] P9.4: compare robust linear, gradient-boosted, and ranking-oriented candidates on purged pre-holdout folds only.
- [x] P9.5: close the freeze gate with a versioned no-freeze decision because no challenger qualified; leave the active model unchanged.

## Phase 9A: error-led follow-on research

- [x] P9A.1: diagnose active-model errors by sector, stock-volatility regime, and point-in-time SPY trend regime on purged development folds only.
- [x] P9A.2: pre-register one targeted hypothesis from the diagnostic evidence before fitting another challenger.
- [x] P9A.3: materialize and audit the two pre-registered point-in-time SPY regime-interaction features without fitting the challenger.
- [x] P9A.4: fit and compare the single pre-registered regime-interaction challenger on the purged development folds.
- [x] P9A.5: reject the challenger or freeze it for Phase 10 using the pre-registered gates without changing the active model.

## Phase 10: shadow confirmation and promotion

Phase 10 remains queued until a future pre-registered research cycle produces a
qualifying frozen challenger. Rejected Phase 9 candidates do not enter shadow
scoring.

- [ ] P10.1: score the active model and frozen challenger side by side without changing user-visible rankings.
- [ ] P10.2: materialize new 20-session forward outcomes and compare both models under identical rules.
- [ ] P10.3: promote only after ranking quality, stability, costs, coverage, and data-quality gates pass.

## Phase 11: verified historical data

- [ ] P11.1: adopt dated historical index membership, delistings, and sector classifications from an approved source.
- [ ] P11.2: build the isolated `sp500_verified_pit_v1` cohort without mixing it with Tier-B current survivors.
- [ ] P11.3: repeat development and final confirmation before any unbiased historical-performance claim.
