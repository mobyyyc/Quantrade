# Phase 9D Failure Review

Review key: `phase_9d_failure_review_v1`

Status: closed before Phase 9D fitting

Evidence boundary: Phase 9C development results only. The consumed July 2025
through June 2026 holdout was not used.

## What Phase 9C established

Phase 9C improved the research foundation: corporate-action-aware wealth
labels, point-in-time true-TTM accounting, neutral missing ranks, weekly
formation with calendar-month weighting, purged chronological folds, complete
lineage, and deterministic model and portfolio artifacts all worked. Coverage
and rank stability were not the primary failure.

The model experiment failed because the new rankings did not improve the
deployed ordering on identical samples:

- family ridge paired IC delta: `-0.01991`;
- pairwise-linear paired IC delta: `-0.03194`;
- both candidates produced positive IC in only two of four outer blocks;
- bootstrap probabilities of positive IC improvement were only `11.24%` and
  `8.79%`;
- exact-rule recurring turnover exceeded the reference-relative allowance by
  `0.07826` and `0.16087`;
- paired 25-bp net portfolio deltas were negative for both candidates.

The positive standalone portfolio averages do not contradict the decision.
They came from different sets of completed outcome months. On the required
paired periods, the ridge result was `-0.01589` per month relative to the
deployed reference and the pairwise result was `-0.00068`.

## Root-cause interpretation

1. **Wholesale replacement was too aggressive.** The six-family candidate
   replaced rather than preserved the deployed ordering. The deployed exact
   reference retained materially higher IC on the fair sample.
2. **The pairwise objective added no usable edge.** It had negative average IC,
   a negative top-minus-bottom spread, higher turnover, and an unstable
   momentum/trend sign.
3. **Breadth did not equal incremental information.** Several Phase 9C families
   overlap signals already present in the active model. Adding all six at once
   made attribution weak and increased degrees of freedom.
4. **Accounting additions should be tested as residual information.** The
   direction-adjusted investment/issuance and profitability/quality families
   are economically distinct from the active market-heavy anchor and had
   strong informative coverage. They can be tested without reopening raw
   feature selection.
5. **Turnover must be controlled by model architecture first.** A small
   correction around an anchored score is preferable to selecting a high-
   turnover model and attempting to rescue it with a portfolio buffer.
6. **Regime interactions are not justified.** The weakest slice was generally
   range-bound, low-volatility history, but some regime cells contained only
   two to seven weekly formations. These diagnostics cannot support a new
   conditional model.
7. **The registration process had a preventable omission.** Phase 9C required
   a numeric bootstrap seed before fitting but did not record one. Phase 9D
   records every stochastic constant before any outcome run.

## Consequence for the next experiment

Phase 9D will test one anchored residual-ridge challenger, not a new model
search. The exact deployed score remains the base ordering. Only the frozen
investment/issuance and profitability/quality family values may correct its
residual. The pairwise model, six-family replacement, regime interactions,
trees, neural networks, and new feature definitions are out of scope.

Because Phase 9D design choices were informed by Phase 9C development results,
reusing that history cannot create an independent confirmation claim. A model
that clears the Phase 9D historical readiness gates may be frozen for forward
shadow collection only; it cannot replace the deployed model until untouched
forward outcomes pass Phase 10.
