# Next-Generation Model Evaluation Protocol: `tier_b_challenger_selection_v1`

## Status and purpose

Pre-registered before adding challenger features or training a challenger. This
protocol determines whether a model may be frozen for shadow evaluation. A
negative result is final for that candidate version.

The active `tier_b_regularized_linear_development_v1` model is the reference.
All selection evidence comes from purged development folds ending no later than
2025-06-30. The consumed 2025-07-01 through 2026-06-30 holdout is reporting
history only and cannot select, tune, calibrate, or rescue a challenger.

## Common sample and timing

- Use at least three expanding chronological folds with a 20-session purge
  before each validation window.
- Compare the active model and challenger on exactly the same securities,
  score dates, completed 20-session labels, monthly formations, execution
  marks, and exclusions.
- Use the fixed `sp500_current_survivors_v1` Tier-B cohort and preserve its
  survivorship and static-sector warnings.
- Use the 8:00 p.m. Toronto decision timestamp and next-regular-session open.
- Withhold a row or formation from both models when either side lacks a required
  point-in-time input or valid execution mark.
- Require at least 90% feature coverage. Record every exclusion without repair.

## Candidate feature diagnostics

Before any P9.4 model comparison, `next_gen_feature_diagnostics_v1` evaluates
the fixed `next_gen_free_v1` feature set on monthly development formations from
January 2022 through June 2025. It does not read the locked holdout target.

A candidate proceeds only when all of these frozen data-quality gates pass:

- aggregate cohort coverage is at least 90% and every monthly formation has at
  least 80% coverage;
- median absolute monthly correlation with every active feature is no greater
  than 0.90;
- median consecutive monthly rank correlation is at least 0.10;
- median top-20 month-to-month turnover is no greater than 0.90; and
- point-in-time violations are zero.

Candidate and active inputs are compared after the same static Tier-B sector
normalization. Missing inputs remain explicit exclusions. A rejected feature
version cannot be rescued by imputation or by inspecting the holdout.

## Fixed P9.4 candidate grid

The model-family grid is fixed before comparison results are generated. Every
challenger uses the six active inputs plus the two P9.3-approved candidates,
`downside_volatility_60d@v1` and `return_on_assets_change_yoy@v1`.

- Robust linear: Huber-loss iteratively reweighted ridge with delta `1.0` or
  `1.5` and L2 penalty `0.01` or `0.10`.
- Gradient boosted: deterministic ten-bin regression stumps, either 24 trees
  at learning rate `0.05` or 36 trees at learning rate `0.03`; fitting uses a
  deterministic maximum 100,000-row subsample.
- Ranking-oriented: deterministic pairwise logistic linear ranker using ten
  top-versus-bottom pairs per training date, 20 epochs, learning rate `0.03`,
  and L2 penalty `0.001` or `0.01`. Its training-only scores are linearly
  calibrated to the return target solely for the MAE/RMSE guardrails.

The active reference is refit within every fold using its frozen elastic-net
specification (`l1=0.001`, `l2=0.01`) and the original six features. All models
are measured on the identical complete-row sample. No family, hyperparameter,
feature, or threshold may be changed after seeing these results.

## Frozen measurements

All returns are decimals. All cross-sectional rank calculations use the shared
eligible sample for each score date and ascending stable `security_id` for ties.

| Measure | Definition | Role |
| --- | --- | --- |
| Mean daily Spearman IC | Mean, across validation dates, of Spearman correlation between model score and completed 20-session SPY-relative return | Primary ranking objective |
| Top-minus-bottom spread | Mean return of the highest prediction decile minus the lowest prediction decile, using equal-count date-level deciles before averaging | Economic ranking check |
| Positive IC share | Fraction of validation dates with IC greater than zero | Directional stability |
| Fold IC | Mean daily IC calculated separately within each chronological fold | Regime stability |
| Consecutive-rank correlation | Median Spearman correlation of model ranks on the shared security intersection of consecutive score dates | Score stability |
| Monthly turnover | Mean one-way equal-weight turnover, `0.5 × sum(abs(new_weight - old_weight))`, including entries and exits | Trading stability |
| 20-bps relative return | Cumulative monthly top-20 return after 20-bps one-way entry and exit costs, minus the identically timed SPY return | Cost robustness |
| Positive month share | Fraction of completed monthly formations whose post-cost basket return exceeds SPY | Portfolio consistency |
| MAE | Mean absolute stock-level error for the completed 20-session SPY-relative target | Forecast-error guardrail |
| RMSE | Root mean squared stock-level error for the same target | Tail-error guardrail |

Monthly portfolios use the final eligible score date of each calendar month,
top 20 names, 5% initial weights, and the next-open execution protocol. Adjacent
20-session outcomes may overlap, so they are evidence rather than independent
trials.

## Challenger freeze gates

Every gate must pass on the common purged development comparison:

1. Zero point-in-time violations and zero unresolved data-quality issues.
2. Identical observation count, score-date count, fold count, and monthly
   formation count for the active model and challenger.
3. Challenger feature coverage of at least 90%.
4. Mean daily IC improves on the active model by at least `0.005` absolute.
5. Top-minus-bottom spread is no worse than the active model by more than
   `0.0025`, or 25 basis points per 20-session outcome.
6. Mean IC is greater than zero in every challenger validation fold.
7. Positive IC share is at least 50% and no more than 3 percentage points below
   the active model.
8. Consecutive-rank correlation is no more than `0.05` below the active model.
9. Mean monthly turnover is no more than `0.10` above the active model and does
   not exceed `0.75`.
10. Cumulative 20-bps benchmark-relative return is at least the active model's
    value on the same formations.
11. Positive month share is at least 50% and no more than 5 percentage points
    below the active model.
12. MAE and RMSE are each no more than 2% above the active model.

These are challenger-selection gates, not public-performance or deployment
approval gates. Passing permits one immutable challenger to be frozen for the
Phase 10 shadow comparison. It does not replace the active model.

## Deterministic selection

P9.4 may compare only candidate families and parameter grids committed before
their results are generated. Candidates failing any gate are rejected. If more
than one passes, select lexicographically by:

1. highest mean daily Spearman IC;
2. highest top-minus-bottom spread;
3. lowest mean monthly turnover;
4. lowest RMSE;
5. ascending stable model version.

Do not average away a failed gate, choose a favorable subset of dates, or change
thresholds after observing a result. All candidate metrics, failures, source
hashes, and exclusions remain in the immutable experiment artifact.

## Interpretation boundary

Tier-B selection remains survivorship-biased private research. Neither a passed
development comparison nor a later shadow result guarantees that a stock or
basket will outperform SPY.
