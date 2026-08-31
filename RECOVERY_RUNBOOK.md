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

## Score-anomaly review

For an eligible-count drop above 30% or a mean-score shift above 20 points,
compare the current and prior universe, source coverage, feature availability,
model version, feature version, and data cutoff. Publish only after the change
is explained and recorded. Do not change thresholds or exclude names merely to
make the monitor pass.
