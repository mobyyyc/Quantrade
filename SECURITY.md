# Security and local credentials

Quantrade keeps runtime credentials only in the ignored root `.env` file. Never
paste credentials into source files, issues, commits, screenshots, logs, or chat.
`.env.example` contains names and placeholders only.

## Rotation status and private-beta exception

The previously exposed Alpaca pair has been replaced, the local PostgreSQL role
password has been rotated, and neither value is present in the repository or Git
history. Provider access and database access were verified after rotation.

The replacement Alpaca pair was supplied through an assistant chat on September
9, 2026. The owner explicitly accepted that exposure for the private beta. It is
not stored in tracked files or command logs, but it must be rotated locally again
before staging, external beta access, or sharing the development environment.

To rotate the local PostgreSQL role password and update `.env` atomically without
printing the generated value:

```powershell
.\scripts\rotate-local-postgresql-password.ps1
```

Restrict and audit the local file from PowerShell:

```powershell
.\scripts\protect-local-secrets.ps1
.\scripts\audit-secrets.ps1 -History
```

The scheduled backup and update jobs read `.env` at runtime, so they do not need
to be reinstalled after rotation. Run `scripts/run-daily-update.ps1 -Describe`
to verify routing without contacting a provider or printing credentials.

## Automated enforcement

CI scans every tracked file and every reachable Git blob. It reports only the
path, line number, and rule name—never the matching value. It also rejects
private keys, non-placeholder credential assignments, credential-bearing
PostgreSQL URLs, Alpaca key-shaped identifiers, and common GitHub token formats.
