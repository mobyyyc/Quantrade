# SEC Fundamental Coverage Review

## Scope

This review examines the first completed live score run dated 2026-08-24.
All 500 members of the active S&P 500 universe were processed. The original
`baseline_equal_weight_v1` output contained 434 eligible scores and 66
withheld scores.

## Findings

| Condition | Affected names | Decision |
| --- | ---: | --- |
| No standard SEC `dei:EntityCommonStockSharesOutstanding` fact in the normalized store | 42 | Remain withheld. Do not use weighted-average shares or an inferred share count as a substitute. |
| No eligible annual `us-gaap:NetIncomeLoss` fact | 21 | Recover when an eligible annual SEC `us-gaap:ProfitLoss` fact is present. |
| Missing annual-period opening assets | 1 | Remain withheld. |
| Insufficient split-adjusted history | 3 | Remain withheld until the required history exists. |

The categories overlap: HONA has both a missing annual income input and
insufficient price history. The short-history names are FDXF, HONA, and Q.

## Evidence and recovery rule

The company-facts payload for HRL contains no standard
`dei:EntityCommonStockSharesOutstanding` observation. The absence is therefore
not a parser drop that may be repaired by reingesting the same free source.

For the 21 income gaps, the normalized store already contains standard
`us-gaap:ProfitLoss` observations. SEC describes this as consolidated net
income or loss after income taxes, including the portion attributable to
noncontrolling interests. `earnings_yield_ttm@v2` and
`return_on_assets_ttm@v2` now use an annual `NetIncomeLoss` fact first and use
`ProfitLoss` only when the former is unavailable. Both retain the existing
point-in-time availability and annual-period gates.

No historical snapshot was edited. A read-only rerun against the original
2026-08-24 inputs projects 451 eligible and 49 withheld names under the v2
fundamental definitions. The first published v2 result must be created by the
next normal daily run.

## Follow-up

Do not add a paid provider solely for the 42 share-count gaps yet. First
monitor the v2 run over several sessions and retain the explicit unavailable
reasons. Reconsider a licensed shares-outstanding provider only if coverage
remains materially inadequate for the private-beta workflow.
