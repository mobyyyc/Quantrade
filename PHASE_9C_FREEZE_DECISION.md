# Phase 9C Frozen Gate Decision

Decision: **no-freeze**

Evaluation key: `phase_9c_frozen_gate_evaluation@v1`

Research tier: B, private current-survivors research

## Outcome

Neither registered Phase 9C challenger cleared every immutable gate. No Phase
9C model replaces the deployed active model, and Phase 10 remains blocked by
its requirement for a qualifying frozen challenger.

The July 2025 through June 2026 consumed holdout was not read. No model was
refit, no candidate was added, and no threshold was changed after seeing the
results.

## Primary ridge challenger

The family-shrunk ridge candidate failed gates 1, 3, 4, 5, 7, and 8.

- Paired mean monthly rank IC: `0.00561`
- Deployed reference IC on the identical paired sample: `0.02552`
- Paired IC delta: `-0.01991`
- Positive outer IC blocks: `2 of 4`
- Worst outer-block IC: `-0.04776`
- Three-month moving-block bootstrap probability of a positive IC delta:
  `11.24%` from 10,000 deterministic resamples
- Bootstrap 95% percentile interval: `[-0.05198, 0.01128]`
- Mean monthly top-minus-bottom spread: `+0.00262`
- Candidate 25-bp net relative return in its eight completed periods:
  `+0.00885` per month
- Paired 25-bp net relative-return delta across the three periods where both
  portfolios had complete outcomes: `-0.01589` per month
- Mean recurring one-way turnover: `0.40652`, which is below the absolute
  `0.42` ceiling but `0.07826` above the same-construction reference and thus
  exceeds the allowed `+0.03`
- Consecutive rank stability: `0.95411`
- All six family signs were consistent in at least three of four fits

The candidate's positive unpaired portfolio average cannot override the
negative fair-comparison evidence or the other hard failures. Only three
completed portfolio months were shared with the deployed reference, and their
paired result was materially negative.

## Pairwise-linear backup

The pairwise candidate failed gates 1, 3, 4, 5, 6, 7, 8, and 10.

- Paired mean monthly rank IC: `-0.00642`
- Deployed reference IC on the identical paired sample: `0.02552`
- Paired IC delta: `-0.03194`
- Positive outer IC blocks: `2 of 4`
- Worst outer-block IC: `-0.04143`
- Bootstrap probability of a positive IC delta: `8.79%`
- Bootstrap 95% percentile interval: `[-0.07384, 0.01685]`
- Mean monthly top-minus-bottom spread: `-0.00122`
- Candidate 25-bp net relative return in its fourteen completed periods:
  `+0.00714` per month
- Paired 25-bp net relative-return delta across eight shared completed
  periods: `-0.00068` per month
- Mean recurring one-way turnover: `0.48913`, above both turnover limits
- Consecutive rank stability: `0.94341`
- Momentum/trend coefficient signs split two positive and two negative fits

## Integrity and reproducibility

All included feature lineage and label-overlap audits remained clean, source
artifact hashes were validated, and the consumed holdout remained isolated.
The evaluator is deterministic and uses seed `20260828`, a three-calendar-month
moving block, and 10,000 paired resamples.

However, the frozen protocol required the numeric bootstrap seed to be
persisted before fitting and did not actually record one. The evaluation seed
makes this result replayable but cannot retroactively satisfy the registration
contract. Gate 1 therefore fails for both challengers. This omission does not
change the model conclusion: both challengers independently fail several
substantive ranking, portfolio, and turnover gates.

## Diagnostic boundaries

The SPY trend and volatility slices are diagnostics only. They did not select a
model or alter a gate. Current sectors remain static Tier-B groupings, and the
cohort remains survivorship biased. These results are private research and do
not establish or guarantee future outperformance of SPY.

The immutable machine-readable decision is stored locally at
`data/derived/phase_9c_frozen_gate_evaluation_v1.json` and is authenticated by
its `report_sha256`.
