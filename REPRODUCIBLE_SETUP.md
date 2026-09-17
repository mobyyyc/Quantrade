# Reproducible local setup

Quantrade has two deliberately separate local paths:

- **Synthetic demo:** deterministic generated research values, no provider credentials, no private database, and no redistributed market documents.
- **Private research:** the owner-operated workflow configured through `.env`; this path may contact SEC EDGAR and Alpaca and is not required to review the repository.

The synthetic path is the supported path for an independent reviewer.

## Prerequisites

- Windows 10 or 11 with PowerShell 7
- Git
- Node.js 22 with Corepack
- Python 3.14 through the Windows `py` launcher
- PostgreSQL 18 running locally, with a local role that can create databases

The versions match the repository CI contract. No paid service is needed.

## First setup

From a clean clone:

```powershell
Copy-Item .env.demo.example .env.demo
```

Edit only the password in `.env.demo` so its `DATABASE_URL` can reach the local PostgreSQL server. Leave the database name as `quantrade_demo`, then run:

```powershell
.\scripts\bootstrap-demo.ps1
```

The bootstrap installs dependencies from the committed lockfiles, installs the research package, applies all ordered migrations to a newly reset `quantrade_demo` database, and loads the deterministic fixture. The reset is guarded: only a local PostgreSQL server and a lowercase database ending in `_demo` are accepted.

## Start the demo

```powershell
.\scripts\run-demo.ps1 -SkipSetup
```

Open `http://localhost:3000`. On first use, create a local owner account with any valid email-shaped value and a password of at least 12 characters. The account stays only in `quantrade_demo`.

The app displays a persistent **Synthetic demo** label. Market values, filings, scores, explanations, and portfolio outcomes are generated fixtures. Public issuer labels are used only to exercise navigation. No provider documents or private research data are included. The provider-backed daily-update button and API launch are disabled in this mode.

Omit `-SkipSetup` when you want `run-demo.ps1` to reset the database to the same fixture before starting. Resetting removes demo accounts and any other local changes in `quantrade_demo`; it never targets `quantdb`.

## Read-only daily-update rehearsal

The canonical command supports a representative dry run against the fixture:

```powershell
.\scripts\run-daily-update.ps1 -EnvFile .env.demo -DryRun -ScoreDate 2026-08-28
```

This resolves the cohort, current model, market catch-up boundary, SEC index boundary, and workflow stages. Its result explicitly reports zero network requests and zero database writes. It does not require `RAW_ARTIFACTS_URI`, SEC identity, or Alpaca credentials.

## Full verification

Install the local Chromium test runtime once, then run the complete reproduction gate:

```powershell
corepack pnpm --filter @quantrade/web exec playwright install chromium
.\scripts\verify-reproducible-setup.ps1
```

The gate resets and verifies the synthetic database, runs the read-only update rehearsal, runs all research tests, lints and builds the web app, and executes the isolated browser and accessibility suite. Browser tests use a separate `quantrade_e2e` database.

## Fixture contract

The fixture is versioned as `quantrade_synthetic_demo_v1` and currently lives at `apps/web/e2e/seed.sql` so browser tests and the reviewer demo exercise the same state. Setup reports its SHA-256, migration count, schema-table count, security count, score count, and artifact-reference count. Its `memory://e2e/` provenance entries are metadata-only placeholders, not downloaded source files.

The fixture includes completed, skipped, stale, ranking, stock-evidence, watchlist, model-health, and monthly-portfolio states needed by the product walkthrough. It is not evidence of investment performance.

## Private research path

Private operation continues to use `.env.example`, the canonical scripts, and the runbooks already in this repository. Never copy real credentials into `.env.demo`, commit either environment file, or use the demo setup script against the private database.
