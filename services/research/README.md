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

## Historical research foundation

The free historical lane is a fixed research cohort, not a reconstructed index.
Register it from the current 500-member `sp500` snapshot before historical
backfills begin:

```bash
python -m quantrade_research.register_historical_cohort --code-revision <git-sha>
```

It creates `sp500_current_survivors_v1`: a Tier-B, survivorship-biased cohort
with a static current sector mapping. It is useful for private model
development, but must never be called historical S&P 500 membership or used for
public performance claims. `sp500_verified_pit_v1` remains reserved for a later
licensed point-in-time membership, delisting, and sector source.

Migration `0016_add_historical_research_foundation.sql` adds content-hashed raw
documents, immutable retrieval events, availability-rule definitions, cohort
membership, resumable historical-backfill records, and training-dataset
provenance. Subsequent backfill commands must link their output to these records
and preserve source availability separately from retrieval time.

## Historical market backfill

The historical price worker is prepared, but is not run until its coverage audit
task is approved. It downloads the fixed current-survivors cohort and SPY in
quarterly, 100-symbol batches, with raw and split-adjusted bars. Every
historical session is modeled as available at **6:00 p.m. America/Toronto**,
not at its later download time.

```bash
python -m quantrade_research.historical_market_backfill \
  --start 2021-01-01 --end 2026-06-30 --dry-run
```

Remove `--dry-run` only for the approved execution task. The worker rejects
requests before 2021 because the free-provider runtime audit found incomplete
earlier history. It records completed chunks in PostgreSQL and safely skips
them on a restart; raw and split-adjusted benchmark bars for SPY use the same
availability rule.

## Historical corporate-action backfill

The separate corporate-action worker uses the same fixed Tier-B cohort and
quarterly 100-symbol batches. It preserves content-hashed provider responses,
deduplicates by provider action ID, and assigns every historical action the
conservative **6:00 p.m. America/Toronto** availability cutoff on its process
date. Provider records for symbols outside the fixed cohort are retained in
the raw response but are not mapped into the cohort's action ledger.

```bash
python -m quantrade_research.historical_corporate_action_backfill \
  --start 2021-01-01 --end 2026-06-30 --dry-run
```

Remove `--dry-run` only for an approved data run. The action ledger improves
historical execution integrity, but it does not by itself turn Tier-B results
into unbiased or total-return performance claims.

Before any raw-price execution evaluation, use the read-only coverage monitor.
It requires a completed cohort backfill, all planned chunks, a saved raw
response for every completed chunk, and action records in the requested window:

```bash
python -m quantrade_research.corporate_action_coverage \
  --start 2025-07-01 --end 2026-06-30 \
  --output data/derived/historical-coverage/corporate_actions_2025-07-01_2026-06-30.json
```

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

For the Tier-B historical research track, add `--include-history`. It follows
SEC's dated submission-history references, links every retained fact to its
filing acceptance timestamp, and preserves the raw response that supplied each
filing. The local runner below safely applies this to the registered 500-name
cohort:

```powershell
.\scripts\run-historical-sec-backfill.ps1 -SingleCompanySmokeTest
.\scripts\run-historical-sec-backfill.ps1
```

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

## Transparent composite baseline

P4.2 creates `baseline_equal_weight_v1`: the equally weighted mean of every
required sector-aware percentile rank, shown on a 0–100 presentation scale. It
records the feature-registry hash and makes a security ineligible when any
required rank is unavailable. It has no learned weights or prediction claim.

## Baseline explanations

P4.3 emits one explanation row per required feature for each baseline score:
the sector percentile, fixed equal weight, and contribution. Unavailable ranks
preserve their reason and do not receive an invented contribution. The
normalized store persists explanation rows as immutable children of score
snapshots.

## Next-open rebalance ledger

P4.4 selects exactly 20 eligible baseline scores with equal weights and creates
an execution ledger at the next regular-session open. The ledger rejects
same-close execution, missing opens, duplicate positions, short positions, or
target weights that do not total one. It first closes the prior basket, then
opens the target basket; P4.5 adds costs and liquidity constraints.

The post-close manual update creates a paper portfolio only when the prior
eligible score run's first regular-session open is present in the newly
ingested market data. It never creates missed portfolios retroactively. This
preserves the forward, no-lookahead record needed for evaluation.

Each paper portfolio is then observed only at its 5th, 20th, and 60th regular
SPY session, counting the next-open execution session as day one. Returns use
the same unadjusted prices as the execution ledger and compare the basket with
SPY bought at that same open. Missing marks or a corporate action affecting a
held company yield an immutable withheld checkpoint rather than a substitute
calculation; corporate-action-adjusted position accounting is a later task.

## Forward outcome labels

The daily update also records one immutable 5-, 20-, and 60-session label for
every eligible stock score once its future window has occurred. Each label uses
the split-adjusted close of the first regular SPY session after the score date
and the corresponding later close, alongside the same-window SPY price return.
These are future-only training and validation inputs—not model predictions and
not total-return measures. A missing mark creates a withheld label rather than
moving the window, filling a value, or introducing look-ahead data.

Use the read-only audit export to inspect exactly what an eventual ML experiment
would receive. It includes only completed labels, the immutable score snapshot
metadata, and the sector-percentile feature rows that actually formed that
dated baseline score. It does not train, select, or approve any model:

```bash
python -m quantrade_research.training_dataset --horizon-sessions 5 --output data/derived/score-labels-5d.csv
```

The CSV is intentionally long-format, one feature row per score-label example,
and its adjacent JSON file records the shared feature schema, score-date span,
and example count. `data/derived/` remains local and untracked.

## Costs, liquidity, and performance metrics

P4.5 enforces the provisional USD 10M median-dollar-volume gate for every
target, reports a 5-bps one-way cost baseline plus 1/10/20-bps sensitivities,
and calculates dated portfolio-versus-benchmark diagnostics: cumulative and
relative return, CAGR, annualized volatility, Sharpe, Sortino, maximum drawdown,
and Calmar. The results remain Tier-B research diagnostics, not performance
claims.

## Walk-forward validation

P5.1 creates chronological expanding-window plans before any model comparison.
Each validation window is strictly later than its training history, and each
later fold includes all preceding history. Duplicate dates, overlapping future
windows, and non-expanding manual plans are rejected.

## Final holdout and experiment log

P5.2 locks the completed twelve-month final holdout from 2025-07-01 through
2026-06-30 for protocol `0.1`; see `HOLDOUT_POLICY.md`. Experiment records are
append-only and may only validate data ending before 2025-07-01. Each records
the protocol, model, feature-registry hash, dates, timestamp, and result URI.

## Model approval gates

P5.3 evaluates explicit gates for point-in-time integrity, unresolved data
quality, coverage, walk-forward folds, locked-holdout performance under the
20-bps sensitivity, and data capability. Tier B may pass for private beta but
can never pass the policy for public performance claims; see
`MODEL_APPROVAL_POLICY.md`.

## Regularized linear comparisons

P5.4 permits ridge and elastic-net candidate comparisons only after the
transparent baseline has passed private-beta approval. The comparison requires
the same number of evaluation observations and reports benchmark-relative-return
and Sharpe deltas; it never promotes a candidate automatically.

## First development-only regularized experiment

The first Tier-B regularized-linear experiment uses only the exported
development partition, three chronological validation windows, and a 20-session
purge before each window. Its model card is
`MODEL_CARD_REGULARIZED_LINEAR_DEVELOPMENT.md`. The 2025-07-01 through
2026-06-30 holdout remains untouched; the pre-registered procedure for its
single future evaluation is
`HOLDOUT_EVALUATION_PLAN_REGULARIZED_LINEAR.md`.

## Model cards and rejected hypotheses

P5.5 creates immutable model-card and rejected-hypothesis governance records.
The repository includes the research-only baseline card in `MODEL_CARD_BASELINE.md`
and pre-registered prohibited methods in `REJECTED_HYPOTHESES.md`. Neither file
contains a fabricated evaluation outcome or an approval claim.

## Frozen research-model artifact

The selected development-only elastic-net candidate can be registered once as
an immutable local inference artifact. Registration records a research-only
database model card and links it to the exact experiment hash. It deliberately
does **not** replace the daily baseline model or produce a live portfolio:

```bash
python -m quantrade_research.register_research_model \
  --experiment data/derived/experiments/tier_b_regularized_linear_development_v1.json \
  --training-dataset data/derived/training/sp500_current_survivors_20d_v1.csv \
  --artifact data/derived/model-artifacts/tier_b_regularized_linear_development_v1.json
```

The next explicit model task will build a separate, dated paper-tracking path
that references this artifact. It must not silently change baseline rankings.

## End-of-day score generation

P6.1 generates score snapshots at exactly 8:00 p.m. America/Toronto from
same-date baseline scores. Eligible scores receive deterministic ranks; the
current uncalibrated V1 presentation signal remains `neutral`, while ineligible
scores remain `unavailable` with their reason. PostgreSQL uniqueness makes an
identical rerun idempotent and a changed rerun a hard conflict.
