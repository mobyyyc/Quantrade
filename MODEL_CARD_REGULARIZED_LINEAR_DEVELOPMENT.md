# Model Card: `tier_b_regularized_linear_development_v1`

## Status

**Frozen source model. Private-beta approved through a separate immutable
decision.** This original card remains `research_only` so its development-time
state is not rewritten. The effective lifecycle status comes from the linked
private-beta approval decision and corrected deployment event.

## Purpose

Test whether the six existing point-in-time percentile features contain a
small, regularized signal for a future 20-session return relative to SPY. This
is an early model-selection experiment, not an investment recommendation or a
validated forecast.

## Data and target

- Dataset: `sp500_current_survivors_20d@v1`.
- Cohort: `sp500_current_survivors_v1`, a fixed cohort of current S&P 500
  survivors. It is explicitly **not** historical index membership.
- Capability: **Tier B**. Static current-sector groupings and survivorship bias
  mean this cannot support an unbiased historical-performance claim.
- Development examples: 341,944, dated 2022-01-03 through 2025-06-30.
- Target: completed 20-session split-adjusted return relative to SPY.
- Inputs: earnings yield, median dollar volume, 12-1 momentum, six-month
  relative strength, return on assets, and 60-day trailing volatility—each as
  the dated sector-percentile feature already used by the baseline.

## Selection procedure

- Evaluated ridge and elastic-net candidates on three chronological validation
  windows.
- Before each validation window, excluded the immediately preceding **20 market
  sessions** from training.
- Used mean validation RMSE as the selection metric; mean absolute error is
  recorded as a secondary diagnostic.
- The entire locked period, 2025-07-01 through 2026-06-30, was excluded before
  loading examples. `holdout_used=false` is recorded in the immutable local
  result.

## Development result

The selected configuration was elastic net with L1 penalty `0.001` and L2
penalty `0.01`:

| Measure | Value |
| --- | ---: |
| Mean validation RMSE | 0.07793606 |
| Mean validation MAE | 0.05709397 |
| Validation windows | 2023-12-26–2024-06-26; 2024-06-27–2024-12-24; 2024-12-26–2025-06-30 |

These are target-prediction errors, not portfolio returns, Sharpe ratios, or
evidence of investability. The selection margin versus several alternatives is
small and must not be over-interpreted.

## Important limitations

- This is a current-survivors Tier-B dataset; delisted companies and historical
  membership changes are absent.
- The like-for-like holdout comparison and 1/5/10/20-bps cost sensitivities are
  complete. The 20-bps candidate result passed the private-beta cost gate.
- Holdout integrity passed using provider total-return-adjusted prices and the
  recorded corporate-action coverage audit.
- The final development artifact is the active private-beta inference artifact;
  its bytes and SHA-256 digest remain unchanged.
- Approval is Tier B and private only. It is not an unbiased historical result,
  a public-performance approval, an expected-return calibration, or a guarantee.

## Required next gates

The frozen specification, shared comparison, single holdout evaluation,
integrity audit, and private-beta policy review are complete. Future work uses
new forward paper outcomes or a separately pre-registered challenger. The
consumed holdout cannot be reopened for tuning.

## Reproducibility record

The local immutable result is
`data/derived/experiments/tier_b_regularized_linear_development_v1.json`; the
append-only database experiment key is
`tier_b_regularized_linear_development_v1`.

The effective approval record is
`data/derived/governance/tier_b_regularized_linear_private_beta_approval_v1.json`.
