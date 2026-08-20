# Free-Data Provider Audit

## Audit scope

Date: 2026-08-20

This is a small feasibility audit, not a vendor certification. It tests whether the free-first sources can support the planned private-beta data pipeline and records every unverified assumption.

## Runtime sample

| Source | Sample | Result | Decision |
|---|---|---|---|
| SEC EDGAR submissions | Apple, CIK `0000320193` | Success. The endpoint returned AAPL and 1,000 recent filing records. | Accept as the source-of-record candidate for filing metadata. |
| SEC EDGAR company facts | Apple, CIK `0000320193` | Success. The endpoint returned `dei` and `us-gaap` taxonomies. | Accept for raw fundamental facts, subject to normalization. |
| FRED/ALFRED | S&P 500 historical-series download | Not confirmed. The unauthenticated CSV request was refused by the remote host in this environment. No FRED API key is configured. | Conditional. Obtain an API key and rerun the sample. |
| Alpaca Basic | Historical daily US-equity bars | Not executed. Neither Alpaca API credential is configured. | Conditional. Create a free account, configure credentials locally, then test coverage and adjustments. |

No API secret or credential value was read, printed, or committed during this audit.

## Confirmed SEC behavior

The SEC sample supports these conclusions:

- Public submissions and XBRL company-facts endpoints are reachable without an API key when identified requests are used.
- Filing metadata is sufficient to begin building availability-time logic.
- Facts arrive as source taxonomies, not an immediately usable cross-company factor table. Quantrade must normalize concepts, periods, units, amendments, and accepted timestamps.

## Unconfirmed free-source assumptions

The following remain unverified and must not be assumed by a backtest:

- Alpaca Basic's actual historical daily-bar coverage for the requested universe.
- The provider's adjusted-price and corporate-action behavior in the selected feed.
- Volume completeness for the USD 10 million median-dollar-volume eligibility rule.
- Delisting coverage and point-in-time S&P 500 membership.
- FRED/ALFRED retrieval, rate limits, and real-time-vintage handling under a configured key.

## Capability decision

The free-first path remains appropriate for the private beta, with these constraints:

- SEC EDGAR is approved for the next implementation phase.
- Alpaca Basic and FRED/ALFRED are approved only as conditional adapters; no model or backtest may rely on them until credentialed runtime samples pass.
- All research remains Tier B because historical universe membership and delisted securities are not verified.
- No public or investable historical-performance claim may be made from this data path.

## Required follow-up before ingestion

1. Add local-only Alpaca Basic credentials and FRED API key. Never commit them.
2. Re-run this audit against AAPL, MSFT, and a symbol with a known split or ticker change.
3. Reconcile raw and adjusted bars, split handling, volume, and next-session opens.
4. Record the exact feed, plan, response dates, and failure behavior in the provider adapter tests.

## Definition of done for P0.3

- The runtime result for every proposed free source is documented.
- Unverified provider claims are explicitly separated from tested behavior.
- The data capability decision is ready for P0.4.
