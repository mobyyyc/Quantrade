# Recovery Runbook

## Trigger

Treat any P7.1 critical alert as a publication stop: stale market data, stale
scores, failed or unreadable manifest, or zero eligible scores. Warnings do not
block publication automatically, but require recorded review.

## Immediate response

1. Do not publish a new score run or alter an existing score snapshot.
2. Preserve the failing run manifest, raw-artifact URI, configuration
   fingerprint, Git revision, and monitor output.
3. Classify the failure: provider retrieval, raw storage, normalization,
   quality gate, panel, scoring, or deployment/read API.
4. Check the provider status and credentials without placing secrets in logs.

## Recovery

1. Correct the upstream configuration or provider issue.
2. Re-run the affected ingestion with a new manifest and preserve both
   artifacts. Never replace raw records or manifests.
3. Run the existing data-quality gate and stop if any issue remains.
4. Rebuild the dated panel and generate scores using the same decision-time
   protocol. An identical rerun is idempotent; a conflicting immutable score
   snapshot is a critical investigation, not something to overwrite.
5. Re-run operational monitoring for the completed market session.
6. Record the cause, correction, evidence, and final monitor result with the
   run artifacts.

## Database recovery

PostgreSQL backup creation, verification, isolated restore drills, retention,
and production cutover safeguards are defined in
[`POSTGRESQL_BACKUP_RUNBOOK.md`](POSTGRESQL_BACKUP_RUNBOOK.md). Always restore
into a new database and validate it before changing `DATABASE_URL`; never
overwrite `quantdb` in place.

## Release rollback

Use rollback only after identifying the exact faulty release and preserving its
logs, manifests, audit events, and database state.

1. Disable the daily-update scheduled task and do not launch the web update
   button while the incident is open. Take and verify a fresh PostgreSQL backup.
2. Fetch tags and inspect `v1.0.0-rc.1` with the verification commands in
   `RELEASE_RUNBOOK.md`. Never move or recreate the published tag.
3. Recover code in a separate clone or Git worktree at the tag. Do not use a
   destructive reset on the working repository and do not copy `.env` into Git.
4. Keep the database at its current migration level. Quantrade migrations and
   immutable research records are forward-only; an application rollback must
   remain compatible with the existing schema.
5. If database recovery is required, restore a verified backup into a new,
   isolated database, validate it, and perform a deliberate connection cutover.
   Never restore over `quantdb` in place.
6. A model rollback is a separate, append-only governance decision and
   deployment. Do not alter model cards, artifacts, approvals, deployments, or
   existing score snapshots. The eligibility override documented in
   `DAILY_UPDATE_WORKFLOW.md` applies only to future publications and records a
   distinct score protocol.
7. Re-run V1 acceptance against the recovery candidate. Re-enable scheduling
   only after the application, database, active model, artifacts, and installed
   task contracts agree.

Example isolated code recovery:

```powershell
git fetch origin --tags
git worktree add ..\quantrade-v1-rc1 v1.0.0-rc.1
```

Removing that recovery worktree later is a separate cleanup action; confirm it
contains no local evidence or configuration first.

## Score-anomaly review

For an eligible-count drop above 30% or a mean-score shift above 20 points,
compare the current and prior universe, source coverage, feature availability,
model version, feature version, and data cutoff. Publish only after the change
is explained and recorded. Do not change thresholds or exclude names merely to
make the monitor pass.
