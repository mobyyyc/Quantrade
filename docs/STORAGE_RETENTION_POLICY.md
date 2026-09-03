# Storage retention policy

Quantrade retains evidence needed to reproduce point-in-time research. Cleanup is conservative and recoverable: the command is a dry run unless `-Apply` is supplied, and apply moves eligible items to quarantine instead of permanently deleting them.

## Indefinite retention

- PostgreSQL normalized data, raw-artifact rows, compact source receipts, retrieval events, and immutable run records.
- Every local raw artifact referenced by PostgreSQL.
- Raw run manifests, training and holdout datasets, model artifacts, decision documents, and governance evidence.
- PostgreSQL backups, which are governed separately by the tested P12.5 backup policy.
- Market reconciliation reports with actionable findings.

Compact receipts deliberately store hashes and retrieval metadata rather than repeated provider payloads. They are small provenance records and must not be pruned while normalized observations refer to them.

## Eligible for recoverable quarantine

| Storage class | Rule |
| --- | --- |
| Incomplete operational report | Older than 7 days |
| Completed SEC coverage report | Older than 365 days, while retaining at least the newest 12 |
| Completed database-storage report | Older than 365 days, while retaining at least the newest 52 |
| Local operational log | Older than 30 days |
| Unreferenced raw file | Older than 90 days; raw manifest directories are excluded |

The engine rejects paths outside the configured `data` root, refuses symbolic links, rechecks size and modification time before moving anything, and writes a recovery ledger in the quarantine directory.

## Operation

Preview only:

```powershell
.\scripts\run-storage-retention.ps1
```

Review the immutable JSON plan under `data/derived/retention-plans`. To move the same currently eligible classes into recoverable quarantine, run:

```powershell
.\scripts\run-storage-retention.ps1 -Apply
```

Permanent quarantine purging is intentionally not automated in V1. This prevents a scheduling or classification error from destroying research evidence; a future purge must be a separate, reviewed operation after at least 30 days.
