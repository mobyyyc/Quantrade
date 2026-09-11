# Phase 9D anchored-residual readiness decision — September 10, 2026

Status: P9D.4 complete; immutable decision is `no-freeze`.

Candidate: `anchored_accounting_residual_ridge_v1`

Reference: chronological fold-local monthly elastic-net anchor

## Decision

The residual challenger does not qualify for forward shadow collection. It
passed data integrity, coverage, positive top-minus-bottom spread, and rank
stability gates, but failed six of the ten conjunctive preregistered gates. The
result cannot be reversed by relaxing thresholds after observing it.

No holdout row was opened, no outer result tuned the model, and no live artifact,
score, ranking, or portfolio was changed.

## Paired ranking evidence

The evaluation contains 44,828 paired company-week observations across 99
weekly formations and 23 calendar months.

| Measure | Candidate result | Frozen requirement | Result |
| --- | ---: | ---: | --- |
| Mean monthly rank IC | 0.02030 | at least 0.012 | pass |
| IC improvement over anchor | +0.00079 | at least +0.004 | fail |
| Positive outer blocks | 2 of 4 | at least 3 of 4 | fail |
| Worst outer-block IC | -0.02318 | greater than -0.020 | fail |
| Bootstrap probability of positive IC improvement | 65.12% | at least 90% | fail |
| Mean monthly top-minus-bottom spread | +0.00860 | positive | pass |
| Consecutive weekly rank stability | 0.96229 | at least 0.90 | pass |

The candidate's average IC was slightly higher than the anchor's 0.01951, but
the +0.00079 difference was too small and uncertain to establish the registered
incremental benefit. Its deterministic 95% bootstrap interval for the IC delta
was approximately -0.00217 to +0.00426.

## Identical-construction portfolio evidence

Both paths used true calendar month ends, exact Top 20 selection, equal weights,
next-session-open entry, 20 completed sessions, and a 25-bp one-way primary cost.
The buffered Top-20-entry/Top-30-retention path remained diagnostic only.

The conservative wealth ledger produced 12 completed candidate exact-rule
periods and 11 completed periods shared by both paths. A period is withheld when
any selected security lacks a valid corporate-action-aware outcome; incomplete
windows crossing the consumed holdout are also withheld.

| Measure | Candidate result | Frozen requirement | Result |
| --- | ---: | ---: | --- |
| Mean 25-bp net SPY-relative return | +0.00208 | positive | pass component |
| Paired net improvement over anchor | -0.00108 | at least +0.001 | fail |
| Positive net outer blocks | 3 of 4 | at least 3 of 4 | pass component |
| Recurring one-way turnover | 0.39565 | no more than 0.36 | fail |
| Turnover difference versus anchor | -0.00217 | no more than +0.01 | pass component |

Because every component is conjunctive, the positive standalone portfolio mean
does not rescue the negative paired comparison or excess absolute turnover.

## Coefficient stability

Profitability/quality was positive and material in all four outer fits. The
direction-adjusted investment/issuance coefficient was negative in all four,
instead of positive and material in at least three. The registered coefficient
gate therefore failed.

## Gate summary

Passed:

- gate 1 — point-in-time, lineage, overlap, holdout, hash, and deterministic
  integrity;
- gate 2 — score, family, and modeled raw-feature coverage;
- gate 6 — positive mean top-minus-bottom spread; and
- gate 9 — consecutive-rank stability.

Failed:

- gate 3 — required IC level and incremental improvement;
- gate 4 — outer-block consistency and worst-block floor;
- gate 5 — paired block-bootstrap confidence;
- gate 7 — exact-rule net portfolio improvement;
- gate 8 — absolute turnover; and
- gate 10 — correction-coefficient direction and materiality.

## Reproducibility and evidence boundary

Two complete evaluations, including database-backed point-in-time month-end
features, corporate-action-aware outcomes, portfolios, and SPY regimes, produced
byte-identical reports.

- logical report SHA-256: `09aa9095d428961fb5ce0b8d2c7894c897c327d03cd92b6df82368857378fa13`;
- report file SHA-256: `f85692a345481f44768acb52419f74f5faee785f3f68edbbbf1c28192f2381cc`;
- canonical local artifact:
  `data/derived/phase_9d-gate-evaluation/20260910-v1-decision.json`.

The report authenticates the registration, original and amended protocols,
residual dataset, folds, feature-panel report, eligibility audit, training fits,
outer predictions, monthly anchor dataset, and evaluation code.

This remains Tier-B current-survivor research with survivorship bias and static
present-day sectors. It is not independent confirmation, a deployment result,
or a guarantee of future SPY outperformance. Phase 10 stays closed for this
candidate, and the current live elastic-net model remains active.
