# Phase 9C monthly portfolio attribution decision

Status: **complete for P9C.7; attribution advances to frozen gate evaluation, not promotion**

## Construction

P9C.7 scores the final regular market session of each calendar month using the
already-fitted outer-fold models from P9C.6. Weekly predictions are not treated
as month-end predictions, no model is refit, and no hyperparameter or portfolio
rule is selected from these results.

Every model is evaluated under both frozen rules:

1. current Top 20, equal weighted; and
2. retain prior holdings still ranked in the current Top 30, fill vacancies
   from the current ranking, and return to 20 equal-weight names.

Entry is the next regular-session open. The result is measured through 20
completed sessions with the same corporate-action-aware stock and SPY wealth
ledger used by the Phase 9C dataset. One-way turnover is
`1 - retained / 20`; net sensitivity subtracts turnover times 5, 10, 25, or
50 basis points. No selected stock is replaced after its outcome is observed.

## Attribution summary

Descriptive path results use every completed formation available to that exact
model/rule path. Direct effects use only paired dates shared by the two paths
being compared.

| Model | Exact completed months | Exact gross relative / month | Exact recurring turnover | Buffered completed months | Buffered recurring turnover |
| --- | ---: | ---: | ---: | ---: | ---: |
| Exact deployed artifact | 9 | +0.09% | 33.75% | 8 | 24.29% |
| Active-family weekly refit | 13 | -0.17% | 39.17% | 13 | 30.42% |
| Phase 9C family ridge | 8 | +0.98% | 35.71% | 9 | 21.88% |
| Phase 9C pairwise linear | 14 | +0.84% | 45.38% | 14 | 35.77% |

Buffering lowers recurring turnover for every model. It does not reliably
improve gross return: the paired gross effect is approximately +0.16 percentage
points per month for the deployed reference, -0.02 for the active-family refit,
-0.28 for the family ridge, and -0.60 for the pairwise model. P9C.8 must keep
this portfolio-rule effect separate from model improvement.

The apparently strong standalone ridge return is not a fair model comparison.
Only three completed exact-Top-20 months overlap its deployed-reference path,
and on those paired dates its mean gross relative return is approximately 1.56
percentage points per month lower. The pairwise model has eight paired dates
and is approximately 0.02 percentage points per month below the deployed
reference. These sparse diagnostics do not authorize promotion.

## Fail-closed outcome coverage

The feature inference contains 24 true month ends. The final two cannot finish
their 20-session outcomes before the preserved July 2025 holdout. Among earlier
months, a portfolio is withheld when any selected name crosses an unresolved
complex corporate action, undated action, missing price path, or unexplained
structural discontinuity. The engine does not replace that name with the next
ranked stock because doing so after reading the outcome would leak future
information.

Consequently, only two months are completed across all eight model/rule paths.
P9C.7 does not use that two-month intersection as the main estimator. It uses
paired intersections for each specific model effect and buffer effect and
records the exact dates. The small paired sample—especially three months for
the primary ridge-versus-deployed comparison—is a material limitation for the
frozen P9C.8 gates.

## Reproducibility and provenance

The local derived artifact is
`data/derived/phase_9c_monthly_portfolio_attribution_v1.json`. It records:

- authenticated P9C.6 prediction, fit, and fold hashes;
- true month-end feature and active-reference source hashes;
- complete ranking hashes and selected security IDs for each path and month;
- entry and outcome dates, selected label hashes, exclusions, turnover,
  additions, removals, and returns;
- paired model and portfolio-rule attribution dates; and
- explicit `model_refit=false`, `model_selection_performed=false`,
  `holdout_used=false`, and `outer_results_used_for_tuning=false` assertions.

Two complete replays produced an identical attribution artifact hash. A
previous equal-key SEC fact lineage ambiguity was removed by using the
immutable fact ID as the final deterministic tie-breaker; it did not alter the
economic selection rule.
