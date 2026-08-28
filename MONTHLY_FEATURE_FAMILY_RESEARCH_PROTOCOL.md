# Monthly Feature-Family Research Protocol: `tier_b_monthly_feature_family_v2`

## Registration status

Revised and pre-registered on 2026-08-28 before Phase 9B feature
materialization, candidate fitting, or result inspection. Version 2 supersedes
version 1 only to replace the unnecessary full SEC-store copy with the lean
freeze-and-resolve architecture. The feature scope, validation design, model
set, portfolio construction, and decision gates are unchanged. A feature,
transformation, model family, parameter, portfolio size, cost assumption, or
gate may not be changed after its relevant out-of-fold result is inspected.

The active `tier_b_regularized_linear_development_v1` model remains the live
private-beta model throughout this program. Phase 9B does not change published
scores, rankings, watchlists, portfolios, or the active model artifact.

## Research objective

Test whether a small group of economically distinct, free-data feature
families provides stable incremental **monthly cross-sectional ranking**
information beyond the active model. The objective is not a precise stock
return forecast and is not a claim that a portfolio will outperform SPY.

## Data scope and permanent exclusions

- Cohort: `sp500_current_survivors_v1`, a fixed current-members Tier-B cohort.
  Historical membership, delistings, and sector classifications are not
  available. Survivorship and static-sector warnings must remain attached to
  every result.
- Development observations may use only formations whose complete 20-session
  label ends before 2025-07-01.
- The consumed 2025-07-01 through 2026-06-30 historical holdout is
  reporting-only. It must not select or remove a feature, transformation,
  model, hyperparameter, coefficient cap, cost case, portfolio size, ensemble,
  or promotion decision.
- Any future confirmation period starts only after a candidate is frozen.
- A row with a missing or invalid required point-in-time input, execution mark,
  provenance reference, or completed label is withheld. It is never repaired
  by backward fill, later facts, or full-history imputation.

## Point-in-time decision policy

For every monthly formation, use the final regular market session of that
calendar month and make the research decision at 8:00 p.m. America/Toronto.

- Price inputs may use regular-session bars through the formation close only
  when their recorded `available_at` is no later than that decision time.
- Filing-derived inputs may use only accession-level facts with the required
  filing acceptance time and source lineage. Eligibility uses a conservative
  five-minute SEC publication buffer. Frozen legacy facts use acceptance plus
  five minutes under the disclosed Tier-B historical assumption. Future
  append-only observations use the later of acceptance-plus-five-minutes and
  the actual observation time.
- Amendments and restatements must be accession-aware. A later amendment may
  affect decisions only after its own allowed availability time; it must not
  overwrite what was knowable before acceptance.
- TTM flow features must be constructed from point-in-time annual and
  comparable year-to-date components, not from a later restated aggregate.
- Existing canonical SEC facts are frozen in place; they are not duplicated
  into a second full fact store. The research artifact persists only the
  selected monthly feature values and their accession/fact lineage.

## Label and execution policy

- Primary ranking label: completed 20-session stock return relative to SPY,
  using a common stock/benchmark adjustment convention for each experiment.
  SPY subtraction does not change the within-date stock ordering, but it is
  retained for portfolio evaluation.
- The training comparison uses one equally weighted cross-section per monthly
  formation. Daily observations may be reported only as a clearly separate
  sensitivity analysis, never pooled as the primary evidence.
- A formation portfolio selects the top 20 eligible names, equally weighted at
  5% each, from the final session's decision. It enters at the next regular
  session open and exits under the same next-open convention after the
  completed holding interval.
- Exclude every training formation whose 20-session label overlaps a validation
  block. The purge is defined by label overlap, not a convenient calendar gap.

## Feature-family scope

The active six input definitions remain the reference set. Phase 9B may test
only the following additions after P9B.2 proves their data construction and
P9B.3 records immutable definitions:

1. **Reversal:** one 20-session short-term reversal measure, excluding the
   most recent session.
2. **Investment:** asset growth using comparable point-in-time balance-sheet
   facts.
3. **Financing:** net share issuance using split-reconciled reported share
   counts.
4. **Quality:** exactly one initial specification, either gross
   profitability-to-assets or accrual quality. A second quality specification
   requires a new protocol version.

Six-month relative strength is retained for the active reference but is
explicitly tested for redundancy with 12-1 momentum. Risk and liquidity inputs
remain controls unless out-of-fold evidence supports their ranking use.

## Transformations and missing data

- Primary transformation: market-wide centered percentile ranks, calculated
  only within each formation's eligible point-in-time cross-section.
- Static current-sector percentile ranks are a Tier-B robustness comparison.
  A result that succeeds only under static-sector grouping cannot select a
  production candidate.
- No backward fill, full-sample statistic, or future-aware imputation is
  permitted. P9B.3 may evaluate explicit missingness indicators only if their
  fitting is contained within each chronological training fold.

## Validation and candidate comparison

- Use expanding chronological outer folds. The intended validation blocks are
  Jul-Dec 2023, Jan-Jun 2024, Jul-Dec 2024, and Jan 2025 through the final
  label-safe pre-July-2025 formation. A missing qualifying monthly formation
  is documented, not substituted.
- Tune any permitted penalty only inside each outer fold's chronological inner
  training/validation split. Outer validation predictions remain untouched
  until comparison.
- Every formation receives equal aggregate training weight.
- Compare on the identical complete-row monthly sample: the active elastic-net
  reference, signed equal-weight family composite, ridge, low-L1 elastic net,
  and robust ridge-like regression. Pairwise ranking, constrained ridge, a
  nonlinear additive model, or an ensemble require a new protocol version.

## Measurements and fixed decision gates

All models must report monthly rank IC, top-minus-bottom spread, top-20
next-open benchmark-relative return, one-way turnover, rank stability, feature
coverage, coefficient or family-sign stability, SPY trend/volatility
diagnostics, and 5, 10, 25, and 50 basis-point one-way cost cases.

A candidate can freeze only when its common-sample out-of-fold evidence shows:

1. zero point-in-time or lineage violations;
2. at least 80% coverage on every included monthly formation and 90% aggregate
   coverage;
3. strictly positive mean monthly rank IC and improvement over the active
   reference;
4. top-20 benchmark-relative return no worse than the active reference at the
   pre-specified 25-basis-point cost case;
5. mean one-way turnover no more than 10 percentage points above the active
   reference and no greater than 75%;
6. no validation block with negative mean rank IC;
7. no material regression in rank stability or unexplained concentration in a
   single SPY trend/volatility regime; and
8. byte-identical repeated results with all exclusions and source hashes
   recorded.

If no candidate clears every gate, Phase 9B ends with a versioned no-freeze
decision. The number of non-zero coefficients is descriptive only. No model
may force an economically unsupported feature to be non-zero merely to appear
broader.

## Interpretation boundary

All Phase 9B outputs are private Tier-B research. They cannot support an
unbiased historical-performance claim, a public product-performance claim, or
a guarantee that individual stocks or the top-20 portfolio will outperform
SPY.
