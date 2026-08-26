# Regularized Model Comparison Protocol: `tier_b_regularized_linear_v1`

## Status

Pre-registered comparison specification. This document fixes how the existing
baseline and the frozen development-only elastic-net candidate will be compared
before the locked holdout is evaluated. It does not authorize that evaluation.

## Common universe and eligibility

On each formation date, both portfolios start with the **same** eligible
universe: securities with a completed, eligible baseline snapshot and all six
required percentile features, a current cohort membership record, a valid
next-session regular-session open, and trailing 20-session median dollar volume
of at least USD 10 million.

If fewer than 20 shared eligible securities exist, the formation is withheld
for both portfolios. Neither side may replace a missing name after rankings are
known.

## Only permitted difference: ranking signal

| Portfolio | Ranking signal |
| --- | --- |
| Baseline | Existing `baseline_equal_weight_v1` score, descending |
| Candidate | Frozen elastic-net prediction of 20-session return relative to SPY, descending |

The candidate uses exactly the six exported percentile features, development-fit
standardization means/scales, L1 penalty `0.001`, and L2 penalty `0.01` from
`MODEL_CARD_REGULARIZED_LINEAR_DEVELOPMENT.md`. There is no blending,
calibration, threshold, sector cap, or post-selection discretion.

For equal values, both rankings break ties by ascending stable `security_id`.
Each selects the top 20 shared eligible securities.

## Identical portfolio mechanics

- Formation: final eligible US trading day of each calendar month.
- Decision time: 8:00 p.m. America/Toronto with the recorded point-in-time data
  cutoff.
- Execution: next eligible US regular-session open; never same-close.
- Capital: common USD 1,000,000 analytical starting NAV, fractional shares,
  long-only, fully invested, no leverage, borrowing, shorting, cash yield, or
  sector cap.
- Weighting: 5% per selected security at every formation.
- Rebalance: sell all prior positions at the common next-open price, then buy
  the new 20-name basket at that same open.
- Benchmark: SPY, formed and executed at the same next-open convention.
- Marks: use the documented unadjusted execution opens and approved adjusted
  pricing/position-accounting convention. Missing marks, opens, or corporate
  action handling produce an explicit withheld outcome rather than a repair.

## Identical cost and reporting treatment

Both portfolios report the same one-way cost cases: 1, 5 (baseline), 10, and
20 basis points on every entry and exit notional. Both report identical
coverage, exclusions, turnover, exposure, sector concentration, cumulative and
benchmark-relative return, CAGR, annualized volatility, Sharpe, Sortino,
maximum drawdown, and Calmar diagnostics.

No result may be selected solely because it looks favorable under a lower cost
assumption.

## Holdout safety

The fixed 2025-07-01 through 2026-06-30 holdout may not be used to modify this
document, candidate hyperparameters, the feature set, the portfolio size, or
any execution rule. A completed evaluation is recorded once in the immutable
experiment log. A failed condition remains a failure; there is no rerun after
viewing results.

## Interpretation boundary

Even if the candidate exceeds the baseline, it remains Tier-B private research
only. This comparison cannot create an unbiased historical-performance or
public-performance claim.
