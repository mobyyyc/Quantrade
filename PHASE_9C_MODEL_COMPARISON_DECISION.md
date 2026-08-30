# Phase 9C nested model comparison decision

Status: **complete for P9C.6; fitted artifacts advance to portfolio attribution, not promotion**

## What was fit

The comparison consumed only the authenticated Phase 9C weekly development
dataset and its registered nested chronological folds. The July 2025–June 2026
holdout was not read.

Four model paths were produced:

1. `deployed_active_exact` replays the immutable deployed
   `tier_b_monthly_elastic_net_sec_clean_v3` artifact without refitting. Its
   original six sector-percentile inputs, means, scales, target mean, and
   coefficients are preserved.
2. `active_family_refit` uses those same six inputs but refits a ridge rank
   model under the Phase 9C weekly protocol. This isolates training-protocol
   changes from feature changes.
3. `phase9c_family_ridge` fits the six frozen Phase 9C economic-family values.
4. `phase9c_pairwise_linear` fits the same six families with deterministic,
   normalized, 64-pair-per-formation logistic rank training.

The optional additive model was not activated. The candidate search therefore
used 8 configurations against the frozen budget of 12: four penalties each for
ridge and pairwise linear models.

## Exact active-reference reconstruction

The active reference is not given the improved Phase 9C accounting semantics.
Its historical inputs are reconstructed with the deployed feature definitions:

- split-adjusted 12-1 momentum, six-month relative strength, and 60-session
  realized volatility;
- unadjusted 20-session median dollar volume;
- annual SEC net income with the deployed concept fallback, eligible shares,
  and annual-period asset endpoints; and
- the current sector classification as the explicitly disclosed static Tier-B
  grouping.

The model artifact is loaded through the immutable deployment registry and its
content hash is verified before scoring. Active-reference coverage is 92.37%
of development examples; missing required active inputs remain unavailable
rather than being imputed. Phase 9C family models retain the approved neutral
missing-value treatment from the model dataset.

## Selection discipline

- Every outer fold selects its penalty using only its three registered earlier
  inner validation blocks.
- Mean weekly Spearman IC is calculated first within formation and then given
  equal weight by calendar month.
- A penalty within 0.002 of the best inner score loses to the larger penalty.
- Outer predictions are emitted only for the next attribution and gate steps;
  no outer result changes a fit or configuration.
- Each calendar month has aggregate fit weight one.

## Preliminary outer diagnostics

These are recorded for audit and must not be used to revise the models:

| Model | Mean monthly rank IC |
| --- | ---: |
| Exact deployed active artifact | 0.02552 |
| Active-family weekly refit | 0.00516 |
| Phase 9C family ridge | 0.01374 |
| Phase 9C pairwise linear | 0.00030 |

The Phase 9C ridge is positive in aggregate, but these figures alone do not
authorize model selection or deployment. P9C.7 must apply identical portfolio
construction to every path, and P9C.8 must evaluate all frozen gates, paired
uncertainty, stability, coverage, and economic results. In particular, the
challenger has not yet demonstrated improvement over the exact deployed
reference.

## Artifacts

Local, derived artifacts (ignored by Git) are:

- `data/derived/phase_9c_nested_weekly_rank_predictions_v1.csv.gz`
- `data/derived/phase_9c_nested_weekly_rank_predictions_v1.fits.json`
- `data/derived/phase_9c_nested_weekly_rank_predictions_v1.json`

The manifest records the dataset, fold, deployed-artifact, reconstructed input,
fit, and prediction hashes; the static-sector limitation; the configuration
budget; and explicit `holdout_used=false` and
`outer_results_used_for_selection=false` assertions.
