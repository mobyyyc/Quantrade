# Canonical Daily-Update Workflow

`scripts/run-daily-update.ps1` is the only supported executable boundary for a
routine daily update. It resolves the repository root, `.env` file, Python
source path, interpreter version, and canonical Python orchestrator.

All entry points must invoke that script:

| Entry point | Invocation |
| --- | --- |
| Interactive terminal | `.\scripts\run-daily-update.ps1` |
| Web button | `POST /api/v1/operations/daily-update`, which launches the script |
| Scheduler | `.\scripts\run-daily-update.ps1` from the repository root |

The script calls `quantrade_research.manual_daily_update`. That Python module
owns the PostgreSQL advisory lock, same-date idempotency, incremental market and
SEC retrieval, validation, publication, and post-publication bookkeeping.

Use `.\scripts\run-daily-update.ps1 -Describe` to inspect the resolved launch
contract without contacting providers or changing the database. A different
entry point must not invoke the Python module directly.

Identical invocations are safe to repeat. The database ledger permits one
canonical completed publication per score date. A completed date skips ingestion
and scoring but retries unfinished post-publication maintenance under the same
advisory lock. It returns `already_completed` only after maintenance is confirmed.

## Score publication versus maintenance completion

The run ledger's `completed` status means immutable scores were published. A
separate append-only `completed` event at stage `portfolio` checkpoints successful
maintenance. Legacy completed runs without this checkpoint receive one safe
maintenance pass when retried. The latest portfolio checkpoint/warning determines
whether maintenance is still pending; historical warning events are retained.

- Monthly publication examines only the immediately preceding observed regular
  SPY session. It must belong to an earlier month, and its next observed session
  must equal the execution date. Ordinary days cannot enter month-end publication.
- Existing portfolios are a no-op under a transaction-scoped per-formation lock.
- Portfolio publication, portfolio outcomes, and forward outcomes can progress
  independently. Readiness is recorded only if forward-outcome materialization
  succeeded. Partial work remains safe to repeat through existing idempotency.
- If any maintenance step or checkpoint fails, the process exits **2** and emits
  `partial_completed` plus a structured completion warning. Scores remain intact.
  Scheduler whole-run retries can now recover maintenance instead of skipping it.
- The web button displays **Scores ready · Maintenance pending**, with a retry
  instruction and a still-enabled button. Retrying does not recalculate scores.
  Operations history counts unresolved warnings after the latest success checkpoint.
- Exit **0** means completion, a fully maintained duplicate, or a non-market skip;
  ordinary pre-publication failures continue to exit nonzero.

Missing market observations are fetched on the next run, but knowledge is never
backdated. Live scores use the versioned `live_after_validation_v1` contract: the
cutoff is the actual time after ingestion and validation. A failed attempt without
immutable scores gets a fresh cutoff when retried; an existing immutable score set
keeps its original timestamp. Historical replay remains separately identified as
`historical_replay_2000_toronto_v1` with a fixed 8:00 p.m. Toronto cutoff.

Official monthly portfolios are still created only for their exact next-session
execution date. Once that window has elapsed, the formation is stored in
`missed_paper_portfolio_formations` as unavailable; later data cannot be used to
invent its holdings. Monitoring begins with the live contract's effective date,
so older historical replay dates are not retroactively labeled as operational misses.
Restart an already-running web server after code changes so it uses the new route.

P12.7 verification (September 7, 2026): 371 research tests, 12 browser tests,
lint, and production build passed. Read-only validation of the candidate query
for September 4 returned no due portfolios in approximately 0.06 seconds. The
operations-history SQL also ran successfully. Browser stream tests use fixtures;
no live daily update, new score publication, or historical basket repair was run.

## Progress contract

The Python orchestrator emits a bounded `daily_update_progress_v1` JSON-lines
contract prefixed with `QUANTRADE_PROGRESS `. It reports stage transitions for
initialization, market data, SEC filings, validation, scoring, portfolio
maintenance, and completion. Each stage reports only meaningful state changes,
not per-symbol or per-document activity.

The web route converts those lines to an `application/x-ndjson` response so the
button can show the current stage while the canonical script is still running.
Terminal and scheduled runs receive the same concise stage output. Ordinary
human-readable completion and error lines remain available for logs and failure
diagnosis. Closing the browser does not cancel the database-backed update.

## Provider retries

The orchestrator retries only idempotent provider-ingestion commands. Benchmark
and stock bars retain `--only-missing`; SEC filing discovery retains
`--incremental`. All attempts run beneath the same PostgreSQL advisory lock and
before score publication, so a partial provider response can be resumed without
creating duplicate bars, filings, facts, or scores.

Temporary network failures and HTTP 408, 425, 429, 500, 502, 503, and 504
responses receive at most three total attempts with one- and two-second waits.
Each retry emits one bounded progress event. Authentication and authorization
errors, invalid data, code failures, and a current SEC index that has not yet
been published fail immediately. Scoring and post-publication portfolio work
are not provider-retried. Windows Task Scheduler's whole-run retries remain a
separate recovery layer for failures that outlast these short attempts.

## Windows scheduling

Install or repair the Codex-independent weekday task with:

```powershell
.\scripts\install-daily-update-task.ps1
```

Run this installer once from a PowerShell window opened as Administrator.
The installed task itself runs with limited privileges under the current user.

The task runs Monday through Friday at 10:15 p.m. in the Windows `Eastern
Standard Time` zone. It starts a missed run when the machine becomes available,
requires network connectivity, ignores overlapping launches, retries a failed
process twice at ten-minute intervals, and wakes a sleeping PC when Windows
permits it.

The current Windows account must remain signed in because Quantrade's Python
launcher is installed for that user. PostgreSQL, internet access, and `.env`
credentials must be available. Codex and the web application do not need to be
open.

Remove the task with:

```powershell
.\scripts\uninstall-daily-update-task.ps1
```

Verify the installed action, principal, schedule, and safety settings with:

```powershell
.\scripts\verify-daily-update-task.ps1
```
