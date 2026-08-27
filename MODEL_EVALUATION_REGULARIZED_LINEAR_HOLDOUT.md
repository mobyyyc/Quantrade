# Elastic-Net Holdout Prediction Evaluation

## Status

Completed reporting-only evaluation of `tier_b_regularized_linear_development_v1`
against the already-consumed July 1, 2025 through June 30, 2026 holdout.

This report does not authorize model tuning, feature selection, or a public
performance claim. The model remains a Tier-B private-beta research model.

## What was evaluated

- 116,396 completed stock-date examples across 251 score dates.
- Target: each stock's split-adjusted 20-session return minus SPY's return over
  the matching period.
- Predictions came from the frozen development artifact. It was not refit.
- The training CSV was verified against its immutable SHA-256 manifest before
  evaluation.
- The monthly top-20 summary uses the final eligible score date in each month.
  It is distinct from the separate next-open, total-return portfolio evaluator.

## Prediction accuracy

| Measure | Holdout result | Interpretation |
| --- | ---: | --- |
| Mean absolute error | 7.01 percentage points | Individual return estimates are imprecise. |
| Root mean squared error | 9.78 percentage points | Larger misses remain material. |
| Directional accuracy | 52.79% | Slightly better than an even-direction benchmark. |
| Pearson correlation | 0.0868 | Weak positive linear relationship. |
| Mean prediction | -0.163% vs SPY | Forecasts are tightly compressed around zero. |
| Mean actual outcome | -0.089% vs SPY | Average bias is small. |
| Mean prediction error | -0.074 percentage points | Limited average downward bias. |
| Calibration slope | 2.824 | Realized dispersion was much larger than forecast dispersion. |
| Prediction range | -0.709% to +0.409% | Raw estimates are under-dispersed and should not be read as precise targets. |

Development validation was stronger: MAE was 5.71 percentage points and RMSE
was 7.79 percentage points. Holdout MAE deteriorated by about 1.30 percentage
points and RMSE by about 1.98 percentage points.

## Ranking quality

| Measure | Holdout result |
| --- | ---: |
| Mean daily Spearman information coefficient | 0.0660 |
| Median daily Spearman information coefficient | 0.0673 |
| Score dates with positive information coefficient | 71.31% |
| Top prediction decile mean actual return vs SPY | +2.26% |
| Bottom prediction decile mean actual return vs SPY | -1.28% |
| Top-minus-bottom realized spread | +3.55 percentage points |

The evidence supports treating the model as a cross-sectional ranker. It does
not support treating the raw predicted percentages as accurate price targets.

## Monthly top-20 research basket

- 12 completed monthly formation dates were available for prediction-label
  diagnostics.
- The top-20 basket beat SPY in 8 of 12 periods, or 66.67%.
- Mean predicted relative return was +0.36% per 20-session period.
- Mean realized relative return was +3.17% per 20-session period.

The separate execution evaluator contains 11 fully contained next-open periods
and total-return corporate-action accounting. At a 20-basis-point cost case it
reported +85.31% for the candidate, +20.26% for SPY, and +65.05 percentage
points of cumulative relative return. These are portfolio results, not
individual prediction accuracy.

## Decision

Keep the current model active for private-beta ranking research. Do not present
its raw percentage output as a calibrated expected return. The next model
comparison should prioritize daily rank correlation, top-minus-bottom spread,
stability, turnover, and cost-aware portfolio behavior alongside MAE and RMSE.

Calibration changes must be developed using pre-holdout folds or new forward
data. This consumed holdout cannot be used to choose a calibration multiplier.

## Reproducibility

- Machine-readable report:
  `data/derived/holdout/tier_b_regularized_linear_prediction_diagnostics_v1.json`
- Report SHA-256:
  `abcc0a614c87ae5120e0859027ba5734daa159bf3beddef0e72c1c60d66b731c`
- Dataset:
  `data/derived/training/sp500_current_survivors_20d_v1.csv`
- Frozen model artifact:
  `data/derived/experiments/tier_b_regularized_linear_development_v1.json`

## Limitations

- Tier B uses a fixed cohort of current S&P 500 survivors and therefore has
  survivorship bias.
- Historical sector grouping is static rather than point-in-time.
- Overlapping daily 20-session labels are not independent portfolio trials.
- The holdout has been observed and is unavailable for future model selection.
