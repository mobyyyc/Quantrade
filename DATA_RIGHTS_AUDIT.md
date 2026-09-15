# Quantrade Data-Rights Audit

**Decision date:** 2026-09-15  
**Scope:** Alpaca market data and SEC EDGAR-derived data used by the private V1 release candidate  
**Decision owner:** Quantrade project owner  
**Status:** private local use may continue; external staging is blocked on market-data rights

This is an engineering compliance assessment, not legal advice. It records what
the application actually retrieves, stores, derives, and displays, then applies a
conservative release rule where a provider has not granted an explicit right.

## Executive decision

| Data path | Local, single-owner private research | Hosted processing/storage | Invited closed-beta display | Public display or data API |
|---|---|---|---|---|
| Alpaca IEX bars and corporate actions | **Allowed for the current private workflow**, subject to the account agreement and plan limits | **Needs written confirmation before migration** | **Blocked until Alpaca grants the required display/redistribution and derived-data rights** | **Blocked** |
| SEC EDGAR submissions, filing metadata, and XBRL facts | **Allowed** | **Allowed after fair-access controls are implemented** | **Allowed with source attribution and truthful context** | **Allowed for the limited product presentation; do not create an unrestricted mirror without a separate review** |
| Scores, ranks, baskets, charts, and performance derived from Alpaca data | **Allowed for private research** | **Needs written confirmation** | **Blocked until written confirmation covers non-reconstructable derived outputs** | **Blocked** |

The architecture may be built, but no closed beta may expose Alpaca-derived
prices, charts, changes, rankings, scores, basket holdings, or performance until
the market-data gate below is satisfied. Calling a beta private, invite-only, or
free does not make its users the account holder.

## What the code actually uses

### Alpaca

The adapter calls Alpaca's Stock Historical Bars endpoint with the `iex` feed and
the Corporate Actions endpoint. It retrieves daily OHLCV bars using raw, split,
or all-adjusted semantics and actions needed to validate splits and distributions.
SPY uses the same source. Quantrade does not currently retrieve quotes, order-book
data, real-time streaming data, or submit trades.

Stored material includes compact, content-hashed source receipts; normalized
daily equity and benchmark bars; normalized corporate actions; availability and
retrieval times; and immutable run provenance. Historical research artifacts and
model datasets retain the normalized observations needed for reproducibility.

The web application displays or derives:

- latest regular-session close and one-session change;
- approximately one-year price charts;
- factor values, scores, ranks, explanations, and eligibility;
- top-stock and model-basket holdings; and
- historical basket and benchmark-relative results.

These are all inside the market-data rights boundary. A transformation is not
automatically free of the source agreement merely because the response is no
longer a raw JSON payload.

### SEC EDGAR

The ingestion path calls SEC company ticker/exchange data, submissions JSON,
dated submission history, Company Facts/XBRL APIs, and daily master indexes. The
daily path is incremental and limited to the configured company CIKs and relevant
forms: 10-K, 10-Q, 20-F, 40-F, 8-K, and their amendments. Forms such as 424B2 and
FWP are excluded.

Quantrade does not download original filing PDFs or HTML documents. It stores
compact, content-hashed JSON/index receipts, filing identity and acceptance
metadata, and selected normalized facts with observation history. The product
uses those records for new-filing counts, filing context, fundamental features,
score evidence, issuer identity, and point-in-time lineage.

## Provider findings

### Alpaca: no affirmative external-display clearance

Alpaca's official Market Data documentation describes the Basic plan as IEX-only
for real-time US equities, with historical data since 2016, a latest-15-minute
restriction, and a 200-request-per-minute limit. The documentation supports the
present private charting, backtesting, and strategy-development use case.

Alpaca's customer agreement also states that exchanges retain proprietary
interests in market data and restrict reproduction, distribution, sale, or
commercial exploitation without written consent. The repository contains no
separate redistribution agreement, commercial market-data license, or written
approval covering Quantrade.

Therefore:

- internal research access is not treated as permission to redistribute data;
- an authenticated closed beta is still external display to third parties;
- delayed or end-of-day presentation is not assumed to remove the restriction;
- derived scores and portfolios are not assumed to be exempt; and
- a no-charge beta is not assumed to be non-commercial.

Before staging, obtain a written answer from Alpaca that explicitly covers:

1. cached daily IEX OHLCV and corporate-action history from 2021 onward;
2. cloud processing, object storage, backups, and retention for internal service
   operation;
3. display of close, change, and historical charts to authenticated beta users;
4. display of non-reconstructable scores, ranks, feature explanations, basket
   selections, and SPY-relative performance derived from the data;
5. user count, delay requirements, attribution, exchange agreements, fees, and
   deletion obligations; and
6. whether bulk export or client-side access must remain prohibited.

An appropriate paid plan or separate license should be considered only if the
written response says the free plan cannot support the exact closed-beta use
case. If licensing is disproportionate, replace only the external-display source
with a provider whose terms explicitly permit it; do not silently mix providers
inside one historical series.

### SEC: reuse permitted, operational compliance incomplete

The SEC's Webmaster FAQ says SEC.gov content and EDGAR public filing content are
free to access and reuse, with limited exceptions such as separately licensed
stock imagery. The SEC APIs are public and require no authentication. This is
sufficient for Quantrade's extraction and limited product display of filing
metadata and facts.

Reuse permission does not remove these engineering obligations:

- identify requests with a descriptive User-Agent and monitored contact address;
- keep aggregate automated access at or below 10 requests per second across all
  processes and machines;
- cache, deduplicate, and request only required data;
- prefer SEC bulk files for large backfills instead of high-volume per-company
  traffic;
- tolerate temporary blocks and retry with bounded backoff;
- retain accession, form, acceptance time, source URL, and retrieval provenance;
- link or name the SEC as the source without implying SEC endorsement; and
- avoid republishing personal information merely because it appears in a public
  filing.

The current client is sequential and sends an identified User-Agent, and the
pipeline already caches compact receipts and deduplicates content. It does **not**
enforce a shared aggregate request-rate limit. Hosted SEC ingestion is therefore
blocked until Q4/Q5 adds a shared limiter. Use a conservative ceiling of five
requests per second for the deployment, leaving headroom below the SEC's
10-request-per-second maximum.

## Required data controls

### Rights classes

| Class | Examples | Storage rule | Product rule |
|---|---|---|---|
| `internal_market_raw` | Alpaca response receipts | Encrypted private storage; least privilege; no user download | Never return from product APIs |
| `internal_market_normalized` | OHLCV, actions, SPY bars | Private database/artifacts; retain only for research, audit, and recovery | Block externally until licensed |
| `market_derived_restricted` | scores, ranks, baskets, charts, relative results | Versioned private artifacts with source lineage | Block externally until derived-use rights are confirmed |
| `public_regulatory_source` | SEC submissions, Company Facts, daily indexes | Compact immutable receipts; deduplicate by content hash | Do not expose raw mirrors by default |
| `public_regulatory_derived` | filing metadata, selected facts, filing counts | Normalized, versioned, point-in-time records | May display with source/time/form/accession context |

No browser bundle, unauthenticated route, export, log, analytics event, or error
message may contain `internal_market_raw` material. Database credentials and
provider credentials remain server-only.

### Retention and deletion

Quantrade currently needs long-lived observations and lineage to reproduce model
research. That purpose does not itself grant retention rights. Before cloud
migration, the Alpaca confirmation must state permitted retention and required
deletion after termination. Until then, keep the dataset local, private, and
access-controlled; do not copy it into staging fixtures or developer downloads.

SEC compact receipts and normalized facts may be retained for provenance.
Original filings are intentionally not mirrored. Existing content hashes and
append-only observation history should remain; a later SEC revision is stored as
a later observation and must not overwrite what was available at an earlier
decision time.

### Product and deployment gates

The following gates are mandatory before Q6 external staging:

1. Store dated written evidence of the Alpaca decision, applicable agreement/plan,
   permitted uses, attribution, retention, and expiry/review date.
2. Add an explicit server-side market-data display entitlement. It must default
   to denied outside local-owner mode and fail closed when rights evidence is
   absent or expired.
3. Keep sanitized synthetic fixtures available so hosted UI work can proceed
   without copying restricted observations.
4. Add one aggregate SEC limiter shared by every hosted worker and backfill path,
   plus bounded retry/telemetry for 403 and 429 responses.
5. Prevent bulk data export and direct object-store access; authorize every
   company, chart, ranking, watchlist, portfolio, and update-status route.
6. Review these findings at least annually and whenever a provider, plan, feed,
   endpoint, product audience, display field, region, or agreement changes.

If Alpaca declines or does not answer, the release decision remains **blocked**;
silence is not permission.

## Tier-B and adjacent-source constraints

This audit does not upgrade the research evidence. The
`sp500_current_survivors_v1` cohort remains a fixed current-member sample with
survivorship bias, and current sectors remain static, non-point-in-time groupings.
Every model/performance presentation must retain those warnings. It must never be
described as verified historical S&P 500 membership or unbiased historical
performance.

The committed cohort artifact is a CIK-only CSV and the sector importer supports
a manually sourced CSV. Their original source/license is not independently
recoverable from the committed files. Before external staging, record the exact
source and reuse terms for the membership and sector snapshot. Do not add S&P/Dow
Jones branding, index logos, or company logos without a separate trademark and
asset-rights review. This is an adjacent staging dependency, not evidence that
the current Tier-B cohort is licensed index history.

## Evidence reviewed

Official sources reviewed on 2026-09-15:

- [Alpaca Market Data API overview](https://docs.alpaca.markets/us/docs/about-market-data-api)
- [Alpaca Market Data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq)
- [Alpaca Customer Agreement](https://files.alpaca.markets/disclosures/library/AcctAppMarginAndCustAgmt.pdf)
- [Alpaca disclosures library](https://alpaca.markets/disclosures)
- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [SEC Developer Resources](https://www.sec.gov/about/developer-resources)
- [SEC Webmaster FAQ](https://www.sec.gov/about/webmaster-frequently-asked-questions)
- [SEC Privacy and Security Policy, including automated-access limits](https://www.sec.gov/about/privacy-information)

Repository paths reviewed include the Alpaca adapter, market and benchmark
ingestion, SEC client and filing ingestion, source-receipt persistence, form
scope, score publication, and web price/research/portfolio queries. Provider
terms may change; the dated source evidence, not this summary alone, controls the
next release review.
