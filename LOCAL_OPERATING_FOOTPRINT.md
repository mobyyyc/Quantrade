# Quantrade Local Operating Footprint

**Measured:** 2026-09-16, America/Toronto  
**Scope:** zero-additional-budget portfolio-project operation on the current Windows workstation  
**Status:** healthy

## Decision

Quantrade can continue its current private daily workflow on the existing D:
drive without buying storage or infrastructure. The current retained-data
footprint is 28.97 GiB outside PostgreSQL, PostgreSQL is 11.24 GiB, and the drive
has 228.45 GiB free. The 30-day backup policy is the largest continuing storage
consumer but remains affordable on the existing disk.

No retention policy, backup schedule, provider plan, or data history was changed
by this audit. The new read-only capacity command makes the limits repeatable and
fails closed when requested.

## Measured inventory

| Component | Current size | Files/rows | Notes |
|---|---:|---:|---|
| PostgreSQL `quantdb` | 11.24 GiB | See table inventory below | Grew 21.34 MiB across the 13.32-day verified observation window |
| `data/raw` | 7.76 GiB | 10,365 files | Primarily historical source artifacts; current compact ingestion does not retain response payloads |
| `data/derived` | 0.91 GiB | 140 files | Datasets, models, reports, and immutable manifests |
| `data/backups` | 20.30 GiB | 17 dumps plus metadata | Each current compressed logical dump is about 1.19 GiB |
| `data/logs` | 0.03 MiB | 2 files | Operational logs are negligible |
| Total retained repository data | 28.97 GiB | 10,542 files | Excludes PostgreSQL itself, build caches, and dependencies |
| Next.js `.next` cache | 0.93 GiB | 2,384 files | Rebuildable and excluded from retention/runway calculations |
| Root `node_modules` | 0.41 GiB | 21,683 files | Reinstallable and excluded from retention/runway calculations |

D: is 554.98 GiB total with 228.45 GiB free (41.16%). After the backup set
reaches its conservative 31-copy projection, estimated free space is still
211.73 GiB (38.15%).

## Database concentration

The database is intentionally dominated by reproducible historical research:

| Relation | Allocated size | Purpose |
|---|---:|---|
| `filing_facts` | 8.13 GiB | Point-in-time SEC facts and indexes |
| `score_explanations` | 1.64 GiB | Immutable feature-level evidence for historical scores |
| `daily_price_bars` | 0.56 GiB | Equity OHLCV history |
| `score_snapshots` | 0.48 GiB | Dated published ranks and scores |
| `forward_score_outcomes` | 0.31 GiB | Completed forward evaluation outcomes |

Exact audit counts were 21,121,729 filing facts, 1,537,220 equity bars, 3,128
SPY bars, 215,628 relevant filings, 697,000 score snapshots, 4,159,500 score
explanations, 887 compact source receipts, and 1,035 receipt retrieval events.

The database monitor classified the 22,380,544-byte increase since the prior
verified snapshot as normal. The observed 1.60 MiB/day database rate is useful
for monitoring, not a long-term prediction; it covers only 13.32 days.

## Daily operating cost

For September 1–15, the canonical ledger records ten completed runs, one expected
skip, and no failed terminal run. Completed updates had:

- 48.45-second median duration;
- 97.31-second p95 duration; and
- 127.58-second maximum duration.

Across active ingestion days, compact receipt history observed a median of 65
provider retrievals per day, a 65.4 mean, and a 90 maximum. The provider means
were 22.6 Alpaca retrievals and 42.7 SEC retrievals per active day. Represented
response bodies averaged about 19.5 MB/day, but every current compact receipt has
`payload_retained=false`; normalized rows and small provenance records, not those
response bodies, form the daily storage growth.

These counts are well inside the configured provider request budgets. They are
observations, not a promise that future filing-heavy days will have the same
shape.

## Backup steady state

The scheduled policy retains at least seven backups and otherwise keeps 30 days.
At one backup per day, the conservative projection is 31 copies. Using the
current median dump size:

- current backup set: 20.30 GiB;
- projected steady state: 37.01 GiB;
- additional space before steady state: 16.71 GiB; and
- observed per-copy size growth: about 0.24 MiB/day.

The 30-day policy therefore remains safe. Reducing it would save local disk but
is unnecessary now and would weaken recovery history. Reconsider only if the
capacity command warns or the project is intentionally archived.

## Deduplication and retention findings

Current ingestion is storage-efficient:

- `source_receipts` are unique by provider, source reference, content hash, and
  parser version;
- all 887 current compact receipts retain metadata only;
- `raw_documents` deduplicate immutable lineage by provider and content hash;
- normalized observations use database uniqueness constraints; and
- the retention dry run found zero eligible items and zero bytes on this date.

The historical artifact store predates compact receipts. Filename hashes reveal
1,027 repeated content groups, 2,472 extra physical files, and 4.51 GiB of
duplicate physical bytes. Database lineage already identifies a canonical
document, but older `raw_artifacts` rows still reference these copies, so the
conservative retention engine correctly refuses to remove them.

This is accepted one-time legacy overhead, not evidence of current daily payload
duplication. Do not delete or hard-link these files manually. A future reclamation
would require a separately tested reference migration plus restore verification;
with more than 200 GiB projected free, that risk is not justified for the resume
project.

## Encoded warning thresholds

`scripts/check-local-capacity.ps1` applies these local limits:

| Scope | Warning | Critical |
|---|---:|---:|
| D: free space | at or below 100 GiB or 20% | at or below 50 GiB or 10% |
| PostgreSQL | at or above 25 GiB | at or above 40 GiB |
| Raw artifacts | at or above 12 GiB | at or above 20 GiB |
| Retained backups | at or above 45 GiB | at or above 60 GiB |
| Newest backup age | at least 36 hours | at least 72 hours or no backup |

It also projects the configured backup steady state. A projection that crosses a
drive floor produces the matching warning or critical result before the disk is
actually consumed.

Run the read-only check monthly and after a large backfill:

```powershell
.\scripts\check-local-capacity.ps1
```

Use this form in an acceptance or scheduled check when any warning should fail
the command:

```powershell
.\scripts\check-local-capacity.ps1 -FailOnWarning
```

Continue the existing immutable database-growth snapshot separately:

```powershell
.\scripts\run-database-storage-monitor.ps1 -FailOnWarning
```

Preview retention without changing files:

```powershell
.\scripts\run-storage-retention.ps1
```

## No-cost runway conclusion

The backup projection leaves 211.73 GiB free, more than twice the 100 GiB warning
floor. Even a sustained rate several times the short observed database and backup
growth would leave multiple years of local headroom. Because the observation
window is short and provider activity varies, the defensible conclusion is not a
precise exhaustion date: **the existing workstation has ample multi-year runway,
provided the monthly capacity check stays healthy and no new historical backfill
or raw-payload retention is introduced.**

No paid capacity is required for the active roadmap.
