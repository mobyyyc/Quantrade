# Data Capability Decision: DEP-001

## Decision

Date: 2026-08-20

**Accept the free-first stack for foundation work and SEC fundamental-data development. Do not approve it for validated market-data research, live scoring, or public performance claims until the conditional-source tests pass.**

The current project capability is **Tier B: research-only, not external-performance claims**.

## Provider disposition

| Source | Decision | Approved use now | Blocking condition |
|---|---|---|---|
| SEC EDGAR | Approved | Filing metadata, raw XBRL facts, availability-time design | Normalization and point-in-time tests still required before factors. |
| Alpaca Basic | Conditional | Provider contract and local adapter scaffolding only | Local API credentials plus historical-bar, adjustment, volume, and next-open audit. |
| FRED/ALFRED | Conditional | Provider contract and macro-schema scaffolding only | Local API key plus historical-vintage retrieval audit. |
| Alpha Vantage | Not adopted | Small manual comparison only | Its free request limit is unsuitable for the planned universe pipeline. |

## What is permitted

- Start Phase 1 foundation work: repository structure, provider-neutral contracts, schema design, configuration boundaries, and deterministic run metadata.
- Implement SEC ingestion behind a provider boundary.
- Build static or fixture-backed private-beta UI states clearly labeled as sample data.
- Run exploratory research that is explicitly marked Tier B and does not represent an unbiased historical index result.

## What is prohibited

- Production score publication or an investable backtest based on untested Alpaca data.
- Any claim that a current S&P 500 snapshot represents historical S&P 500 membership.
- Liquidity, capacity, or transaction-cost conclusions before volume and corporate-action treatment are tested.
- Committing API keys, provider responses containing secrets, or unlicensed redistributed market data.

## Required gate before market-data-dependent research

The following must be complete before P2 market-data ingestion can support factor or backtest work:

1. Configure local-only `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` credentials for a free Alpaca account.
2. Configure a local-only `FRED_API_KEY`.
3. Re-run the audit for AAPL, MSFT, and a known split or ticker-change case.
4. Reconcile adjusted close, raw open, split treatment, dividend treatment, volume, and historical availability.
5. Record the results in provider-adapter tests and update the data capability tier if warranted.

## Paid-data trigger

Do not purchase data preemptively. Evaluate paid providers only if the project needs validated historical constituent membership, delisted securities, longer auditable price history, guaranteed point-in-time data, public display rights, or real-time coverage.

## Consequence for the roadmap

Phase 0 is complete. Phase 1 may begin because it does not rely on unverified market-data results. The first market-data-dependent task remains gated by this decision.
