# Private-Beta Release Runbook

## Preconditions

- `DATABASE_URL`, durable raw-artifact storage, and a durable manifest
  directory are configured locally or in the release environment.
- The required database migrations are applied in order.
- The effective model card is `private_beta_approved`, its immutable approval
  decision passes every required gate, and the latest deployment cites that
  decision's exact URI and SHA-256 digest.
- The active artifact bytes, feature registry, and model version match their
  immutable registry records.
- The web application and research service use the same normalized database.

## Release gate

1. Ingest the completed market session and retain every raw artifact.
2. Run quality checks, build the point-in-time panel, and generate the dated
   score snapshots.
3. Run P7.1 monitoring with the completed session as the expected price and
   score date.
4. Stop on every critical alert. Investigate warnings through
   `RECOVERY_RUNBOOK.md` before publishing.
5. Verify the private-beta web routes show the published date, model context,
   data cutoff, uncertainty notice, and no invented fallback data.
6. Tag the release with the Git revision and retain the manifest IDs and monitor
   result.

## Rollback

Do not mutate or delete score snapshots. Roll back the web deployment or stop
the read API from selecting a faulty release, then investigate with the
recovery runbook. Publish a corrected later snapshot only after all gates pass.
