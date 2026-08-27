# Regime-Interaction Challenger Protocol: `active_linear_spy_regime_interactions_v1`

## Registration status

Pre-registered on 2026-08-27 before feature materialization, fitting, or result
inspection. This protocol defines one challenger and one decision path. A failed
result is final for this version; its features, penalties, thresholds, or sample
may not be changed to rescue it.

The active `tier_b_regularized_linear_development_v1` elastic-net model remains
the reference. This task does not train a model, open the locked July 2025
through June 2026 holdout, or change user-visible rankings.

## Hypothesis

The active model's cross-sectional price signals vary with the broad market
trend. Allowing only the existing momentum and relative-strength coefficients
to interact with a point-in-time SPY trend signal will improve development-set
ranking quality, specifically in range-bound markets, without materially
damaging stability, forecast error, turnover, or cost robustness.

This hypothesis follows the development-only diagnostic in
`ACTIVE_MODEL_DEVELOPMENT_ERROR_ANALYSIS.md`: the active model's mean daily rank
IC was -0.0002 in range-bound markets, versus 0.0265 in bullish markets and
0.1867 in bearish markets. The sector diagnostic is not used to define a
challenger because the free cohort has static, non-point-in-time sectors.

## Frozen point-in-time regime signal

For score date `t`, use SPY split-adjusted regular-session closes through `t`
only when every contributing bar has `available_at <= 8:00 p.m.
America/Toronto` on that decision date.

Define the continuous regime signal as:

`market_trend_60d = clip(SPY_close_t / SPY_close_t_minus_60_sessions - 1, -0.30, 0.30) / 0.30`

The result is bounded to `[-1, 1]`. No future bar, revised later snapshot, macro
series, sector label, or ex-post regime classification may enter the feature.
A row without the full 60-session SPY window is excluded from both models.

## Frozen challenger

The challenger uses the active six features unchanged and adds exactly two
interaction columns:

1. `momentum_12_1_market_trend_interaction_v1` =
   `(momentum_12_1_percentile - 0.5) * market_trend_60d`
2. `relative_strength_6m_market_trend_interaction_v1` =
   `(relative_strength_6m_percentile - 0.5) * market_trend_60d`

Fit one elastic-net challenger with `l1=0.001` and `l2=0.01`, matching the
active model. There is no parameter grid, standalone regime feature, nonlinear
learner, imputation, feature selection, or coefficient-sign constraint. The
active reference is refit inside each fold with its original six features.

## Common sample and evaluation

- Use only development observations before 2025-07-01.
- Use the same completed 20-session SPY-relative target, three expanding
  chronological folds, and 20-session purge as the active comparison.
- Compare both models on identical securities, score dates, labels, monthly
  formations, execution marks, and exclusions.
- Preserve `sp500_current_survivors_v1` Tier-B survivorship warnings.
- Require at least 90% challenger-feature coverage and zero point-in-time
  violations.
- Reuse every measurement, cost assumption, and challenger freeze gate in
  `NEXT_GENERATION_MODEL_EVALUATION_PROTOCOL.md`.

Range-bound days are frozen as those with an unclipped 60-session SPY return
strictly between -5% and +5%, matching the diagnostic definition. In addition
to the existing gates, the challenger must achieve range-bound mean daily rank
IC of at least 0.005 and improve it over the active reference by at least 0.005
on the identical range-bound observations.

## Decision rule

The hypothesis passes only if the single challenger:

1. passes all twelve existing challenger freeze gates;
2. passes both range-bound IC thresholds above;
3. produces byte-identical results in two independent runs; and
4. reports no unresolved data-quality or provenance exception.

Failure of any condition rejects `active_linear_spy_regime_interactions_v1`.
Passing permits an immutable challenger artifact to be frozen for Phase 10
shadow scoring; it does not replace the active model or authorize a performance
claim.

## Prohibited actions

- Do not inspect or tune against the locked holdout.
- Do not add another interaction, feature, model family, or hyperparameter.
- Do not alter the regime boundaries or clipping limit after seeing results.
- Do not select favorable sectors, volatility groups, dates, or folds.
- Do not calibrate predictions or relax a failed gate after evaluation.

