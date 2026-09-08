# Leakage-safe evaluation repair v1

Registered: September 7, 2026, before the corrected fits/outcomes are run.
Scope: P9D.0a protocol amendment and P9D.0b comparison repair. Research only.

## Superseding rule

The exact deployed artifact trained through April 2025 must not serve as an
out-of-sample reference for earlier validation windows. Earlier Phase 9C/9D
documents and outputs remain historical records, not erased or silently rewritten.
This amendment supersedes the fixed final-artifact reference and residual-anchor
rules in PHASE_9D_STABILITY_PROTOCOL.md. Its other restrictions remain in force.
No residual challenger is fit in this repair. Its eventual training residuals
must use chronological cross-fitted anchors, including inner tuning: no label
may enter the fit, parameter selection, or preprocessing used to predict itself.
Initial observations with insufficient earlier history must be excluded explicitly.

## Fixed inputs and comparisons

- Authenticate the Phase 9C weekly development dataset, folds, and feature panel.
- Authenticate the original SEC-clean monthly development dataset. Preserve its
  monthly sampling, six original percentile inputs, equal-formation weighting,
  and split-adjusted benchmark-relative target for the elastic-net reference.
- Refit that reference family within each chronological window; do not reuse
  final-artifact coefficients, fitted statistics, or its selected penalties.
  Inner-only grid: L1 {0.0001, 0.001}, L2 {0.001, 0.01, 0.1} (existing family grid).
- Challenger: existing six-family weekly rank ridge, penalties {0.1, 1, 10, 100}.
  No new features, residual corrections, pairwise models, or additional search.
- Preserve Phase 9C's four outer and twelve inner weekly windows. Monthly
  reference training is additionally restricted to their training-end cutoff;
  every included actual outcome must precede the validation start.
- Evaluate both predictions against the same existing wealth-ledger rank labels.
  This is an end-to-end recipe comparison, not attribution solely to estimator
  choice: the reference and challenger intentionally differ in features, target,
  and sampling. Do not mislabel it a controlled algorithm-only experiment.
- Reconstruct reference cross-sectional percentiles over the full available
  feature-panel universe, before joining completed labels. Never use future
  label availability to choose the percentile peer universe. Legacy reference
  fundamentals remain explicitly legacy annual semantics; the candidate retains
  the authenticated true-TTM values. Current sectors remain static Tier B.
- Inner selection compares candidates on identical reference-eligible rows;
  prefer stronger regularization within 0.002 monthly rank IC of the best.
- Fit preprocessing only on each fit's training rows. Reject non-finite values,
  duplicate keys, missing fold rows, outcome overlaps, and holdout-reaching labels.

## Reporting and artifact contract

Store complete outer predictions, fitted parameters, tuning records, source hashes,
training/validation boundaries, and paired coverage in a new immutable run folder.
Report paired monthly rank IC, four block results, same-sample weekly Top-20 gross
wealth-relative returns, and deterministic paired three-month moving-block
bootstrap (10,000 resamples, seed 20260830). Weekly Top-20 outcomes overlap and
are diagnostics, NOT a monthly tradable portfolio/backtest, net return, or live
performance. Official month-end construction/cost/turnover gates remain mandatory
before any shadow qualification; this repair does not pass them by proxy.

Write the final ridge research fit using a penalty selected on the registered
inner-validation predictions only, not outer metrics. Report the best observed
paired ranking diagnostic descriptively; do not automatically select or deploy
the model with the largest outer metric. Final fits are research artifacts only.
Refuse to overwrite any output run directory; failed runs are retained. A second
run must reproduce prediction and fit hashes before calling the repair verified.

## Evidence limits

The development history and model families have already informed prior research.
Correct chronological refitting removes parameter leakage, but cannot make reused
history independently untouched. July 2025–June 2026 stays report-only and is not
read by this runner. The 500-current-survivor cohort and static sectors remain
biased; no unbiased performance claim or guaranteed SPY outperformance is allowed.
Live eligibility/decision-time corrections and forward-confirmation gates remain
separate roadmap tasks. No deployment, scoring, ingestion, or database writes.
