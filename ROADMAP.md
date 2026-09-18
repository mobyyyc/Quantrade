# Quantrade Forward Roadmap

**Version:** 2026-09-16

**Stage:** functional local private beta; portfolio-project completion

**Authority:** this file defines future work. Completed history remains in Git and the decision documents listed below.

## Execution rules

- Execute one numbered task per approved run.
- After a detour, return to the next incomplete task here.
- Reorder, add, or remove tasks only with explicit user approval and record the change here.
- A phase is complete only when its exit criteria pass.
- Negative model results count as completed research when documented and reproducible.
- Never present research as guaranteed performance or personalized investment advice.

## Audited baseline

Quantrade currently has:

- A 500-name, explicitly Tier-B current-S&P-500-survivor cohort.
- Point-in-time-aware market and SEC data, historical datasets, daily scores, rankings, stock details, watchlists, and model portfolios.
- A locked, incremental, idempotent daily update; automated backups; and healthy hidden Windows scheduled tasks.
- Authentication, same-origin mutation protection, database rate limits, audit events, and per-user watchlists.
- Passing web lint/build and research CI coverage.
- Active private-beta model `tier_b_monthly_elastic_net_sec_clean_v3`.

The active model registers six inputs, but only momentum, volatility, and liquidity have non-zero coefficients. Phases 9B, 9C, and 9D each ended in reproducible no-freeze decisions. Phase 9D's improvement was small and uncertain and failed robustness, portfolio, turnover, and coefficient-direction gates. The July 2025–June 2026 holdout is consumed and cannot be reused for selection.

## Priority decision

Quantrade is now a **zero-additional-budget resume project**, not an active commercialization or hosted-beta program. The goal is to present the substantial system that already works: a polished local web application, reproducible point-in-time research pipeline, explainable active model, durable daily operations, and honest evaluation record.

Work now prioritizes reproducibility, maintainability, technical communication, and a convincing local demonstration. The completed architecture and data-rights work remain valuable evidence of production judgment, but they do not trigger infrastructure purchases or deployment. Paid hosting, paid data, external beta access, and broad public release are deferred unless the owner later changes the project goal and explicitly approves a budget.

An immediate next-generation model search also remains inefficient. The existing holdout has been consumed, prior challenger searches are documented, and repeated tuning on the same history would add multiple-testing risk rather than credible evidence. The active model remains frozen while new forward outcomes accumulate through the existing no-cost local workflow.

---

## Q1 — Current-model correctness

Goal: one accurate, versioned scoring contract across batch jobs, APIs, explanations, and monitoring.

- [x] **Q1.1 — Roll out exact-zero eligibility.** Future live scores use the exact-zero contract and a distinct snapshot protocol; historical replay remains legacy, completed dates are not rewritten, rollback is future-only, and the September 10 dry run raised eligibility from 462 to 495 while recording all five remaining exclusions. See `CURRENT_MODEL_ELIGIBILITY_ROLLOUT.md`.
- [x] **Q1.2 — Align score evidence and metadata.** Immutable artifact-backed input contracts now distinguish registered, active, zero-weight, unavailable, required-at-publication, and displayed inputs across APIs and UI; dated score responses carry score, rank, explanations, model version, protocol, feature versions, definition hashes, and the matching model card together. See `CURRENT_MODEL_ELIGIBILITY_ROLLOUT.md`.
- [x] **Q1.3 — Add model-health monitoring.** Immutable post-publication snapshots now track coverage, grouped exclusions, active-feature missingness and PSI drift, rank churn, same-date forward-outcome readiness, and artifact/registry/explanation integrity. Deterministic hashes and database mutation guards fail closed; alerts remain diagnostic and cannot retrain or promote a model. See `MODEL_HEALTH_MONITORING.md`.

**Exit:** old eligible predictions are unchanged and every score/exclusion is explained by the same contract.

---

## Q2 — V1 release-candidate closure

Goal: freeze a polished and truthful private V1 before changing its hosting model.

- [x] **Q2.1 — Finish operational states.** The web now derives running, provider-retrying, complete, partial, skipped, duplicate-prevented, and failed states from the durable run ledger and append-only events. Publication freshness separately identifies aligned, stale, misaligned, and unavailable evidence with score, market, SPY, SEC, and event dates. Streamed button outcomes use the same vocabulary, raw failures stay private, and the displayed schedule matches the installed 10:15 p.m. Toronto task. See `DAILY_UPDATE_WORKFLOW.md`.
- [x] **Q2.2 — Audit portfolio truthfulness.** Formation now follows the dated month-end model; next-open simulation language, exact holdings, complete/pending/withheld/missed history, gross and 25 bp turnover-adjusted comparisons, and legacy-preview exclusion are reconciled by a read-only integrity audit. See `PORTFOLIO_TRUTHFULNESS_AUDIT.md`.
- [x] **Q2.3 — Complete the real-state UX matrix.** Test all main pages with real empty, partial, stale, failed, month-end, and long-list states; fix measured accessibility, responsive, layout, and interaction issues under the existing design system. Completed 2026-09-14; see `REAL_STATE_UX_MATRIX.md`.
- [x] **Q2.4 — Run V1 acceptance.** Migrations, 422 research tests, lint/build, 21 browser and accessibility tests, update dry runs, both schedules, backup verification, a full isolated restore, secret/history scanning, artifact hygiene, retention, and portfolio integrity passed on 2026-09-14. Accepted limitations are recorded in `V1_ACCEPTANCE_REPORT.md`.
- [x] **Q2.5 — Cut the private V1 RC.** Schema/model/feature/content/run-contract versions are frozen in `releases/private-v1-rc1.json`; release verification and non-destructive rollback are documented, and the recoverable annotated tag is `v1.0.0-rc.1`.

**Exit:** a reproducible private V1 release candidate with accurate status, model, and portfolio communication.

---

## Q3 — Portfolio-project completion

Goal: turn the working private V1 into a reproducible, technically credible portfolio artifact without buying infrastructure or data.

- [x] **Q3.1 — Architecture ADR.** Accepted a Render-centered Ohio staging architecture with separate Next.js web and Python worker services, PostgreSQL-backed durable jobs, managed PostgreSQL, R2 artifacts, Clerk identity, and OpenTelemetry/Sentry observability. Vercel-plus-worker, Vercel Services/Workflow, Railway, and a VPS were compared by failure modes, burden, and directional cost in `docs/adr/0001-production-architecture.md`; no resource was provisioned.
- [x] **Q3.2 — Data-rights audit.** SEC reuse is permitted subject to fair-access controls, while private Alpaca research may continue but hosted storage and any third-party display of market data or derived outputs remain blocked pending explicit written rights. The exact external-use questions, data classes, fail-closed gates, adjacent cohort-source gap, and Tier-B limits are recorded in `DATA_RIGHTS_AUDIT.md`; no paid provider was selected.
- [x] **Q3.3 — Bound the local operating footprint.** The read-only `quantrade_local_capacity_v1` check now measures database, retained data, backup steady state/freshness, legacy content-addressed copies, and drive headroom against explicit warning/critical thresholds. The measured 11.24 GiB database, 28.97 GiB retained repository data, 48.45-second median update, compact-request profile, 228.45 GiB free space, deduplication limits, retention dry run, and multi-year no-cost runway are recorded in `LOCAL_OPERATING_FOOTPRINT.md`.
- [x] **Q3.4 — Make the repository independently reproducible.** The guarded `quantrade_synthetic_demo_v1` bootstrap now installs locked dependencies, creates only a local `_demo` database, applies all 39 migrations, and loads deterministic metadata-only fixtures without provider credentials or redistributed documents. Demo mode is visibly labeled, isolates old browser watchlists, and blocks provider launches in both UI and API. A canonical read-only update rehearsal reports zero network requests and writes; 432 research tests, lint/build, 21 browser/accessibility tests, and a clean live-browser check passed. See `REPRODUCIBLE_SETUP.md`.
- [x] **Q3.5 — Publish the technical case study.** Reworked the repository entry point and architecture guide around the implemented local system, point-in-time lineage, incremental/idempotent updates, active-model training and evaluation, preserved negative experiments, measured operating evidence, exact synthetic-demo commands, and an explicit implemented-versus-proposed deployment boundary. See `TECHNICAL_CASE_STUDY.md`.
- [x] **Q3.6 — Prepare the portfolio demo package (owner-supplied).** No repository work was needed: the owner confirmed that the screenshots, recording material, and portfolio presentation package already exist and explicitly chose to skip duplicate preparation. The repository's deterministic demo and technical case study remain the canonical supporting evidence.
- [x] **Q3.7 — Cut the final portfolio release.** The independent reproduction suite, 433 research tests, lint/build, 21 browser/accessibility tests, full-history secret scan, artifact-hygiene and documentation-link audits, schedule checks, verified backup, full isolated restore, and capacity gate passed on 2026-09-16. The frozen contract and known limitations are recorded in `FINAL_PORTFOLIO_RELEASE.md` and `releases/portfolio-v1.json`; the recoverable annotated tag is `v1.0.0-portfolio.1`.

**Exit:** a reviewer can understand, run, inspect, and discuss Quantrade from the repository and local demo without paid infrastructure, private data leakage, or exaggerated claims.

---

## Q4 — No-cost local maintenance

Goal: keep the completed project healthy and continue collecting genuinely new evidence without turning maintenance into another development program.

- [x] **Q4.1 — Operate the existing daily workflow.** The September 16 failure was traced to a late SEC daily-index publication rather than scoring, storage, or request identity. Current-evening SEC 403/404 responses are now classified accurately, and the installed `windows_daily_update_task_v4` contract adds an explicit idempotent 11:00 p.m. retry after the 10:15 p.m. primary run. Point-in-time integrity remains fail-closed: September 16 stays a recorded miss rather than being backdated with later information. The hidden limited-privilege task, overlap guard, network requirement, logon catch-up, wake setting, canonical launch boundary, and provider access were verified on 2026-09-17.
- [ ] **Q4.2 — Accumulate forward model evidence.** Preserve immutable daily scores and completed 20-session outcomes, then publish a periodic report of coverage, drift, rank stability, and basket-versus-SPY results. Do not tune the model from this stream before a new experiment is approved.
- [ ] **Q4.3 — Perform bounded maintenance reviews.** On a quarterly or release-triggered cadence, review dependencies, restoreability, credentials, disk growth, provider changes, and test health. Prefer small fixes over new platform features.

**Exit:** the local application remains recoverable, current, and capable of producing untouched forward evidence at no additional service cost.

---

## Q5 — Optional next-model research (deferred)

Goal: attempt another model only when the evidence can support a credible conclusion, using the existing free data path.

- [ ] **Q5.1 — Pass a model-readiness checkpoint.** Inventory genuinely untouched forward outcomes and any materially new free features or corrected data. Stop if the only option is to search the already-consumed evidence again.
- [ ] **Q5.2 — Pre-register one bounded challenger.** Freeze the hypothesis, features, transformations, chronological folds, purge/embargo, costs, metrics, coefficient expectations, and stopping rule before observing test results.
- [ ] **Q5.3 — Train and compare reproducibly.** Authenticate the point-in-time dataset, fit inside development folds, and compare one challenger with the active model under identical eligibility and portfolio construction.
- [ ] **Q5.4 — Shadow or retain.** A passing challenger first runs on untouched forward observations without changing displayed rankings. Promote only after independent confirmation; otherwise preserve the negative result and retain the active model.

**Exit:** the current model remains, or one demonstrably better no-cost challenger is promoted without reusing consumed evidence for selection.

---

## Q6 — Optional hosted product (deferred and unfunded)

Goal: preserve a responsible path to a real product without treating it as active portfolio work.

- [ ] **Q6.1 — Reauthorize the product goal.** Define the intended audience, operating period, support commitment, acceptable monthly budget, and success/stop criteria.
- [ ] **Q6.2 — Clear data rights.** Obtain written market-data display, derived-use, cloud-storage, retention, and cohort-source rights. Do not infer permission from private API access.
- [ ] **Q6.3 — Revalidate the architecture and threat model.** Revisit the existing ADR against current pricing and requirements, then cover identity, authorization, secrets, jobs, logs, backups, abuse, privacy, deletion, and recovery.
- [ ] **Q6.4 — Build and prove staging.** Only after explicit budget approval, add managed identity, durable jobs, managed storage/database, observability, security drills, and hosted end-to-end testing.
- [ ] **Q6.5 — Decide on external beta.** Invite nobody until rights, cost, reliability, security, truthful disclosures, and rollback all pass.

**Exit:** an explicitly funded and rights-cleared hosted product is approved—or the local portfolio project remains the final scope.

---

## Prohibited shortcuts

- Do not reuse the consumed July 2025–June 2026 holdout for model selection.
- Do not call the current-survivor cohort historical S&P 500 membership.
- Do not convert scores into guaranteed returns or promise SPY outperformance.
- Do not shadow/deploy rejected Phase 9B, 9C, or 9D candidates.
- Do not buy data, hosting, identity, storage, monitoring, or other services under the current portfolio-project scope.
- Do not publish restricted raw market data, private database contents, unnecessary artifacts, or credentials in the repository or demo media.
- Do not treat proposed production architecture as implemented behavior.
- Do not let model experiments or speculative platform work displace reproducibility, documentation, demo quality, or local reliability.

## Historical evidence

- Model: `MODEL_APPROVAL_REGULARIZED_LINEAR_PRIVATE_BETA.md`, `MODEL_EVALUATION_REPAIR_RESULTS.md`, `PHASE_9C_FREEZE_DECISION.md`, `PHASE_9D_READINESS_DECISION.md`.
- Eligibility: `PHASE_9D_ELIGIBILITY_AUDIT.md`.
- Operations: `DAILY_UPDATE_WORKFLOW.md`, `RECOVERY_RUNBOOK.md`, `POSTGRESQL_BACKUP_RUNBOOK.md`.
- Quality/security: `WEB_SECURITY_BOUNDARY.md`, `ACCESSIBILITY_REVIEW.md`, `docs/WEB_PERFORMANCE_PROFILE.md`.

## Next task

**Q4.2 — Accumulate forward model evidence**, awaiting explicit approval.
