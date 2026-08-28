# Phase 9B monthly feature-family decision

**Decision: NO FREEZE**

No pre-registered market-wide challenger passed every frozen gate. The active private-beta model remains unchanged.

## Gate results

| Candidate | Failed gates | Mean monthly IC | 25 bp top-20 relative return | Turnover |
| --- | --- | ---: | ---: | ---: |
| `signed_family_composite` | coverage, rank_ic, top20_return_at_25bp, turnover, all_validation_blocks_positive, rank_stability | -0.048094807100712324 | -0.014853634170448257 | 0.5857142857142857 |
| `ridge` | coverage, rank_ic, top20_return_at_25bp, turnover, all_validation_blocks_positive, rank_stability | 0.0014429261350421558 | -0.0008095627506410499 | 0.5928571428571429 |
| `low_l1_elastic_net` | coverage, rank_ic, top20_return_at_25bp, turnover, all_validation_blocks_positive, rank_stability | -0.0015351523303903795 | -0.001138708095244793 | 0.5761904761904761 |
| `robust_ridge` | coverage, top20_return_at_25bp, turnover, all_validation_blocks_positive, rank_stability | 0.008564593152878539 | -0.004328364257284941 | 0.5595238095238095 |

## Interpretation

The market-wide robust-ridge challenger produced a small IC improvement, but failed coverage, 25 bp portfolio return, validation-block consistency, and rank-stability requirements. Static-sector variants cannot rescue a candidate because current sector labels are non-point-in-time Tier-B metadata.

The result is a valid negative experiment, not permission to tune the gates after seeing outcomes. All outputs remain private, survivorship-biased Tier-B research and do not establish future outperformance.

Decision hash: `3e2ed09e64bdfadbf6631b8eac56710102b46adc65ad19ee6139e930dc8c7241`
