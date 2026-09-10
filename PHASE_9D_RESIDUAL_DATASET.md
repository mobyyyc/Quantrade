# Phase 9D anchored-residual dataset — September 10, 2026

Status: P9D.2 complete; authenticated development dataset ready for P9D.3.

Dataset key: `phase_9d_anchored_residual_development:v1`

## Outcome

The model-ready residual dataset was built from the existing authenticated Phase
9C weekly features, corporate-action-aware 20-session labels, registered folds,
and clean monthly elastic-net inputs. No provider data was downloaded, no raw SEC
artifact was regenerated, PostgreSQL was read-only, and the live model and scores
were not changed.

The dataset contains 54,544 company-week examples across 121 formations from
January 6, 2023 through May 23, 2025. It covers 495 of the fixed 500 current-
survivor companies. Each row contains:

- a chronological cross-fitted elastic-net anchor prediction and centered rank;
- the frozen label-centered rank and residual target (`label - anchor`);
- only the registered investment/issuance and profitability/quality family
  values as potential model inputs;
- the original 20-session benchmark-relative return for later attribution;
- monthly-balanced sample weight, outer-fold membership, and complete source,
  label, anchor-fit, and row hashes.

Availability diagnostics are retained for auditing but are explicitly excluded
from the model inputs.

## Chronological construction

The October–December 2022 inner block is used only to tune later anchors and is
not admitted as residual-training data. The first residual examples begin in
January 2023. Before every prediction episode:

1. monthly elastic-net preprocessing and coefficients are fit on earlier rows;
2. only completed outcomes strictly before that episode's start may select its
   elastic-net configuration; and
3. the selected raw predictions are ranked across the full eligible historical
   peer universe before labels are joined.

The latest tuning outcome precedes its prediction cutoff in every episode. For
example, the January 6, 2023 episode uses outcomes through January 4 only; the
January 3, 2025 outer block uses outcomes through December 31, 2024 only.

The original Phase 9C fold hash is preserved. Outer validation coverage is:

| Outer block | Dataset rows |
| --- | ---: |
| Jul–Dec 2023 | 11,555 |
| Jan–Jun 2024 | 11,643 |
| Jul–Dec 2024 | 11,663 |
| Jan–May 2025 | 9,967 |

The consumed July 2025–June 2026 holdout was not read.

## Exclusions and coverage

Of 82,551 authenticated Phase 9C label rows:

- 22,401 precede the first honest cross-fitted anchor and are explicitly
  excluded for insufficient earlier tuning history; and
- 5,606 lack an input required by their selected fold-local elastic-net fit.

The investment/issuance family is informative for 99.88% of included rows, with
99.15% minimum formation coverage. Profitability/quality is informative for
97.41%, with 96.20% minimum formation coverage. Both exceed the registered 80%
aggregate and 70% per-formation gates.

All dataset integrity gates passed: no holdout access, no label overlap,
no anchor-selection outcome overlap, complete lineage, preserved folds, and
monthly weights summing to one.

## Reproducibility

Two complete materializations produced identical artifacts:

- dataset SHA-256: `db816c27deefcc80cac10946ad1980678d650c8ff42b01217bd278d5b695b199`;
- logical row SHA-256: `7210632d6a5c6f11d63a0c25505160ddbd11a1134dc1df7cf63b080564e7b25b`;
- anchor manifest SHA-256: `2af641bd2abc3a81b3f75bec92593930347988459be1987f2896bc3644a29d44`;
  and
- report SHA-256: `090904dda4a51d4c46c6176baa9ac85d6068c30c7454a4e4c4578e011f265de8`.

The fail-closed loader independently verified all 54,544 row hashes, artifact
hashes, residual arithmetic, positive weights, monthly weight totals, partitions,
fold identifiers, date boundaries, and manifest hashes.

Canonical local artifacts are:

- `data/derived/phase_9d_anchored_residual_development_v1.csv.gz`;
- `data/derived/phase_9d_anchored_residual_development_v1.anchors.json`; and
- `data/derived/phase_9d_anchored_residual_development_v1.json`.

Rebuild from the repository root with PostgreSQL and `.env` available:

```powershell
py -3.14 -m quantrade_research.phase_9d_residual_dataset --env-file .env
```

The builder refuses to overwrite existing immutable outputs.

## Evidence boundary

No ridge challenger was fit and no outer challenger-performance result was
evaluated in P9D.2. Earlier inner outcomes were used only where required to
select the chronological elastic-net anchors.
The data remain Tier-B, survivorship-biased research with static present-day
sectors. Reused development history can qualify a future candidate only for
forward shadow collection; it cannot independently justify deployment or a
public performance claim.
