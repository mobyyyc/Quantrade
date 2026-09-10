# Quantrade Roadmap

Each item is intended to fit a focused development session. A negative research result is complete when it is documented and reproducible.

## Approved execution order — September 7, 2026

User-approved priority override completed: **P9D.0b — leakage-safe training and
evaluation repair** ran before P12.7. The amended protocol, tested fold-local
comparison, and reproducible research-only results are recorded in
`MODEL_EVALUATION_REPAIR_RESULTS.md`. No live promotion or residual challenger
was performed. **P9D.0c** is also complete: the direct elastic-net comparison did
not support superiority, so the live model was retained. See
`ELASTIC_NET_SWAP_REVIEW.md`. P12.7–P12.9 and P15.4–P15.6 are complete. The
P9D.1 exact-zero eligibility audit also passed without changing live scoring.
**Next: P9D.2**, awaiting approval.

Prioritize operational reliability and valid model comparisons before additional
model complexity or cosmetic redesign. This sequence supersedes numerical phase
order; completed work below remains historical, not a guarantee that no follow-up
is needed. Execute one approved task per run and request approval for the next.

1. **P12.7–P12.9:** correct portfolio maintenance and missed-run reporting, reconcile decision-time rules, and align schedules with PC availability.
2. **P15.4:** verify migrations and production builds in CI.
3. **P15.5:** audit configuration and rotate exposed credentials.
4. **P9D.0a:** amend the comparison protocol before any residual fitting.
5. **P9D.1:** audit zero-weight eligibility and live/research consistency.
6. **P9D.2–P9D.4:** reuse authenticated research data, fit the bounded challenger, and record a reproducible readiness decision.
7. **P10.1–P10.3:** proceed only for a qualifying frozen challenger; retain the live model until confirmation gates pass. Forward collection must not block independent product work.
8. **P13.7:** polish operational clarity and model evidence, not a broad visual redesign.
9. **P15.6, then Phase 16:** secure the application before staging and external beta access.

The inspection found repeated post-publication portfolio warnings despite completed
score runs and no official monthly basket. It also found that the exact deployed
artifact was trained through April 2025 but replayed against earlier validation
windows: that replay is diagnostic, not an out-of-sample reference. Correct the
comparison procedure rather than discarding authenticated datasets or assuming a
challenger is superior. Preserve prior research decisions as records, the consumed
July 2025–June 2026 holdout as report-only, and Tier-B survivorship/static-sector
limitations. P11 and P14.6 remain separately gated; no paid source, model promotion,
bulk rebuild, or deployment is authorized by this roadmap update.

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
- [x] P9C.1: run the no-download data-feasibility audit for corporate-action-aware wealth labels, point-in-time quarterly/TTM SEC reconstruction, endpoint shares, historical SIC/FF12, market-feature coverage, and weekly calendar weights; then freeze admissible scope and numeric gates before inspecting outcomes. The decision restricts the common weekly start to 2022-01-07, defers historical SIC/FF12, excludes direct gross profitability from the first candidate, and authorizes the label and true-TTM foundation work only.
- [x] P9C.2: implement the deterministic stock-and-SPY wealth ledger for ordinary dividends and splits, withholding labels that cross unresolved complex actions. The implementation is append-only, reconciles completed results against provider total-return marks within 25 basis points, and records its passing audit in `PHASE_9C_WEALTH_LEDGER_DECISION.md`.
- [x] P9C.3: implement the fail-closed point-in-time standalone-quarter and true-TTM SEC engine with full selected-fact lineage and no weighted-average-share primary fallback. The 183-formation audit passed with zero lineage violations; all admitted primitives exceeded both frozen coverage gates, and endpoint-only shares never fall back to period averages. See `PHASE_9C_ACCOUNTING_ENGINE_DECISION.md`.
- [x] P9C.4: freeze and materialize the approved six economic families with neutral missing ranks, separately measured informative coverage, and calendar-month-normalized weekly sample weights. The 91,500-row panel passed every frozen coverage, lineage, deterministic-replay, calendar-weight, and within-family redundancy gate without reading the consumed holdout. See `PHASE_9C_FEATURE_FAMILY_DECISION.md`.
- [x] P9C.5: build the label-safe weekly development dataset and nested chronological folds; preserve July 2025–June 2026 as report-only. The 82,551-row dataset spans 172 retained weekly formations, has complete serialized label lineage, gives each represented calendar month aggregate weight one, and passes all four outer plus twelve inner actual-outcome purge audits with zero overlap violations. Five windows crossing an incomplete 2022-03-08 provider session were excluded in full. See `PHASE_9C_MODEL_DATASET_DECISION.md`.
- [x] P9C.6: replay the exact deployed artifact and an active-family refit, then fit no more than the pre-registered ridge-rank, pairwise-linear, and optional low-DF additive challengers. See `PHASE_9C_MODEL_COMPARISON_DECISION.md`.
- [x] P9C.7: attribute model versus portfolio effects under both exact Top 20 and Top-20-entry/Top-30-retention rules, with identical construction for every comparison. See `PHASE_9C_PORTFOLIO_ATTRIBUTION_DECISION.md`.
- [x] P9C.8: run monthly block-bootstrap, cost, turnover, stability, coverage, and regime diagnostics; issue an immutable freeze or no-freeze decision without relaxing gates. Neither registered challenger cleared all hard gates, so the immutable result is no-freeze and the deployed active model remains unchanged. See `PHASE_9C_FREEZE_DECISION.md`.

## Phase 9D: anchored accounting residual research

Phase 9D is a result-informed successor to the Phase 9C no-freeze decision. It
permits only a small accounting residual correction. Fitting is paused until
P9D.0a freezes a superseding protocol with fold-local anchors; the final deployed
artifact is retained as a diagnostic replay, not an out-of-sample benchmark.
Historical results can qualify a candidate for forward shadow collection, but
cannot independently confirm or promote it.

- [x] P9D.0: diagnose the Phase 9C failures and preregister one anchored two-family residual-ridge challenger, including the exact bootstrap seed, tightened turnover and stability gates, and the boundary that reused development history cannot count as independent confirmation. See `PHASE_9D_FAILURE_REVIEW.md` and `PHASE_9D_STABILITY_PROTOCOL.md`.
- [x] P9D.0a: freeze the versioned amendment in `MODEL_EVALUATION_REPAIR_PROTOCOL.md` before corrected fitting: fold-local reference fitting and preprocessing, earlier-only parameter selection, exact final-artifact replay as diagnostic only, and chronological cross-fitted residuals required for the later challenger. Preserve earlier records and gates; do not reopen the consumed holdout. Residual implementation remains P9D.2–P9D.3.
- [x] P9D.0b: repair and run the historical training/evaluation comparison under the amended protocol. The original monthly elastic-net family and existing weekly six-family ridge were compared on 44,230 paired outer rows; two runs reproduced prediction and fit hashes, with 361 tests passing. See `MODEL_EVALUATION_REPAIR_RESULTS.md`. No live deployment or independent-confirmation claim.
- [x] P9D.0c: test the new elastic-net regularization against the deployed recipe on 10,012 identical month-end validation rows with actual-outcome purges. Both parameter sources reproduced; the new setting had weaker ranking and basket diagnostics. No swap; existing model, scores, and history retained. See `ELASTIC_NET_SWAP_REVIEW.md`.
- [x] P9D.1: implement and audit eligibility that ignores only mathematically exact-zero coefficient inputs. The authenticated 91,500-row weekly replay raised research-anchor coverage from 90.28% to 97.70% (95.6% minimum formation), admitted 6,783 rows solely because exact-zero inputs were absent, and preserved byte-identical raw predictions for all 82,609 previously eligible rows. Display-score, rank, and explanation-universe changes are versioned separately; P12.8 decision-time contracts are explicit and share one eligibility implementation. Live scoring remains in legacy all-input mode pending separate approval. See `PHASE_9D_ELIGIBILITY_AUDIT.md`.
- [ ] P9D.2: materialize the authenticated anchored-residual dataset on the existing Phase 9C folds under the amended protocol, using chronological cross-fitted training anchors and complete lineage without reading the consumed holdout. Reuse validated features and labels; regenerate only affected derived artifacts, not the raw SEC store.
- [ ] P9D.3: fit the three registered ridge penalties inside nested chronological folds and write deterministic outer predictions without model expansion.
- [ ] P9D.4: run identical-construction portfolio attribution and every frozen readiness gate; issue either `freeze_for_forward_shadow` or `no-freeze`.

## Phase 10: shadow confirmation and promotion

Phase 10 remains queued until the latest preregistered research phase produces
a qualifying challenger frozen for forward shadow. Rejected candidates do not
enter shadow scoring. The next genuinely untouched confirmation period is
forward data collected after the frozen candidate, not the consumed historical
holdout.

- [ ] P10.1: score the active model and frozen challenger side by side without changing user-visible rankings.
- [ ] P10.2: materialize new 20-session forward outcomes and compare both models under identical rules.
- [ ] P10.3: promote only after ranking quality, stability, costs, coverage, and data-quality gates pass.

## Phase 11: verified historical data

- [ ] P11.1: adopt dated historical index membership, delistings, and sector classifications from an approved source.
- [ ] P11.2: build the isolated `sp500_verified_pit_v1` cohort without mixing it with Tier-B current survivors.
- [ ] P11.3: repeat development and final confirmation before any unbiased historical-performance claim.

## Phase 12: operational reliability

Phase 12 makes the existing private-beta workflow dependable before additional
product expansion. Model research can continue independently, but it must not
be required for daily operations.

- [x] P12.1: audit the web button, PowerShell command, and scheduled entry point; consolidate them behind `scripts/run-daily-update.ps1`, document the resolved execution contract, and verify that all launch paths reach the same locked, idempotent Python orchestrator.
- [x] P12.2: replace Codex-dependent scheduling with a verified Windows Task Scheduler job that invokes the canonical script on weekdays at 10:15 p.m. Toronto time; require only a powered-on PC with the current Windows user signed in, PostgreSQL, internet access, and configured credentials.
- [x] P12.3: expose structured progress for market data, SEC retrieval, validation, scoring, portfolio publication, and completion without excessive console or UI updates.
- [x] P12.4: add bounded retries for temporary provider failures while preserving idempotency and duplicate prevention.
- [x] P12.5: implement automated PostgreSQL backups, retention rules, and a tested restore procedure.
- [x] P12.6: add a concise operations-history view for successful, skipped, failed, retried, and duplicate-prevented runs.
- [x] P12.7: correct monthly portfolio candidate selection and recoverable post-publication maintenance. Candidates are restricted to the prior observed session crossing a month boundary; maintenance retries under the daily lock without recalculating published scores, with durable completion checkpoints and a distinct partial-completion exit/stream state. Existing portfolios are idempotent under a formation lock. Verified with 371 research tests, 12 browser tests, lint/build, and read-only production-data SQL checks. See `DAILY_UPDATE_WORKFLOW.md`; no historical baskets or scores were rewritten.
- [x] P12.8: define and test honest missed-run recovery and a versioned decision-time contract. Historical replay retains `historical_replay_2000_toronto_v1`; approved live publication uses `live_after_validation_v1` and captures the actual post-validation timestamp. Failed pre-publication retries receive a fresh cutoff, while immutable score timestamps are preserved. Missing market observations may catch up without backfilled scores or holdings, and elapsed month-end formations are recorded immutably as unavailable rather than fabricated.
- [x] P12.9: aligned operations with the approved 9:45 p.m. daily backup and 10:15 p.m. weekday update schedule. Both installed actions are hidden and Codex-independent; backup catch-up remains safe at login; the daily task has a guarded, logged same-evening trigger that never backdates a missed score. Verified installed contract v3, exact trigger times, current-user limited principal, canonical routing, two bounded daily-update retries, missed-run settings, and no visible launcher on September 8, 2026.

## Phase 13: portfolio and research experience

Phase 13 improves how users follow validated research over time without
presenting daily rankings as trading instructions or daily portfolio changes.

- [x] P13.1: build a dedicated model-portfolio page instead of redirecting the portfolio route to the research page.
- [x] P13.2: show official current holdings, formation date, next-open execution date, weights, and the next scheduled rebalance.
- [x] P13.3: add completed official basket history with basket return, SPY return, percentage-point difference, turnover, and applicable transaction-cost assumptions.
- [x] P13.4: add daily movement context for rank and score changes plus Top-20 entries and exits, while stating that the monthly basket remains fixed.
- [x] P13.5: add private watchlist notes, optional tags, and changed-since-last-update indicators.
- [x] P13.6: add a compact daily research summary covering new scores, largest movements, research-relevant filings, portfolio status, and data-quality warnings.
- [ ] P13.7: refine targeted UX for full versus partial update completion, data freshness, missing official monthly baskets, and understandable active-model evidence. Use the existing design rules and tested operational states; do not substitute a cosmetic redesign for reliability or imply unavailable results exist.

## Phase 14: data reliability and storage

Phase 14 strengthens the existing free-data foundation without changing the
active model or weakening point-in-time rules.

- [x] P14.1: periodically reconcile Alpaca prices, splits, dividends, and missing sessions against the normalized market-data ledger.
- [x] P14.2: publish SEC coverage reports by company, accepted form, selected concept, and reporting period.
- [x] P14.3: monitor database size and per-table growth, with thresholds for unexpected expansion.
- [x] P14.4: enforce documented retention rules for manifests, compact receipts, logs, and raw artifacts. See `docs/STORAGE_RETENTION_POLICY.md`.
- [x] P14.5: define provider-failover interfaces so another market-data source can be added without rewriting normalized ingestion. See `PROVIDER_FAILOVER.md`.
- [ ] P14.6: evaluate an approved paid historical-membership source when Phase 11 is authorized; keep verified data isolated from Tier-B research.

## Phase 15: quality, performance, and security

Phase 15 prepares Quantrade to behave like a reliable beta product under
repeat use and eventual external access.

- [x] P15.1: add end-to-end tests for search, rankings, stock details, watchlists, daily updates, and official portfolio history.
- [x] P15.2: profile slow server-rendered pages and database queries; add indexes or bounded caching only where measurement justifies them. See `docs/WEB_PERFORMANCE_PROFILE.md`.
- [x] P15.3: complete an accessibility audit covering keyboard navigation, focus, contrast, chart alternatives, and screen-reader labels. See `ACCESSIBILITY_REVIEW.md` for fixes, automated coverage, and manual release checks.
- [x] P15.4: add a least-privilege GitHub Actions workflow that applies all ordered migrations to a disposable `_ci` PostgreSQL database, runs the full research suite and web lint, and produces a production Next.js build. The migration verifier rejects non-CI database names and fails on missing or malformed migration sequence numbers.
- [x] P15.5: audit secrets and configuration, rotate previously exposed provider credentials, and prevent secrets from entering source control or logs. Repository/history scanning found no real credentials in Git; local `.env` permissions are protected; PostgreSQL and Alpaca credentials were replaced and verified. The owner accepted assistant-chat exposure of the replacement Alpaca pair for private beta only, so another local-only rotation remains mandatory before staging or external access.
- [x] P15.6: add authentication, rate limiting, audit logging, and user-data isolation before external beta access. The local-first owner flow now uses scrypt password hashes, revocable opaque database sessions, fail-closed page/API guards, same-origin mutation checks, PostgreSQL-backed limits, append-only sanitized audit events, and per-user server-side watchlists. See `WEB_SECURITY_BOUNDARY.md`; managed identity and MFA remain staging requirements in Phase 16.

## Phase 16: deployment and public-beta architecture

Phase 16 moves the validated local application toward durable staging and a
controlled external beta. It does not add brokerage execution or personalized
investment advice.

- [ ] P16.1: document the deployment architecture for the Next.js frontend, Python research worker, PostgreSQL, durable artifact storage, and scheduled jobs.
- [ ] P16.2: create a staging environment with isolated credentials, storage, and database state.
- [ ] P16.3: adopt managed PostgreSQL and durable artifact storage before external access requires always-on infrastructure.
- [ ] P16.4: deploy the web application and research worker with health checks, centralized logs, and recoverable releases.
- [ ] P16.5: add onboarding, privacy documentation, methodology disclosures, and structured feedback collection.
- [ ] P16.6: run a closed external beta and resolve operational, usability, and governance findings before broader release.
