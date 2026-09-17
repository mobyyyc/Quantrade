# Quantrade Release Runbook

The current portfolio release is the annotated Git tag
`v1.0.0-portfolio.1`. Its acceptance record is
[`FINAL_PORTFOLIO_RELEASE.md`](FINAL_PORTFOLIO_RELEASE.md), and its
machine-readable freeze record is
[`releases/portfolio-v1.json`](releases/portfolio-v1.json). The earlier private
release candidate remains available as `v1.0.0-rc.1`; published tags are never
moved or reused.

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
- The release manifest's schema head, model artifact, feature registry, content
  contract, and run contracts match the environment being released.

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
6. Run `scripts/verify-final-portfolio-release.ps1` and require a passing result
   before creating a new release tag. A provider-backed daily incident must be
   recorded separately from this deterministic repository and recovery gate.
7. Commit the release freeze, create an annotated immutable tag, and push both
   the commit and tag. Never move or reuse a published release tag.

## Verify the release

From a clean checkout:

```powershell
git fetch origin --tags
git show --no-patch --decorate v1.0.0-portfolio.1
git rev-parse v1.0.0-portfolio.1^{}
git status --short
```

The displayed tag must resolve to the final portfolio-release commit, and the
worktree must be clean. Review the freeze record and verify its model and
registry hashes against the immutable database registry before running an
update. Apply all 39 migrations through
`0039_add_model_health_monitoring.sql`; migrations are forward-only and are
never reversed as part of an application rollback.

The supported routine update remains:

```powershell
.\scripts\run-daily-update.ps1
```

The terminal command, web button, and Windows scheduler all cross that same
versioned boundary. Local `.env`, databases, raw artifacts, logs, and backups
are runtime state and are intentionally absent from the Git tag.

## Rollback

Do not mutate or delete score snapshots. Stop new publications, preserve the
failed evidence, and follow the release rollback section in
`RECOVERY_RUNBOOK.md`. A code rollback does not imply a database downgrade or a
model rollback. Publish a corrected later snapshot only after all gates pass.
