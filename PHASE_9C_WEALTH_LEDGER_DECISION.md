# Phase 9C Wealth-Ledger Decision

Decision key: `phase_9c_wealth_ledger_reconciliation_v1`

Decision date: 2026-08-29

Status: **P9C.2 complete; proceed to P9C.3**

## Implemented accounting

The deterministic ledger buys one share at the formation entry mark, applies
ordinary forward/reverse/unit splits and USD cash dividends in effective-date
order, retains distributions as cash, and values the resulting shares and cash
at the exit mark. The same rule is applied independently to SPY. Entry-date
actions are excluded because the entry price is already ex-action; exit-date
actions are included.

Unknown, undated, incomplete, non-USD, or complex actions are never estimated.
Those windows are withheld. Extreme unexplained raw-price discontinuities are
also withheld.

Provider total-return-adjusted bars are a reconciliation control, not the
development label source. A ledger result is usable only when its return agrees
with the provider control within 25 basis points. This catches omitted actions
and ticker-identity collisions without hard-coded symbol exceptions.

## Reconciliation result

The frozen July 2025 through June 2026 audit produced:

- status: `pass`;
- accepted equity windows: 110,771;
- accepted ordinary-action equity windows: 28,528;
- ledger-rule withheld equity windows: 3,064;
- provider-reconciliation withheld equity windows: 950;
- SPY comparison windows: 231;
- SPY corporate actions: 4;
- equity-action p95 absolute difference: 0.0007362137;
- equity-action maximum accepted difference: 0.0024993656;
- SPY p95 absolute difference: 0.0000811149; and
- SPY maximum absolute difference: 0.0002558749.

The 10-basis-point p95 and 25-basis-point maximum gates passed without being
relaxed. The audit correctly detected examples where the free action feed was
not safe to trust directly, including a missing spin-off and a ticker-identity
collision. Those observations are withheld by the reconciliation policy.

Audit artifact:
`data/derived/phase_9c_wealth_ledger_reconciliation_20260829_v4.json`

Audit SHA-256:
`d87d07eb4e62b4306e88a69bc368cefb895f20b5998a1eeb76bb6e36f22c1e7f`

## Operational integration

Daily ingestion now stores raw, split-adjusted, and total-return-adjusted stock
and SPY bars, plus compact SPY corporate-action receipts. Stock and benchmark
actions catch up from the last successful source-update boundary. Complete
equity actions and benchmark actions are append-only; duplicate provider IDs
are no-ops.

Paper-portfolio checkpoints use explicit stock/SPY wealth accounting and store
the rule, source cutoff, action count, and deterministic ledger hashes. A
missing mark, complex action, incomplete price path, or reconciliation failure
creates an immutable withheld checkpoint rather than a performance value.

## Limitations

- This remains Tier-B current-survivor research and is not an unbiased public
  performance claim.
- Cash dividends remain cash; small differences from provider reinvestment are
  tolerated only within the frozen reconciliation gates.
- Provider controls are used only to validate or withhold a result, never to
  replace the explicit ledger return.
- Historical weekly label materialization belongs to P9C.5; this decision
  closes the accounting engine and its validation foundation only.

## Consequence

P9C.2 no longer blocks Phase 9C. P9C.3 is the next roadmap task: implement the
fail-closed point-in-time standalone-quarter and true-TTM SEC engine with full
selected-fact lineage and no weighted-average-share primary fallback.
