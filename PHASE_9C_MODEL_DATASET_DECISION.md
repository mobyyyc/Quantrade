# Phase 9C Weekly Model-Dataset Decision

Date: 2026-08-30
Status: **pass; P9C.5 complete**

## Decision

Quantrade freezes `phase_9c_weekly_rank_development_v1` as the label-safe
development dataset and `phase_9c_nested_chronological_actual_outcome_purge_v1`
as its fold specification. The dataset may be used by P9C.6 for the registered
reference and challenger fits. It does not replace the deployed model and it
contains no July 2025–June 2026 holdout observation.

Each included example joins the immutable P9C.4 feature row to an explicit
next-open wealth label:

- entry is the next regular-session open after the weekly formation;
- exit is the open after 20 completed sessions;
- ordinary cash dividends and splits are handled by the P9C.2 wealth ledger;
- the raw outcome is stock wealth return minus matching SPY wealth return; and
- the model target is that outcome's tie-aware same-formation centered rank in
  `[-1, 1]`.

Provider-adjusted returns never replace the explicit development label. The
P9C.2 July 2025–June 2026 provider-control audit validates the ledger engine;
the development rows retain the ledger's exact 21 stock marks, 21 SPY marks,
action identifiers, ledger hashes, and label hash.

## Fail-closed eligibility

A row is included only when its P9C.4 feature row is score eligible and both
the stock and SPY have a complete 21-mark unadjusted path. Unknown, undated,
incomplete, or complex corporate actions and unexplained structural price
discontinuities are withheld rather than repaired.

The existing score-coverage thresholds were applied symmetrically to label
coverage before any outcome or model metric was inspected: at least 95%
aggregate label coverage and at least 90% completed-label coverage in every
retained weekly cross-section.

The audit found an incomplete Alpaca session on 2022-03-08. A missing-only
source retry left unadjusted coverage at 148 of the fixed 500 securities, so no
interpolation or adjusted-price substitution was used. The five weekly windows
whose 20-session paths crossed that session were excluded in full:

- 2022-02-04;
- 2022-02-11;
- 2022-02-18;
- 2022-02-25; and
- 2022-03-04.

The final six P9C.4 formations were also excluded because their outcomes reach
the consumed holdout beginning 2025-07-01.

## Dataset audit

The frozen development dataset contains 82,551 rows across 172 weekly
formations. Completed-label coverage among feature-eligible rows is 97.74%,
and the minimum retained formation coverage is 91.52%.

| Exclusion class | Candidate rows/windows |
| --- | ---: |
| Feature row not score eligible | 1,615 |
| Formation below label-coverage gate | 689 completed candidates withheld with the formation |
| Label window reaches consumed holdout | 3,000 |
| Missing complete stock price path | 1,746 |
| Undated corporate action | 67 |
| Unexplained structural price discontinuity | 1,544 |
| Cash merger | 111 |
| Stock-and-cash merger | 29 |
| Stock dividend | 4 |
| Stock merger | 144 |

All 82,551 serialized rows and all 82,551 label-lineage records were read back
successfully with zero hash, key, schema, range, partition, or lineage
violations. Every represented calendar month has aggregate sample weight one.
Reconstructing the fixed replay label produced the same hash.

- Dataset file SHA-256: `d8b4bdc7d56c1cafe51585dea7db5a339163354e7b3cb5914cd03e7586481587`
- Dataset logical SHA-256: `3c4f76cf70b8e346279481fbc3e0f56a35dfba6f67eb0f9b77307ec943f9074d`
- Label-lineage SHA-256: `526841a9702c724909b8072036d9a06b45484f962b9b212feec11adc377eb886`
- Fold file SHA-256: `67536af96ff9b31dc1395e4766750715d8f23d4488219e4c7e2c3d5b37bc5194`
- Fold logical SHA-256: `6e9ea3c770b8f0eaf69ccc809cf405b71a21d83bc86fb0787f890345a93e62a9`
- Fixed-label replay SHA-256: `588635b2021210145c8873a827db2a3b2ebafbf619903ec5cb0269bd55abbec5`
- Audit report SHA-256: `f0dc1eccce537361a7130affdd96f0959944331436892d921bfb90080b861dbc`

The generated dataset, manifest, label lineage, and fold manifest remain local
derived artifacts under `data/derived/phase_9c_weekly_rank_development_v1.*`.

## Nested chronological folds

The four frozen outer blocks contain 26, 26, 26, and 21 weekly validation
formations. Their training sets contain 69, 95, 121, and 147 formations. Four
immediately preceding formations are purged at every outer boundary because
their realized outcome reaches or crosses the next validation start.

Each outer fold contains three continuous inner validation blocks drawn from
its last nine eligible training months. Every inner and outer split applies the
same rule: a training row's actual `outcome_date` must be earlier than the
validation formation date. The audit found zero overlap violations across all
four outer and twelve inner folds.

## Limitations

This remains private Tier-B current-survivor research and is survivorship
biased. The missing March 2022 provider cross-section creates a deliberate gap
in the training calendar. Corporate-action and structural-jump exclusions can
also be non-random; their counts must accompany every later result. The
consumed holdout remains report-only and cannot choose P9C.6 features,
hyperparameters, models, or thresholds.

## Consequence

P9C.6 may replay the exact deployed artifact, refit the active family under
these same weekly folds, and fit only the pre-registered ridge-rank,
pairwise-linear, and optional low-DF additive challengers. Model selection must
use the nested development folds only.
