# Quantrade Forward Roadmap

**Version:** 2026-09-10

**Stage:** functional local private beta

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

An immediate next-generation model search is **not** the efficient next phase. Repeated searches on the same history would increase multiple-testing risk without adding independent evidence. Product reliability and deployability now have more value.

One easy, valuable model-correctness change comes first: Phase 9D.1 proved that missing inputs with mathematically exact-zero coefficients can be ignored without changing any previously eligible prediction. After that, close V1 and build staging. New model research resumes after a readiness checkpoint confirms genuinely untouched evidence or materially new data.

---

## Q1 — Current-model correctness

Goal: one accurate, versioned scoring contract across batch jobs, APIs, explanations, and monitoring.

- [ ] **Q1.1 — Roll out exact-zero eligibility.** Reuse the audited implementation; require only non-zero-weight inputs; version the eligibility/display contract; preserve historical scores; prove byte-identical old eligible predictions; report newly eligible and still-excluded rows; document rollback.
- [ ] **Q1.2 — Align score evidence and metadata.** Make APIs, stock/research pages, and model cards distinguish registered, active, zero-weight, unavailable, and displayed inputs; verify score, rank, contribution, and model-version lineage end to end.
- [ ] **Q1.3 — Add model-health monitoring.** Track coverage, exclusions, missingness, drift, rank churn, and forward-outcome readiness; define warning thresholds and hash checks; do not auto-retrain or auto-promote.

**Exit:** old eligible predictions are unchanged and every score/exclusion is explained by the same contract.

---

## Q2 — V1 release-candidate closure

Goal: freeze a polished and truthful private V1 before changing its hosting model.

- [ ] **Q2.1 — Finish operational states.** Clearly represent running, retrying, complete, partial, skipped, duplicate-prevented, stale, and failed updates with useful freshness dates and safe error messages.
- [ ] **Q2.2 — Audit portfolio truthfulness.** Reconcile formation, next-open execution, holdings, realized basket/SPY results, costs, missing months, and preview data; rankings must not imply mid-month rebalancing.
- [ ] **Q2.3 — Complete the real-state UX matrix.** Test all main pages with real empty, partial, stale, failed, month-end, and long-list states; fix measured accessibility, responsive, layout, and interaction issues under the existing design system.
- [ ] **Q2.4 — Run V1 acceptance.** Run migrations, research tests, lint/build, browser tests, accessibility checks, update dry runs, backup verification, restore rehearsal, and secret/artifact scanning; record limitations.
- [ ] **Q2.5 — Cut the private V1 RC.** Freeze schema/model/feature/content/run-contract versions, update release and rollback instructions, and create a recoverable Git tag after Q2.4 passes.

**Exit:** a reproducible private V1 release candidate with accurate status, model, and portfolio communication.

---

## Q3 — Production architecture and external-use decision

Goal: decide how Quantrade can safely leave one Windows workstation before provisioning services.

- [ ] **Q3.1 — Architecture ADR.** Define Next.js web, Python worker, durable jobs, managed PostgreSQL, artifacts, scheduler, identity, and observability; compare Vercel-plus-worker with practical alternatives by failure modes, burden, and cost.
- [ ] **Q3.2 — Data-rights audit.** Confirm display, redistribution, caching, and retention rights for Alpaca and SEC-derived data. Prefer free providers; identify paid data only for a concrete unsupported need. Preserve Tier-B warnings.
- [ ] **Q3.3 — Capacity and cost budget.** Measure database, artifact, backup, request, and compute growth; estimate closed-beta costs at defined volumes and set alerts.
- [ ] **Q3.4 — Threat and privacy model.** Cover identity, authorization, secrets, watchlists, jobs, dependencies, logs, backups, abuse, retention, deletion, and recovery.
- [ ] **Q3.5 — Approve staging bill of materials.** Record services, regions, limits, expected cost, owners, and rollback. Provision nothing paid until explicitly approved.

**Exit:** one approved, costed architecture with acceptable rights and no unresolved critical threat.

---

## Q4 — Deployable platform foundation

Goal: remove workstation-only assumptions and make services independently deployable.

- [ ] **Q4.1 — Package the research worker.** Pin runtime/dependencies, define health/readiness, and make non-interactive jobs reproducible.
- [ ] **Q4.2 — Add a durable job boundary.** Replace hosted web child processes with authenticated enqueue/status APIs while preserving the canonical orchestrator, progress, locks, retries, and one-publication guarantee.
- [ ] **Q4.3 — Prepare managed PostgreSQL.** Separate migration/app/worker roles; require TLS; configure pooling, timeouts, backups, restore tests, and sanitized staging migrations.
- [ ] **Q4.4 — Add durable object storage.** Preserve immutable content hashes, provenance, compact receipts, retention, and deduplication; do not copy unnecessary unrestricted raw material.
- [ ] **Q4.5 — Adopt managed identity.** Add invitations, verified email, secure sessions, MFA/recovery, roles, isolation, and a safe local-owner migration.
- [ ] **Q4.6 — Separate config and rotate secrets.** Define local/CI/staging/production contracts, rotate exposed Alpaca credentials before staging, and verify redaction.

**Exit:** web, worker, database, identity, and artifacts deploy independently; research never runs inside a hosted web request.

---

## Q5 — Durable workflows and observability

Goal: make unattended hosted operations recoverable and understandable.

- [ ] **Q5.1 — Hosted scheduling/retries.** Schedule market-day updates, SEC catch-up, portfolio maintenance, backups, and cleanup with explicit time zones and bounded retries.
- [ ] **Q5.2 — Distributed idempotency.** Prevent concurrent workers, repeat clicks, delayed retries, and scheduler overlap from duplicating data, scores, or portfolios.
- [ ] **Q5.3 — End-to-end telemetry.** Correlate requests, jobs, provider calls, database writes, artifacts, model versions, and publication; measure latency, volume, freshness, coverage, errors, storage, and cost.
- [ ] **Q5.4 — Actionable alerts.** Alert on missed sessions, stale filings, coverage shifts, failed jobs/backups, abnormal growth, and auth abuse without noisy expected-no-op alerts.
- [ ] **Q5.5 — Recovery drills.** Test provider outage, partial jobs, worker restart, queue replay, restore, artifact recovery, secret rotation, and release rollback.

**Exit:** hosted jobs survive interruption without duplicate publication and material failures are observable and recoverable.

---

## Q6 — Staging and release gate

Goal: prove the complete hosted system before inviting users.

- [ ] **Q6.1 — Deploy isolated staging.** Provision approved services, domain/TLS, secrets, migrations, worker, scheduler, storage, and access controls.
- [ ] **Q6.2 — Seed representative states.** Use sanitized fixtures for normal, empty, stale, partial, failed, month-end, and recovery cases.
- [ ] **Q6.3 — Hosted E2E/accessibility.** Verify auth, search, rankings, stock, watchlist, research, portfolio, update status, keyboard use, charts, and responsive behavior.
- [ ] **Q6.4 — Performance/capacity validation.** Measure cold/warm latency, query plans, queue delay, worker duration, provider limits, and concurrency against budgets.
- [ ] **Q6.5 — Security/failure drills.** Verify isolation, authorization, origin checks, limits, audit logs, leak resistance, restore, and rollback.
- [ ] **Q6.6 — Staging decision.** Publish an evidence-backed `ready_for_closed_beta` or `not_ready` record.

**Exit:** staging passes functional, performance, accessibility, security, recovery, cost, and governance gates.

---

## Q7 — Closed external beta

Goal: validate the product with a small controlled audience without changing research claims.

- [ ] **Q7.1 — Onboarding/disclosures.** Explain dated research, score meaning, Tier-B limits, timing, freshness, privacy, and non-advisory boundaries.
- [ ] **Q7.2 — Feedback/analytics.** Collect only privacy-conscious signals needed for usability and reliability; document retention and opt-out.
- [ ] **Q7.3 — Invite first cohort.** Use a capped allowlist, support path, incident process, and feature flags; keep brokerage execution out of scope.
- [ ] **Q7.4 — Operate observation window.** Monitor reliability, freshness, security, comprehension, support burden, and cost.
- [ ] **Q7.5 — Resolve and decide.** Fix blockers and record whether to expand, hold, or stop.

**Exit:** closed beta is stable, understandable, supportable, and within cost/risk budgets.

---

## Q8 — Next-generation model program

Goal: one bounded, leakage-safe attempt to improve ranking quality. It may begin after Q6 if Q8.1 passes and must not block reliability work.

- [ ] **Q8.1 — Model-readiness checkpoint.** Inventory genuinely untouched forward outcomes, account for prior experiments, and decide whether evidence supports discovery, shadow qualification, or promotion testing. Stop if there is neither independent evidence nor materially new data.
- [ ] **Q8.2 — Approve new data capability.** Prefer free point-in-time data. If membership/delistings/sectors/licensing block the question, assess paid data and isolate `sp500_verified_pit_v1`; never mix it with Tier B.
- [ ] **Q8.3 — Outcome-blind feature feasibility.** Audit availability, timestamps, revisions, coverage, stability, redundancy, rationale, and storage before fitting; reject leakage-prone features.
- [ ] **Q8.4 — Pre-register one hypothesis.** Freeze features, transformations, model family, hyperparameter budget, chronological folds, purge/embargo, basket rules, costs, metrics, seeds, gates, and stopping rule.
- [ ] **Q8.5 — Authenticate the dataset.** Materialize decision-time rows, labels, lineage, exclusions, weights, versions, and deterministic hashes; keep the consumed holdout report-only.
- [ ] **Q8.6 — Nested chronological training.** Fit preprocessing/parameters inside training folds and compare the active model with one challenger under identical eligibility and portfolio construction.
- [ ] **Q8.7 — Frozen historical decision.** Evaluate rank IC, breadth, stability, turnover, cost-adjusted basket results, coverage, regimes, and feature behavior. Freeze only if every gate passes; otherwise record no-freeze.
- [ ] **Q8.8 — Untouched forward shadow.** Score active and frozen challenger side by side, keep rankings unchanged, collect only the preregistered evidence, and do not tune mid-window.
- [ ] **Q8.9 — Promote or retain.** Require independent confirmation, reproducible artifacts, updated model card, rollback rehearsal, and explicit approval. A rejection starts no new search without new evidence/hypothesis.

**Exit:** a demonstrably superior model is safely promoted, or the current model remains with a reproducible negative result.

---

## Q9 — Verified data and broader public expansion

Goal: remove Tier-B limitations and mature governance before any broad public-performance claim.

- [ ] **Q9.1 — Verified historical cohort.** License dated membership, delistings, identifiers, actions, and sectors; build isolated `sp500_verified_pit_v1` data and rerun the protocol.
- [ ] **Q9.2 — Independent security review.** Resolve material application, infrastructure, dependency, and privacy findings.
- [ ] **Q9.3 — Production governance.** Define incident response, access reviews, deletion, model-change approval, vendor review, audit retention, and public methodology maintenance.
- [ ] **Q9.4 — Public-launch decision.** Require verified rights, reliable operations, external security evidence, truthful performance reporting, and business/legal approval.

**Exit:** public expansion has verified data, mature operations, external security evidence, and defensible claims.

## Prohibited shortcuts

- Do not reuse the consumed July 2025–June 2026 holdout for model selection.
- Do not call the current-survivor cohort historical S&P 500 membership.
- Do not convert scores into guaranteed returns or promise SPY outperformance.
- Do not shadow/deploy rejected Phase 9B, 9C, or 9D candidates.
- Do not run long research inside a hosted web request.
- Do not copy private production data, unnecessary raw artifacts, or exposed credentials to staging.
- Do not buy data/services without an approved need and cost decision.
- Do not let model experiments block correctness, security, V1 closure, or reliability.

## Historical evidence

- Model: `MODEL_APPROVAL_REGULARIZED_LINEAR_PRIVATE_BETA.md`, `MODEL_EVALUATION_REPAIR_RESULTS.md`, `PHASE_9C_FREEZE_DECISION.md`, `PHASE_9D_READINESS_DECISION.md`.
- Eligibility: `PHASE_9D_ELIGIBILITY_AUDIT.md`.
- Operations: `DAILY_UPDATE_WORKFLOW.md`, `RECOVERY_RUNBOOK.md`, `POSTGRESQL_BACKUP_RUNBOOK.md`.
- Quality/security: `WEB_SECURITY_BOUNDARY.md`, `ACCESSIBILITY_REVIEW.md`, `docs/WEB_PERFORMANCE_PROFILE.md`.

## Next task

**Q1.1 — Roll out exact-zero eligibility**, awaiting explicit approval.
