# Next-Generation Model Comparison

## Decision

P9.4 is complete. No tested challenger passed the pre-registered development
gates, so no challenger is eligible to be frozen or promoted. The active
elastic-net model remains the research model.

This is a development-only Tier B result. The July 2025 through June 2026
holdout was not opened or used.

## Common sample

- Source development rows: 341,944
- Common-sample rows: 338,189 (98.90% coverage)
- Historical formation dates: 875
- Purged expanding validation folds: 3
- Validation observations: 171,041 across 378 score dates
- Monthly portfolio formations evaluated: 19
- Candidate features: 60-day downside-volatility percentile and year-over-year
  return-on-assets-change percentile
- Dataset SHA-256: `3453339bf14569fcb04df48db0386aae1a7d5bb6e887b5957b1a9a7b9f6643f8`
- Combined feature-registry hash:
  `9f2901f581af7ffdf1d250086a8b422c1dce28da2666305ef5c5ec5b68f968fe`

Rows without both candidate ranks were withheld. The dataset remains subject to
the fixed-current-survivors and static-sector Tier B limitations.

## Results

| Model | Mean daily IC | Top-bottom spread | Return after 20 bps | Positive months | Freeze eligible |
| --- | ---: | ---: | ---: | ---: | --- |
| Active elastic-net refit | 0.0310 | 0.0086 | 0.0868 | 68.42% | Reference |
| Huber, delta 1.0, L2 0.01 | 0.0229 | 0.0117 | 0.2685 | 63.16% | No |
| Huber, delta 1.0, L2 0.1 | 0.0230 | 0.0117 | 0.1784 | 57.89% | No |
| Huber, delta 1.5, L2 0.01 | 0.0237 | 0.0116 | 0.2620 | 57.89% | No |
| Huber, delta 1.5, L2 0.1 | 0.0239 | 0.0117 | 0.2931 | 57.89% | No |
| Boosted stumps, 24 at 0.05 | 0.0242 | 0.0061 | 0.0041 | 52.63% | No |
| Boosted stumps, 36 at 0.03 | 0.0229 | 0.0059 | -0.0301 | 47.37% | No |
| Pairwise ranker, L2 0.001 | -0.0004 | 0.0012 | -0.3057 | 47.37% | No |
| Pairwise ranker, L2 0.01 | -0.0004 | 0.0012 | -0.3298 | 42.11% | No |

The robust models improved simulated spread and post-cost return, but all had
lower mean rank IC than the active reference and missed the positive-month gate.
The boosted candidates also failed fold-stability and/or cost gates. Both
pairwise rankers produced slightly negative IC and failed multiple gates.

## Reproducibility

The complete experiment was run twice from the immutable common-sample dataset.
Both JSON outputs had file SHA-256
`94f4f788c5b052fb1e562ddc22b12954870b2338b5d43001e7c580758bbcbcd3`
and result hash
`28ba13c3f05ff1e0c2c6456649e213882cd45458678aa7f74c1a6b5abb78769a`.

## Consequence

P9.5 cannot freeze a challenger from this comparison. A future challenger must
be based on a new pre-registered hypothesis and must pass the same gates without
tuning against the consumed holdout.
