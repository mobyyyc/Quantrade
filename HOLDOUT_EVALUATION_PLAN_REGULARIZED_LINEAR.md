# Holdout Evaluation Plan: Regularized Linear Development Candidate

## Status and boundary

This plan is pre-registered before any holdout rows are read for the
regularized-linear candidate. The final holdout is locked from 2025-07-01
through 2026-06-30, inclusive, under `tier_b_20d_v1`.

Do not execute this plan until the baseline-comparison protocol is frozen and
explicitly approved. The holdout may be evaluated once; it cannot be reused for
feature changes, hyperparameter selection, or retrying a failed gate.

## Frozen candidate

- Model: elastic net.
- Inputs: the six percentile columns in
  `sp500_current_survivors_20d@v1`, with no additions or transformations.
- Target: completed 20-session benchmark-relative return.
- Hyperparameters: L1 `0.001`; L2 `0.01`.
- Training data: all development rows dated no later than 2025-06-30.
- No holdout fit, scaling fit, threshold tuning, feature selection, or
  calibration is permitted.

## Required comparable baseline

`REGULARIZED_MODEL_COMPARISON_PROTOCOL.md` freezes the exact baseline portfolio
mapping, candidate mapping, rebalance schedule, common eligibility universe,
liquidity gate, next-session execution convention, portfolio size, and
1/5/10/20-bps one-way-cost calculations.

The existing equal-weight score baseline is not yet an approved benchmark for a
regularized-model promotion. Therefore the holdout run must not be treated as
approval until the baseline is finalized under the same protocol.

## Single evaluation procedure

1. Confirm the immutable dataset hash, holdout dates, cohort version, feature
   registry hash, and model-card hyperparameters.
2. Fit the frozen candidate once using development rows only.
3. Generate candidate and baseline signals on holdout decision dates without
   revising any feature, price, or filing availability timestamp.
4. Apply the shared liquidity and execution rules; report coverage and every
   exclusion.
5. Calculate relative return, cumulative return, volatility, Sharpe, Sortino,
   drawdown, and 5/20-bps cost sensitivities for both methods.
6. Append one immutable evaluation record and a result artifact; do not rerun
   after viewing results.
7. Apply `MODEL_APPROVAL_POLICY.md`. A failure is recorded, not tuned away.

The first guarded implementation is `quantrade_research.holdout_evaluation`.
It requires `--confirm-locked-holdout`, refuses to overwrite its selection
manifest, and produces selections only; it intentionally does not calculate or
expose holdout performance until the separately approved execution-and-cost
evaluation step.

`quantrade_research.execution_cost_evaluation` is the corresponding frozen-
selection calculator. It applies identical next-open entry/exit mechanics and
1/5/10/20-bps cases to supplied price periods, rejects missing marks and
unhandled corporate actions, and cannot accept a formation date outside the
selection manifest. A separate database adapter supplies those price periods;
this calculator never re-ranks names.

## Non-negotiable interpretations

- A positive holdout result would support only private Tier-B research review.
- A Tier-B result is never an unbiased historical-performance or public
  performance claim.
- Any protocol change requires a new experiment version and a new, untouched
  final holdout; it cannot reopen this one.
