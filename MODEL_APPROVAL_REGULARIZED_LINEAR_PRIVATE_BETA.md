# Private-Beta Approval: `tier_b_regularized_linear_development_v1`

## Decision

**Approved for private Tier-B research.** The frozen elastic-net artifact may
produce Quantrade scores, rankings, and monthly paper portfolios. This approval
does not authorize a public historical-performance claim, personalized advice,
or any guarantee of outperforming SPY.

The development-time model card remains immutable and `research_only`. An
append-only approval decision supplies the effective `private_beta_approved`
status, and the latest deployment event cites that exact decision artifact.

## Evidence applied to the fixed policy

| Gate | Evidence | Result |
| --- | ---: | --- |
| Point-in-time integrity | 0 violations | Pass |
| Unresolved data quality | 0 issues after the holdout integrity audit | Pass |
| Feature coverage | 463 / 500 minimum shared eligible names, 92.6% | Pass |
| Walk-forward validation | 3 purged chronological folds | Pass |
| Locked holdout | Evaluated once, 2025-07-01 through 2026-06-30 | Pass |
| 20-bps cost robustness | Candidate benchmark-relative return remained non-negative | Pass |
| Data capability | Tier B is permitted for private beta | Pass |

The exact numeric evidence, gate details, timestamps, and hashes are stored in
`data/derived/governance/tier_b_regularized_linear_private_beta_approval_v1.json`.
The file is generated from the frozen artifact, development experiment,
training manifest, holdout selection, holdout evaluation, and integrity audit.

## Interpretation limits

- The cohort contains current S&P 500 survivors, not verified historical index
  membership. Survivorship bias and static current-sector classifications remain.
- The holdout has been consumed. It is reporting evidence, not reusable training
  or tuning data.
- Raw model percentages are not calibrated expected returns.
- Future performance can differ materially. The model cannot guarantee that a
  stock or monthly basket will outperform SPY.
