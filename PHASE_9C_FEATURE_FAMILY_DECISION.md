# Phase 9C Feature-Family Decision

Date: 2026-08-30
Status: **pass; P9C.4 complete**

## Decision

Quantrade freezes `phase_9c_weekly_feature_family_v1` as the first Phase 9C
feature panel. It contains 13 raw features grouped into six economic families.
The panel is suitable for constructing the Phase 9C development dataset, but
it does not replace the deployed model and it is not a performance result.

The frozen families and signs are:

| Family | Raw feature | Preferred direction |
| --- | --- | ---: |
| Momentum / trend | 12-to-1-month momentum | higher |
| Momentum / trend | six-month SPY-relative strength | higher |
| Reversal | prior 20-session return, excluding formation day | lower |
| Value | book to market | higher |
| Value | true-TTM earnings yield | higher |
| Value | true-TTM operating-cash-flow yield | higher |
| Profitability / quality | true-TTM return on assets | higher |
| Profitability / quality | true-TTM operating-cash-flow profitability | higher |
| Profitability / quality | true-TTM accruals scaled by assets | lower |
| Investment / issuance | year-over-year asset growth | lower |
| Investment / issuance | split-reconciled year-over-year share issuance | lower |
| Risk | 60-session realized volatility | lower |
| Risk | 60-session SPY-residual volatility | lower |

Every raw feature is converted to a tie-aware, market-wide centered rank in
`[-1, 1]`. Missing values receive a neutral rank of zero. Each family is the
sum of its member ranks divided by the family's fixed member count, so missing
inputs cannot increase the weight of whichever inputs remain. Availability is
recorded separately and does not enter the v1 model. A row becomes score
eligible when at least three families have one or more informative inputs.

Historical sector ranks are not used because point-in-time SIC/FF12 coverage
was not adequate at P9C.1. Direct gross profitability also remains excluded.
Additional correlated variants such as 52-week-high proximity and residual
momentum were not added after seeing the panel; the family scope stayed at the
pre-authorized compact set.

## Point-in-time and construction rules

- The fixed Tier-B `sp500_current_survivors_v1` cohort is used; results remain
  survivorship biased.
- Weekly formations span 2022-01-07 through 2025-06-30. The consumed
  July 2025–June 2026 holdout was not read.
- Price features use only bars available at formation time. Formation market
  capitalization uses the unadjusted close and endpoint-only shares.
- Accounting inputs use the P9C.3 strict standalone-quarter and true-TTM
  resolver, a 450-day staleness ceiling, and complete selected-fact lineage.
- Share issuance reconciles ordinary splits and fails closed across unresolved
  structural actions.
- Weekly examples receive weights normalized to sum to one inside each
  calendar month. Calendar months remain the independent inference unit.

## Frozen-range audit

The immutable panel contains 91,500 rows: 500 securities across 183 weekly
formations. Overall score eligibility is 98.21%, and the minimum formation
eligibility is 96.80%.

| Family | Aggregate informative coverage | Minimum formation coverage |
| --- | ---: | ---: |
| Momentum / trend | 98.07% | 96.80% |
| Reversal | 98.30% | 97.00% |
| Value | 87.42% | 85.40% |
| Profitability / quality | 94.12% | 92.20% |
| Investment / issuance | 96.67% | 94.60% |
| Risk | 98.22% | 97.00% |

All 13 raw features exceed the frozen 70% aggregate gate. Every market family
exceeds 90% coverage at every formation, every accounting family exceeds 80%
aggregate and 70% at every formation, and calendar-month weights are one to
decimal tolerance. The audit found zero availability-lineage violations.

No within-family pair exceeds the absolute 0.95 redundancy gate. The largest
within-family correlation is 0.8953 between realized and idiosyncratic
volatility; momentum and relative strength correlate at 0.6177. Replaying the
final formation produced an identical result hash.

- Panel SHA-256: `9ffb5b22a7aaf8f6e75dd2b14331c64602b0df421b7eaaf4ff997d694ad84dd5`
- Lineage SHA-256: `af80804e2a4d28fde1a6911838339907cd2563ed3d8e6f0819b4b1111794a142`
- Logical panel SHA-256: `9ebd42735c7a7c67cf616dd6243062516242b6fe1d86db81fd1f11c284dab977`
- Formation panel SHA-256: `5c29dc52898a701a72d768948e574b4fccaadbbdf951686b5f8d70c236a257c2`
- Fixed-date replay SHA-256: `46ca1d50f7b430f25ad7ad185f2f893bc92d3dbd9ca130ecf8758cee99098708`
- Audit report SHA-256: `03470f46456b71908a428a055720b8199e0191ffce3eb18b8ddae83a08455952b`

The generated panel, compressed lineage, and audit report remain local derived
artifacts under `data/derived/phase_9c_weekly_feature_panel_v1.*`.

## Limitations

This is Tier-B private research using today's S&P 500 survivors and current
sector metadata only as provenance. It cannot support an unbiased historical
S&P 500 claim. Neutral missing ranks prevent missing data from mechanically
helping or hurting a company, but they do not make unavailable information
informative. Coverage diagnostics must remain alongside future model results.

## Consequence

P9C.5 may join the frozen wealth labels to this immutable feature panel, apply
label-safe eligibility, and create nested chronological development folds.
The July 2025–June 2026 holdout remains report-only.
