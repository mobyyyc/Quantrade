# Security and local credentials

Quantrade keeps runtime credentials only in the ignored root `.env` file. Never
paste credentials into source files, issues, commits, screenshots, logs, or chat.
`.env.example` contains names and placeholders only.

## Required one-time rotation

The current Alpaca key pair and local PostgreSQL password were previously shared
outside the local environment and must be treated as compromised even though the
repository and Git history do not contain their values.

1. In the Alpaca dashboard, create a replacement paper-account API key pair and
   revoke the previous pair.
2. Replace `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` in `.env` locally. Do not
   send the new values through chat.
3. Rotate the local PostgreSQL role password and update `.env` atomically without
   printing the generated value:

```powershell
.\scripts\rotate-local-postgresql-password.ps1
```

4. Restrict and audit the local file from PowerShell:

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
