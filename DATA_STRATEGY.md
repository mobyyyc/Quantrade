# Free-First Data Strategy

## Initial source mix

| Need | Initial source | Use in V1 | Known boundary |
|---|---|---|---|
| Company filings and XBRL facts | SEC EDGAR | Primary source for fundamentals and filing times | Normalization and point-in-time availability are our responsibility |
| Daily US equities | Alpaca Basic | Historical research and private-beta end-of-day data | Runtime audit supports the clean free-track window from Jan 2021; earlier returned bars are incomplete and excluded |
| Macro context and revisions | FRED / ALFRED | Regime research | Use vintage values for historical decisions |
| News sentiment | None in first model | Deferred research candidate | Historical timestamps, coverage, and licensing require an audit |
| Prototype fallback | Alpha Vantage | Small-sample exploration only | Free tier has 25 requests per day, unsuitable for universe-scale ingestion |

## Free-data capability tiers

### Tier A: valid private-beta product work

- Daily score pipeline and UI using current, documented data snapshots.
- SEC-based quality, value, and growth research.
- Historical studies from the available daily-price history.
- Transparent labels that clearly state the data period and limitations.

### Tier B: research, not external performance claims

- Results using a current index constituent list without historical membership.
- Results that cannot include delisted securities.
- Results using a provider's adjusted bars before its adjustment methodology is audited.

### Tier C: paid-data upgrade gate

Evaluate paid providers when the project needs one or more of:

- Historical constituent membership and delisted securities.
- Longer validated price history.
- Guaranteed corporate-action treatment and point-in-time fundamentals.
- Intraday data, exchange-grade current prices, or public display rights.

## Free historical research window

The audited, model-development window for `sp500_current_survivors_v1` begins
on **2021-01-01**. The first locked holdout remains **2025-07-01 through
2026-06-30**. Historical bars returned before 2021 were not sufficiently
continuous across both equities and SPY, so the downloader rejects requests
before this boundary for the free research track.

This is a data-quality boundary, not a claim that all current cohort companies
traded throughout that window. IPOs, symbol availability, and other missing
inputs remain explicit exclusions in the coverage report; replay and training
export must withhold those examples.

## Provider evaluation requirements

Before adopting a provider, record its plan, date accessed, license/display rights, rate limits, historical start date, price-adjustment policy, delisting treatment, constituent history, filing timestamp coverage, and a reconciliation sample.

## Data-quality policy

- Never silently fill missing critical fundamentals.
- Store raw payloads and source metadata before normalization.
- Reconcile a sample of prices, splits, dividends, and filing dates against primary sources.
- Block scoring when coverage or freshness fails defined thresholds.
- State the data capability tier on every research report and model card.

## Audit record

The first runtime feasibility audit is recorded in `FREE_DATA_AUDIT.md`. Provider documentation is not treated as runtime verification.
