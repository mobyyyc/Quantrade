# Model Approval Policy

This policy governs promotion of a Quantrade research model after its locked
holdout evaluation. It is intentionally conservative and does not turn a score
into investment advice or a guaranteed-performance claim.

## Required gates

Every candidate must pass all of the following:

- Zero point-in-time violations and zero unresolved data-quality issues.
- At least three chronological walk-forward folds.
- At least 90% feature coverage in the approved evaluation universe.
- One final evaluation of the locked holdout period, including the 20-bps
  one-way-cost sensitivity.
- Non-negative benchmark-relative return in that 20-bps holdout sensitivity.

## Approval scopes

- `private_beta`: permits data capability Tier A or B when every required gate
  passes. Tier B output remains a research diagnostic and may not be presented
  as unbiased historical performance.
- `public_performance_claim`: requires Tier A plus every required gate. This is
  a governance threshold, not permission to make personalized investment claims.

Failed gates are recorded with their measured values. A model cannot be approved
by averaging away a failed integrity, coverage, holdout, cost, or data-capability
gate.
