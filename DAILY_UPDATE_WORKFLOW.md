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
