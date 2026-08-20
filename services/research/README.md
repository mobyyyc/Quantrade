# Research service

The research service owns ingestion, point-in-time normalization, feature
generation, scoring, and reproducible research runs. It is deliberately
separate from the web application so research runs can be versioned and
validated independently of presentation.

## Local configuration

Copy the repository-root `.env.example` to a local `.env` and replace only the
values needed for the current task. `.env` files are ignored by Git.

- `DATABASE_URL` and `RAW_ARTIFACTS_URI` are required for database-backed or
  reproducible runtime runs.
- `SEC_USER_AGENT` identifies requests to SEC EDGAR and is not a credential.
- `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` must be configured together.
- `FRED_API_KEY` remains optional until the provider audit begins.

The settings layer never emits values for database URLs or provider keys. It
only exposes configuration-presence flags and a non-secret fingerprint.

## Run manifests

Every ingestion, score, or backtest run creates a `v1` manifest with its Git
revision, source inputs and raw-artifact URIs, data-capability tier,
configuration fingerprint, and—when relevant—decision timestamp. Manifests
are JSON artifacts, not environment dumps, so no credential values belong in
them.

## SEC security master

P2.1 ingests SEC's current ticker/exchange association file as a dated
snapshot. Repeated snapshots create ticker-history intervals; they do not
prove historical index membership or common-stock eligibility. SEC rows start
as `unknown` asset class until a later universe gate verifies them.

With a local PostgreSQL database and a `file://` raw-artifact location
configured, run:

```bash
python -m quantrade_research.ingest_security_master --code-revision <git-sha>
```

The command requires `SEC_USER_AGENT`, writes the raw response before
normalization, and records a completed run manifest. It only normalizes SEC
exchange labels that map unambiguously to supported MICs; all other rows remain
auditable in the raw snapshot and are reported as unmapped.

## Dated universe membership

Use a UTF-8 CSV with a `cik` column and record the source's explicit as-of
date; the importer refuses a file without CIKs. A current constituent snapshot
is not historical membership and therefore defaults to Tier B.

```bash
python -m quantrade_research.ingest_universe \
  --input path/to/constituents.csv \
  --universe-code sp500 \
  --as-of-date 2026-08-20 \
  --source-reference "source URL or record ID" \
  --code-revision <git-sha>
```

Only pass `--historical-membership-verified` after the provider audit confirms
the file's point-in-time constituent coverage. This does not on its own
upgrade the project-wide data-capability tier.

## Alpaca daily bars and corporate actions

P2.3 retrieves both raw (for next-open execution) and split-adjusted (for
price features) daily bars, plus corporate actions with `data_quality=complete`.
The adapter records retrieval time as `available_at`, preserves every response,
and remains Tier B until the documented Alpaca audit reconciles adjustments,
volume, and next-open behavior.

```bash
python -m quantrade_research.ingest_market_data \
  --symbols AAPL,MSFT \
  --start 2026-01-01 \
  --end 2026-08-20 \
  --code-revision <git-sha>
```

This requires paired local Alpaca credentials and an already-ingested security
master. The command is intentionally not a license or data-quality approval.
