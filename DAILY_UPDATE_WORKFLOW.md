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
canonical completed publication per score date, and a completed date returns
`already_completed` without creating duplicate scores.

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
