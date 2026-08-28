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

## Phase 9B: monthly feature-family research reset

Phase 9B replaces ad hoc follow-on challenger search with a single
development-only research program. It does not reopen the consumed July
2025–June 2026 holdout. Its main unit is the monthly portfolio formation date;
daily training remains a documented sensitivity test only.

Phase 9B uses a lean SEC architecture. Existing canonical facts are frozen in
place and future observations are append-only. The five-minute SEC buffer is
applied by the point-in-time resolver. The project must not duplicate the full
canonical fact store; it persists only compact monthly feature values and the
lineage required to reproduce them.

- [x] P9B.1: publish a versioned protocol that fixes monthly formation at the final market session, 8:00 p.m. Toronto decision time, next-open execution, label-safe pre-July-2025 development dates, a 20-session label-overlap purge, top-20 equal weighting, and cost scenarios.
- [x] P9B.2: audit point-in-time accounting construction and availability for amendments, TTM flows, balance-sheet facts, split-adjusted share counts, and a conservative SEC publication-latency rule before adding features. See `MONTHLY_FEATURE_FAMILY_DATA_READINESS_AUDIT.md`.
- [x] P9B.2a: freeze existing canonical SEC facts at the database layer: permit inserts, reject updates/deletes, verify ingestion remains idempotent, and retire the unnecessary full-store snapshot path. The 5,000-row pilot snapshot was removed and is excluded from research inputs.
- [x] P9B.2b: implement one point-in-time SEC resolver. Legacy frozen facts use accession acceptance plus five minutes under an explicit Tier-B assumption; future observations use the later of acceptance-plus-five-minutes and actual observation time. Amendments remain separate accessions, and a later observation never rewrites an earlier decision.
- [x] P9B.2c: audit only the concepts and comparable periods needed at monthly formations for asset growth, split-reconciled net share issuance, and the two pre-registered quality alternatives. Accrual quality was selected before result inspection because its comparable-period coverage is 98.4%, versus 44.6% for direct gross profitability.
- [x] P9B.3: materialize and audit a compact monthly feature panel—not a second SEC store—for short-term reversal, asset growth, split-reconciled net share issuance, and accrual quality. The 20,500-row panel spans 41 label-safe month-ends; every value or exclusion has selected lineage, rule version, and a deterministic hash. A byte-identical replay was verified.
- [x] P9B.4: compare market-wide centered percentile inputs with the existing static-sector percentile transformation as Tier-B robustness only. Static-sector results are reported but cannot select a candidate.
- [x] P9B.5: build a versioned monthly development dataset and nested chronological out-of-fold panel. The next-open dataset contains 14,377 common-sample rows across 40 formations, gives each formation equal aggregate weight, and excludes every outcome reaching July 2025.
- [x] P9B.6: compare the fixed candidate set on the same out-of-fold panel: active elastic net, equal-weight signed family composite, ridge, low-L1 elastic net, and robust ridge-like regression. Penalties are selected inside chronological inner splits; outer training uses label-overlap purges.
- [x] P9B.7: evaluate rank IC, top-20 next-open benchmark-relative return at 5/10/25/50 bp costs, turnover, coverage, factor-sign stability, rank stability, and pre-defined SPY trend/volatility diagnostics. Every candidate rejection is recorded in `MONTHLY_FEATURE_FAMILY_DECISION.md`.
- [x] P9B.8: issue a versioned no-freeze decision. No market-wide challenger cleared every frozen gate, so the active private-beta model remains unchanged; no minimum non-zero-feature condition was imposed.

## Phase 9C: point-in-time weekly rank research

Phase 9C responds to the Phase 9B no-freeze result by correcting the label,
quarterly accounting construction, missing-data policy, ranking objective, and
effective-time validation before adding model complexity. Weekly formations
support training, but calendar months remain the independent weighting and
inference unit; the visible research basket remains monthly.

- [x] P9C.0: translate the external research report into a project-specific protocol, explicitly preserve the consumed holdout, separate deployed/reference/portfolio effects, and document the report's non-portable bibliography limitation.
- [ ] P9C.1: run the no-download data-feasibility audit for corporate-action-aware wealth labels, point-in-time quarterly/TTM SEC reconstruction, endpoint shares, historical SIC/FF12, market-feature coverage, and weekly calendar weights; then freeze admissible scope and numeric gates before inspecting outcomes.
- [ ] P9C.2: implement the deterministic stock-and-SPY wealth ledger for ordinary dividends and splits, withholding labels that cross unresolved complex actions.
- [ ] P9C.3: implement the fail-closed point-in-time standalone-quarter and true-TTM SEC engine with full selected-fact lineage and no weighted-average-share primary fallback.
- [ ] P9C.4: freeze and materialize the approved six economic families with neutral missing ranks, separately measured informative coverage, and calendar-month-normalized weekly sample weights.
- [ ] P9C.5: build the label-safe weekly development dataset and nested chronological folds; preserve July 2025–June 2026 as report-only.
- [ ] P9C.6: replay the exact deployed artifact and an active-family refit, then fit no more than the pre-registered ridge-rank, pairwise-linear, and optional low-DF additive challengers.
- [ ] P9C.7: attribute model versus portfolio effects under both exact Top 20 and Top-20-entry/Top-30-retention rules, with identical construction for every comparison.
- [ ] P9C.8: run monthly block-bootstrap, cost, turnover, stability, coverage, and regime diagnostics; issue an immutable freeze or no-freeze decision without relaxing gates.

## Phase 10: shadow confirmation and promotion

Phase 10 remains queued until Phase 9C produces a qualifying frozen challenger.
Rejected candidates do not enter shadow scoring. The next genuinely untouched
confirmation period is forward data collected after the frozen candidate, not
the consumed historical holdout.

- [ ] P10.1: score the active model and frozen challenger side by side without changing user-visible rankings.
- [ ] P10.2: materialize new 20-session forward outcomes and compare both models under identical rules.
- [ ] P10.3: promote only after ranking quality, stability, costs, coverage, and data-quality gates pass.

## Phase 11: verified historical data

- [ ] P11.1: adopt dated historical index membership, delistings, and sector classifications from an approved source.
- [ ] P11.2: build the isolated `sp500_verified_pit_v1` cohort without mixing it with Tier-B current survivors.
- [ ] P11.3: repeat development and final confirmation before any unbiased historical-performance claim.
