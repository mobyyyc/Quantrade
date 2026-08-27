# Model Prediction Context

## Scope

This context applies to `tier_b_regularized_linear_development_v1` and its 20-session return target relative to SPY. It describes forecast uncertainty for the monthly equal-weight top-20 research portfolio. It does not change rankings, portfolio membership, or stored raw predictions.

## Development-only method

- Replayed the frozen selected elastic-net specification through the existing three purged chronological development folds.
- Generated 173,047 out-of-fold stock predictions from December 26, 2023 through June 30, 2025.
- On the final validation session of each calendar month, selected the top 20 raw predictions and averaged their completed benchmark-relative outcomes.
- Evaluated 19 monthly formations.
- Kept the consumed July 2025 through June 2026 holdout completely outside calibration fitting.

## Result

The monthly development baskets did not produce a positive calibration slope. Quantrade therefore does not transform the raw model percentage into a calibrated expected return.

The empirical 10th-to-90th percentile error range around raw monthly basket output was:

- Lower residual: −6.12 percentage points.
- Upper residual: +5.96 percentage points.

The Research page retains this development diagnostic. The monthly basket does
not present the raw output as an expected return; it reports only completed
realized basket and SPY outcomes from the preceding official portfolio.

## Limitations

- Nineteen monthly formations are a small calibration sample.
- Twenty-session outcomes from adjacent monthly formations can overlap and are not fully independent.
- Tier B current-survivors data remains survivorship-biased and uses static current-sector classifications.
- The consumed holdout may be reported as evaluation evidence, but it cannot be used to fit or select this calibration.
