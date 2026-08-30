# Phase 9C Strict Accounting Engine Decision

Date: 2026-08-29
Status: **pass; P9C.3 complete**

## Decision

Quantrade may use the new `phase_9c_strict_quarterly_ttm_v1` engine as the
accounting foundation for Phase 9C dataset materialization. The engine is
fail-closed, point-in-time, and lineage-bearing. It does not change or replace
the frozen Phase 9B dataset.

The admitted rules are:

- standalone flows are reconstructed as `Q1`, `H1-Q1`, `9M-H1`, and `FY-9M`;
- true TTM is the sum of the latest four consecutive eligible standalone
  quarters without mixing concepts, units, fiscal chains, or future facts;
- net income prefers `NetIncomeLoss` and uses `ProfitLoss` only when the former
  cannot produce a complete TTM;
- balance-sheet inputs use dated instant facts;
- primary shares accept only dated
  `dei:EntityCommonStockSharesOutstanding`; period-average shares have no
  fallback path; and
- missing, incompatible, or ambiguous contexts are withheld with an explicit
  reason instead of being repaired.

The unified SEC resolver now keeps the original canonical fact eligible until
a later immutable observation reaches its own effective availability time.
Every selected fact exposes its accession, form, acceptance and availability
timestamps, period, fiscal context, unit, source, availability rule, and stable
observation hash.

## Frozen-range audit

The read-only audit evaluated the fixed 500-name Tier-B current-survivors
cohort on 183 weekly formations from 2022-01-07 through 2025-06-30. It examined
373,765 candidate facts and did not download data, mutate the database, or use
the July 2025–June 2026 holdout.

| Primitive | Aggregate coverage | Minimum formation coverage |
| --- | ---: | ---: |
| True-TTM net income / profit-loss | 93.37% | 90.80% |
| True-TTM operating cash flow | 92.12% | 89.40% |
| Assets endpoint | 97.32% | 96.00% |
| Equity endpoint | 97.33% | 96.00% |
| Endpoint-only shares | 87.66% | 85.80% |

All raw primitives exceed the frozen 70% aggregate feature gate and the 70%
minimum accounting-formation gate. The audit found zero availability or
lineage violations. Replaying the final historical formation twice produced
the same hash.

- Audit report SHA-256: `f01e78f71dd138183ea97e1547ad3ee5f7ed854bc12cf39f66dcb58e2e2fb847`
- Formation panel SHA-256: `d2f8a2552b189e5da2726554270e2238230a5c70cfd574e54c5e7e8a314d4be2`
- Fixed-date replay SHA-256: `84b42e5b0c71934eb9616e69c18a43577f159446eab7e19508e437c0eff48a78`

The generated detailed report remains a local derived artifact at
`data/derived/phase_9c_accounting_audit_v1.json`.

## Limitations

This remains survivorship-biased Tier B research using the current S&P 500
survivor cohort. Passing this foundation audit is not a performance result and
does not authorize an unbiased historical claim. Direct gross profitability,
historical SIC/FF12, and weighted-average-share primary substitution remain
excluded from Phase 9C v1.

## Consequence

P9C.4 may now materialize the weekly Phase 9C candidate dataset using the
completed wealth ledger and strict accounting engine, then freeze feature
family membership only after the prescribed coverage and redundancy audit.
