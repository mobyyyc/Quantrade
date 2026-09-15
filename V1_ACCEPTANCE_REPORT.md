# V1 acceptance report

**Decision:** passed for private V1 release-candidate closure

**Acceptance date:** 2026-09-14 America/Toronto

**Application source revision tested:** `5052bf9` (the acceptance-only test isolation fix and this report are committed afterward)

## Acceptance evidence

| Gate | Result | Evidence |
| --- | --- | --- |
| Migration rehearsal | Passed | All 39 ordered migrations applied to a disposable `quantdb_ci` database and created 57 Quantrade tables. The database was removed afterward. |
| Research tests | Passed | 422 Python tests passed. |
| Web lint and production build | Passed | ESLint, TypeScript, and the Next.js 16.3.1 production build completed successfully. |
| Browser and accessibility tests | Passed | 21 Playwright tests passed, including WCAG 2.2 AA automation at 1280, 390, and 320 px and the real-state UX matrix. |
| Update dry runs | Passed | The canonical terminal/web/scheduler launch boundary resolved correctly; the 2021-01-01 through 2026-06-30 historical plan resolved to 220 resumable chunks for 500 members; the read-only exact-zero audit preserved history and reported 496 of 500 live snapshots eligible. |
| Scheduled operations | Passed | Daily update and PostgreSQL backup tasks match their hidden-window, overlap, missed-run, network, and timing contracts. Neither requires Codex or the web app. |
| Backup verification | Passed | Latest 1.28 GB custom archive matched its SHA-256 metadata and exposed 402 restore entries. |
| Restore rehearsal | Passed | The verified archive restored all 57 Quantrade tables into a unique `quantrade_restore_drill_*` database. The temporary database was removed after the test. |
| Secret scan | Passed | Current tracked files and full Git history passed; `.env` is ignored, ACL-protected, and its values were not printed. |
| Artifact scan | Passed | No raw data, derived datasets, backups, logs, database dumps, model binaries, Playwright output, or generated research artifacts are tracked. The largest tracked file is the 146,572-byte lockfile. |
| Storage-retention dry run | Passed | Zero unreferenced retention candidates and zero bytes proposed for quarantine. Nothing was deleted. |
| Portfolio integrity | Passed | No critical finding. One stored legacy preview is excluded from official reads. No official monthly formation exists yet. |

## Live acceptance snapshot

- Active model: `tier_b_monthly_elastic_net_sec_clean_v3`.
- Score date inspected: 2026-09-14.
- Published snapshots: 500.
- Eligible under the exact-zero contract: 496.
- Withheld: 4, each with an explicit active-input data-quality reason.
- Existing historical scores were not mutated by the dry run.
- Daily schedule: 10:15 p.m. Toronto time with weekday and logon catch-up guards.
- Backup schedule: 9:45 p.m. Toronto time, hidden, non-overlapping, and no wake-to-run.

## Accepted limitations

- V1 is a private, workstation-hosted research application, not a public or highly available service.
- The research cohort is `sp500_current_survivors_v1`: survivorship-biased Tier B data with current static sector classifications, not verified historical S&P 500 membership.
- Scores are rankings, not expected returns, trade instructions, or guarantees of outperforming SPY.
- The active model has six registered inputs but only momentum, volatility, and liquidity have non-zero coefficients.
- The July 2025 through June 2026 holdout is consumed and cannot be reused for model selection.
- Four current companies remain withheld until their required active market-history inputs become available.
- No official monthly portfolio has formed yet. One legacy preview row remains stored for lineage but is excluded from official UI and APIs.
- The verified restore took about nine minutes for the current 1.28 GB archive; recovery time will grow with the database unless later capacity work changes the storage plan.
- Update acceptance used non-mutating contract and data-readiness dry runs. It did not contact providers or publish a second score for the already completed date.

## Reproduction

```powershell
$env:PYTHONPATH = (Resolve-Path 'services/research/src').Path
py -3.14 -m unittest discover -s services/research/tests -v
Remove-Item Env:PYTHONPATH

pnpm --filter @quantrade/web lint
pnpm test:e2e

.\scripts\run-daily-update.ps1 -Describe
.\scripts\run-historical-market-backfill.ps1 -DryRun
.\scripts\verify-daily-update-task.ps1
.\scripts\verify-postgresql-backup-task.ps1
.\scripts\verify-postgresql-backup.ps1
.\scripts\test-postgresql-restore.ps1
.\scripts\audit-secrets.ps1 -History
.\scripts\run-storage-retention.ps1
```

Migration verification must continue to use a disposable database whose name ends in `_ci`; browser tests continue to use `quantrade_e2e`.
