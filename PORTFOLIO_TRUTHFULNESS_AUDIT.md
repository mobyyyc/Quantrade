# Portfolio Truthfulness Audit

**Audit date:** 2026-09-13

**Roadmap task:** Q2.2

**Scope:** private V1 monthly model portfolio

## Contract

- A formation uses the final completed score publication before a calendar-month boundary.
- The selected model is the model recorded in that dated score run. A deployment change over a weekend cannot replace it.
- Exactly the top 20 eligible names are fixed before the next session and assigned equal 5% target weights.
- The immutable fill ledger uses the first later regular-session open after that open is present in validated market data. The product does not claim an order was physically submitted at the open.
- Daily rankings are separate research context and never alter the current basket.
- A missed next-open formation window is recorded as missed and cannot be reconstructed later.
- The 5-, 20-, and 60-session results use the original fill ledger and the required later close. Ordinary splits and USD cash dividends are applied to both holdings and SPY; incomplete or complex events withhold the result.
- Stored basket and SPY returns are gross. The portfolio history additionally shows an estimated net difference versus SPY by subtracting the pre-registered 25 bp one-way cost case times recorded one-way turnover. Commissions and taxes are not modeled.

## Implemented controls

- `portfolio_truthfulness_audit` checks month-end formation, exact next-open date, dated model identity, top-20 membership, position/trade counts, NAV reconciliation, outcome windows, return arithmetic, wealth-ledger provenance, and gap conflicts.
- The portfolio history is now a complete formation record: completed, pending, withheld, and missed states remain visible.
- Official queries accept only `monthly_last_session_next_open_v1`. Legacy daily and UI-preview records cannot appear as official portfolios.
- Formation now follows the model that produced the dated month-end scores rather than whichever model is deployed on execution day.
- Product copy distinguishes a selection fixed before the session from a fill ledger materialized after validated market data arrives.

## Local database result

The 2026-09-13 read-only audit passed with no critical findings. The database contained no official monthly formation yet and one legacy preview row. That row is intentionally retained under the immutable legacy protocol for provenance, but it is excluded from the portfolio, Today, and Research views. There were no missed-formation records or portfolio outcomes at the audit cutoff.

## Limits

- A paper fill is a deterministic simulation at the recorded regular-session open, not evidence of a live executable fill.
- The 25 bp cost case is an estimate applied to one-way turnover, not a stored broker charge.
- Market impact, commissions, taxes, borrow costs, and FX are outside V1.
- Results are private research evidence, not an outperformance guarantee or personalized investment advice.
