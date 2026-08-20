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

## SEC filings and XBRL facts

P2.4 fetches a CIK's submissions metadata and company-facts payload, stores
both raw responses, and only keeps facts linked to an ingested filing accession.
The filing acceptance timestamp is the fact's `available_at` value; a fiscal
period end alone can never make a fact eligible for a historical decision.

```bash
python -m quantrade_research.ingest_filings \
  --cik 0000320193 \
  --code-revision <git-sha>
```

This requires the SEC user-agent, storage, database, and security-master
configuration described above.

## Data-quality gates

P2.5 supplies fail-closed checks for the next pipeline stage. A dated panel or
score cannot proceed when required daily bars are missing or duplicated, OHLCV
values are invalid, or any market or filing record has an `available_at` later
than the decision timestamp. The gate reports every issue; it does not quietly
filter records to manufacture coverage.

## Point-in-time panel

P2.6 builds a complete, dated panel from explicit universe membership, one
daily-bar basis, and required filing facts. It requires membership to be dated
no later than the requested session, runs the quality gate, and selects the
latest fact that was available by the decision timestamp. Missing facts or bars
stop the build rather than excluding securities invisibly.

## Feature registry

P3.1 records the canonical, versioned meaning of each research feature before
any calculation is implemented. A definition includes its formula, required
inputs, direction, and availability rule; its SHA-256 hash makes a model's
feature set reproducible. The database table is append-only, so a changed
definition must use a new feature version. See the repository-root
`FEATURE_DEFINITIONS.md` for the approved v1 definitions.

## Momentum and relative strength

P3.2 implements `momentum_12_1@v1` and `relative_strength_6m@v1` from
split-adjusted regular-session closes. The calculator requires 253 price
observations for 12–1 momentum and matching 127-session security/benchmark
windows for relative strength. It rejects incomplete, duplicate, non-positive,
or post-decision observations rather than quietly shortening or repairing a
window.

## Value and profitability

P3.3 calculates `earnings_yield_ttm@v1` and `return_on_assets_ttm@v1` from
eligible SEC facts. The conservative v1 definition uses one reported annual
net-income period (330–370 days); it does not reconstruct TTM income from
quarters. Earnings yield requires a positive reported shares-outstanding fact
and split-adjusted formation close. Return on assets additionally requires
positive total-assets facts at the annual period's exact start and end.

## Risk and liquidity

P3.4 calculates `trailing_volatility_60d@v1` from 60 split-adjusted daily log
returns (61 closes) using sample standard deviation and `sqrt(252)`
annualization. `median_dollar_volume_20d@v1` takes the median of unadjusted
close multiplied by volume across 20 completed sessions. Both calculations are
fail-closed on incomplete, duplicate, unavailable, or invalid observations.

## Feature diagnostics

P3.5 reports feature coverage, missingness reasons, paired cross-sectional
correlations, and direction-aware top-bucket turnover. It requires an explicit
outcome for every requested security-feature pair: either a value tied to its
definition hash or an unavailable reason. Correlations with fewer than two
pairs or zero variance are reported as unavailable, never substituted.

## Sector-aware feature ranks

P4.1 converts explicit feature outcomes into tie-aware 0–1 percentiles inside
dated sector cohorts. Every rank is oriented so higher means better, including
inversion of lower-is-better features. Sector labels must be available by the
decision timestamp, and sectors with fewer than two available peers produce an
explicit unavailable rank instead of a cross-sector fallback.
