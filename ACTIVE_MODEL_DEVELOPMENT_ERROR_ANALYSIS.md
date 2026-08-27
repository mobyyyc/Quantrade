# Active-Model Development Error Analysis

## Scope

This report diagnoses the active elastic-net model on purged, out-of-fold
development predictions only. The locked July 2025 through June 2026 holdout
was not opened, and no model or user-visible score changed.

## Overall validation behavior

- Observations: 171,041 across 378 dates
- Mean daily rank IC: 0.0310
- MAE: 5.71%
- RMSE: 7.81%
- Mean prediction error: 0.20%
- Directional accuracy: 52.88%

## Sector

| Segment | Observations | Rank IC | IC delta | MAE | MAE delta | Mean error |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Energy | 7,522 | -0.0435 | -0.0745 | 6.50% | 0.79% | 0.63% |
| Health Care | 21,184 | -0.0119 | -0.0429 | 6.19% | 0.48% | 1.42% |
| Real Estate | 10,962 | 0.0110 | -0.0200 | 4.97% | -0.74% | 0.95% |
| Utilities | 11,676 | 0.0141 | -0.0169 | 5.93% | 0.22% | -0.19% |
| Information Technology | 25,256 | 0.0332 | 0.0022 | 6.65% | 0.94% | -0.41% |
| Materials | 8,737 | 0.0397 | 0.0087 | 5.42% | -0.29% | 0.89% |
| Communication Services | 4,536 | 0.0444 | 0.0134 | 5.73% | 0.01% | -0.59% |
| Consumer Discretionary | 15,120 | 0.0445 | 0.0135 | 6.30% | 0.59% | -0.04% |
| Financials | 26,502 | 0.0502 | 0.0192 | 4.63% | -1.08% | -0.27% |
| Consumer Staples | 9,877 | 0.0612 | 0.0302 | 5.69% | -0.02% | 0.91% |
| Industrials | 29,669 | 0.0909 | 0.0599 | 5.32% | -0.39% | -0.16% |

## Stock volatility

| Segment | Observations | Rank IC | IC delta | MAE | MAE delta | Mean error |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| high | 61,582 | -0.0127 | -0.0438 | 4.71% | -1.00% | 0.22% |
| low | 53,363 | 0.0102 | -0.0208 | 7.11% | 1.40% | 0.05% |
| middle | 56,096 | 0.0218 | -0.0092 | 5.49% | -0.23% | 0.32% |

## Market regime

| Segment | Observations | Rank IC | IC delta | MAE | MAE delta | Mean error |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| range_bound | 71,613 | -0.0002 | -0.0312 | 5.66% | -0.05% | 0.18% |
| bullish | 82,528 | 0.0265 | -0.0045 | 5.55% | -0.17% | 0.11% |
| bearish | 16,900 | 0.1867 | 0.1557 | 6.74% | 1.02% | 0.75% |

## Diagnostic priorities

- Sector: `Energy` had the weakest descriptive rank IC (-0.0435); `Information Technology` had the largest MAE (6.65%).
- Stock volatility: `high` had the weakest descriptive rank IC (-0.0127); `low` had the largest MAE (7.11%).
- Market regime: `range_bound` had the weakest descriptive rank IC (-0.0002); `bearish` had the largest MAE (6.74%).

These are hypothesis-discovery diagnostics, not independent statistical trials.
They do not authorize a feature, model change, or performance claim. The next
research cycle must pre-register one targeted hypothesis before fitting it.

## Provenance

- Dataset SHA-256: `3453339bf14569fcb04df48db0386aae1a7d5bb6e887b5957b1a9a7b9f6643f8`
- Feature-registry hash: `9f2901f581af7ffdf1d250086a8b422c1dce28da2666305ef5c5ec5b68f968fe`
- SPY lineage SHA-256: `e0daf489f6f5e10985c410fb0ccf9fd971658e87c9f46893274a6ed7623ef002`
- Result SHA-256: `eefe5d9ca9142ab0e9e3cf7a69213210833bac00332c78ec82a2e06f5a44d175`
- Sector warning: current static Tier-B sectors are not historical point-in-time classifications.
