# Phase 9D Anchored Stability Protocol

Protocol key: `tier_b_anchored_accounting_residual_rank_v1`

Status: frozen before Phase 9D fitting

Registration date: 2026-08-30

Research tier: B, private current-survivors research

Baseline code commit: `869a5ad48fdb9429620cfae1d9e4c3aa2a359d34`

## Objective and evidence status

The objective is a lower-turnover monthly cross-sectional ordering that adds
incremental accounting information without discarding the deployed model's
existing ordering. It is not a return forecast or a guarantee of SPY
outperformance.

This is a result-informed successor to Phase 9C. Its historical evaluation is
research-readiness evidence, not independent confirmation. The July 2025
through June 2026 holdout has already been consumed and remains permanently
unavailable for selection or promotion.

## Frozen source data

- Cohort: `sp500_current_survivors_v1`, explicitly survivorship biased.
- Weekly feature panel: Phase 9C v1 with the existing point-in-time lineage,
  true-TTM accounting, neutral missing ranks, and static-sector limitation.
- Labels: the existing next-open-to-20-completed-session stock wealth return
  minus matching SPY wealth return, converted to within-formation centered
  ranks for model fitting.
- Development window and outer/inner folds: exactly the Phase 9C v1 registered
  folds. No split, purge, formation, label, or weighting rule may change.
- Calendar months, not security rows, remain the effective observations.

No new download, SEC concept, feature formula, label, cohort, sector mapping,
or historical period is admitted in this version.

## Corrected deployed anchor eligibility

The anchor replays the exact deployed artifact, means, scales, intercept, and
coefficients. A row is scoreable when every **mathematically non-zero** deployed
input is available. Inputs whose frozen coefficient is exactly zero cannot
exclude a row because they make no numerical contribution.

This correction must be audited before labels are read:

- scores for every row previously eligible under the Phase 9C exact replay
  must be byte-identical;
- newly eligible rows must arise only from ignoring exact-zero coefficient
  inputs;
- aggregate anchor coverage must be at least 95% and minimum weekly coverage
  at least 90%;
- every score retains the active artifact hash and input lineage.

Failure of any condition ends Phase 9D before fitting.

Within each formation, the eligible anchor prediction is converted to a
tie-aware centered percentile rank `A` in `[-1, 1]`.

## One frozen challenger

Only `anchored_accounting_residual_ridge_v1` may be fit.

The two allowed correction inputs are the already frozen, direction-adjusted
Phase 9C family values:

1. `investment_issuance`; and
2. `profitability_quality`.

Their raw members, directions, availability rules, accounting staleness limit,
and neutral missing value remain unchanged. Availability indicators do not
enter the model. No ablation or alternative family subset may be selected after
outcomes are inspected.

For each training example, the residual target is:

`R = label_centered_rank - A`

The challenger fits weighted ridge regression without an intercept:

`R = beta_investment * investment_issuance + beta_quality * profitability_quality`

Training-only weighted means and scales are used. The same calendar-month,
weekly-formation, and security weights as Phase 9C apply. Coefficients are not
sign constrained; their expected sign is positive because the two family
values are already direction adjusted.

The final candidate score is:

`candidate_raw = A + predicted_residual`

It is converted to a tie-aware centered cross-sectional rank only for ranking
metrics. No clipping, temporal smoothing, regime switch, or post-fit blending
is allowed.

## Candidate budget and tuning

Exactly three ridge penalties may be evaluated: `{1, 10, 100}`.

Inner chronological folds select the penalty with the highest equal-calendar-
month mean rank IC. If alternatives are within `0.002`, the larger penalty
wins. Outer results cannot tune the penalty, feature set, score formula,
portfolio rule, or gates. Total challenger configuration count is three.

Required references are:

- the corrected exact deployed anchor without refitting; and
- the candidate using the selected inner-fold penalty.

The pairwise model, six-family replacement, additive models, interactions,
regime-conditioned parameters, trees, neural networks, and alternative loss
functions are prohibited in this protocol.

## Portfolio attribution

The primary comparison applies identical construction to both reference and
candidate:

- final regular session of each month;
- exact Top 20;
- equal weight;
- next regular-session open entry;
- 20 completed sessions;
- 25-bp one-way primary cost.

Returns at 5, 10, and 50 bp are diagnostics. Top-20-entry/Top-30-retention may
also be reported as a secondary operational diagnostic, but it cannot earn a
model gate or rescue an exact-rule failure.

Turnover is one minus retained names divided by 20. Initial cash deployment is
reported but excluded from recurring-turnover means.

## Immutable uncertainty and regime definitions

- Primary uncertainty: paired circular moving-block bootstrap over ordered
  calendar-month IC deltas.
- Block length: `3` calendar months.
- Resamples: `10,000`.
- Numeric seed: `20260830`.
- Interval: deterministic 2.5th and 97.5th percentile interval.
- Probability: fraction of resampled paired mean deltas greater than zero.

SPY diagnostics use only bars available by the historical 8:00 p.m. Toronto
decision. Trend is the trailing 60-session return: bullish at or above `+5%`,
bearish at or below `-5%`, otherwise range-bound. Annualized 60-session
volatility is low below `15%`, normal from `15%` to below `25%`, and high at or
above `25%`. Regimes cannot tune or gate the model.

## Research-readiness gates

All gates are hard and conjunctive:

1. zero point-in-time, lineage, label-overlap, artifact-hash, holdout, or
   deterministic-replay violations;
2. 100% lineage, aggregate score coverage at least 95%, minimum weekly score
   coverage at least 90%, each correction family at least 80% aggregate and
   70% per-formation informative coverage, and every underlying modeled raw
   feature at least 70% aggregate coverage;
3. paired mean monthly rank IC at least `0.012` and at least `0.004` above the
   corrected deployed anchor on the identical sample;
4. positive candidate mean rank IC in at least three of four outer blocks and
   worst outer-block IC greater than `-0.020`;
5. paired moving-block-bootstrap probability of positive IC delta at least
   `90%`;
6. positive mean monthly top-minus-bottom-decile relative return;
7. candidate exact-Top-20 25-bp net relative return above zero, paired delta at
   least `+0.001` per month versus the same-construction anchor, and positive
   candidate net return in at least three of four outer blocks;
8. recurring one-way turnover no greater than `0.36` and no more than `0.01`
   above the same-construction anchor;
9. consecutive weekly rank stability at least `0.90`; and
10. each of the two correction coefficients is positive and materially
    non-zero (`abs(beta) > 1e-8`) in at least three of four outer fits.

The IC, coverage, and economic gates retain or tighten Phase 9C standards; none
is relaxed. If any gate fails, the result is `no-freeze`.

## Allowed decision

Passing every gate permits only `freeze_for_forward_shadow`. It does not permit
deployment, user-visible ranking changes, or a historical-performance claim.
Failure produces `no-freeze`. Thresholds and formulas cannot change after the
first Phase 9D outcome evaluation.

Promotion requires genuinely untouched forward observations collected after
the candidate artifact is frozen and evaluated under Phase 10.

## Reproducibility contract

Before fitting, persist and authenticate this protocol, baseline commit,
source artifact hashes, active artifact hash, exact non-zero input registry,
feature registry, folds, purge intervals, sample weights, three-configuration
grid, bootstrap constants, portfolio rules, regime constants, and gates. Two
independent runs must produce identical eligibility, dataset, fit, prediction,
portfolio, and evaluation hashes.
