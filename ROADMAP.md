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
- P6.5: add uncertainty, accessibility, and disclaimer reviews.

## Phase 7: operations and expansion

- P7.1: monitor data freshness, failures, and score anomalies.
- P7.2: write recovery and release runbooks.
- P7.3: add private watchlists and paper portfolio only after V1 stability.
- P7.4: research sentiment or paid data as isolated, gated additions.
