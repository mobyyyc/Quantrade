# PostgreSQL Backup and Restore Runbook

## Operating contract

Quantrade creates one PostgreSQL custom-format logical backup every day at
1:30 a.m. Toronto time. The Windows task invokes
`scripts/backup-postgresql.ps1`; Codex and the web application are not required.
The current Windows user must be signed in and the PostgreSQL service must be
running.

Archives are written to `data/backups/postgresql`, which is excluded from Git.
Each successful backup has a `.dump` archive and `.dump.json` metadata sidecar
containing its SHA-256 checksum, byte count, PostgreSQL version, and restore
catalog entry count. Passwords and provider credentials are never written to
the archive metadata or process arguments.

The default retention policy removes archives older than 30 days only after a
new archive passes validation. It always preserves at least the seven newest
archives. A failed or partial backup never triggers retention and its `.partial`
file is removed.

## Routine commands

Create and validate a backup immediately:

```powershell
.\scripts\backup-postgresql.ps1
```

Verify the newest archive without restoring it:

```powershell
.\scripts\verify-postgresql-backup.ps1
```

Run the complete restore drill against a disposable database:

```powershell
.\scripts\test-postgresql-restore.ps1
```

The drill verifies the checksum, restores with `--exit-on-error`, confirms that
the `quantrade` schema contains tables, and removes only a database whose name
begins with `quantrade_restore_drill_`. It never targets `quantdb`.

Install or repair the independent Windows backup schedule from an Administrator
PowerShell window:

```powershell
.\scripts\install-postgresql-backup-task.ps1
.\scripts\verify-postgresql-backup-task.ps1
```

Remove only the schedule, leaving all backup files intact:

```powershell
.\scripts\uninstall-postgresql-backup-task.ps1
```

## Production recovery

Do not restore directly over `quantdb`. Use this controlled process:

1. Stop the web application and disable the daily-update and backup tasks.
2. Preserve the damaged database and create a final backup if PostgreSQL can
   still read it.
3. Run `verify-postgresql-backup.ps1 -BackupFile <archive>` on the selected
   recovery point.
4. Create a new empty database with a distinct recovery name.
5. Restore the custom archive with PostgreSQL `pg_restore --exit-on-error
   --no-owner --no-privileges` into that new database.
6. Confirm the `quantrade` schema, table counts, latest completed research run,
   score dates, and row counts before changing any application connection.
7. Point `DATABASE_URL` to the validated recovery database, start the app, and
   run read-only checks before re-enabling scheduled writes.
8. Retain the old database until the recovery has been reviewed and recorded.

Never drop, rename, or overwrite a production database merely to make a restore
command succeed. A production cutover remains an explicitly approved recovery
action.
