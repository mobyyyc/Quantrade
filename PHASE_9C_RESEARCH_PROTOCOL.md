# Phase 9C Weekly Rank Research Protocol

Protocol key: `tier_b_weekly_family_rank_v1`

Status: pre-implementation draft; it becomes frozen only after P9C.1 closes the
data-feasibility audit and this document records the resulting admissible data
scope.

Registration date: 2026-08-28

Research tier: B, private current-survivors research

## Why Phase 9C exists

Phase 9B ended correctly with no challenger frozen. Its 14,377 common-sample
rows came from only 40 monthly formations, complete-case filtering reduced the
20,500-row panel non-randomly, and no tested challenger cleared every ranking,
cost, stability, and turnover gate. Phase 9C must improve the data and the
objective before increasing model complexity.

The objective is stable **cross-sectional ordering** of stocks for a monthly
research basket. It is not precise return forecasting, a guarantee of SPY
outperformance, or permission to reinterpret the consumed holdout.

## Permanent research boundaries

- Cohort: `sp500_current_survivors_v1`. It is survivorship-biased and must never
  be represented as historical S&P 500 membership.
- Current sector classifications are not point-in-time. They may remain a
  labelled Tier-B diagnostic but cannot select the primary candidate.
- The July 2025 through June 2026 holdout is permanently report-only because
  its outcomes have been inspected. It cannot select a feature, formula,
  missing-data rule, hyperparameter, model, portfolio rule, or gate.
- Development formations and every nested split must be label-safe and use
  only information available at the historical 8:00 p.m. Toronto decision.
- A future production candidate still requires genuinely forward confirmation
  after it is frozen.
- No Phase 9C result supports an unbiased historical-performance or public
  performance claim.

## Decision, execution, and label

- Training formations are weekly, using the final regular market session of
  each week and an 8:00 p.m. America/Toronto decision timestamp.
- Portfolio formation remains monthly on the final regular market session.
- Portfolio entry is the next regular-session open.
- The primary outcome is the stock's next-open-to-20-completed-session wealth
  return minus the matching SPY wealth return.
- Stock and SPY returns use the same corporate-action convention. Ordinary
  cash dividends and splits are included only when the feasibility audit proves
  complete and deterministic accounting. A label crossing an unresolved
  merger, spin-off, special distribution, symbol discontinuity, or missing
  price is withheld rather than repaired.
- Within every weekly cross-section, the eligible numeric outcome is converted
  to a centered percentile rank in `[-1, 1]`. Raw relative returns remain
  available only for portfolio and diagnostic reporting.
- Every validation formation whose outcome interval overlaps training is
  purged by actual session dates, not by a convenient fixed calendar gap.

## Point-in-time SEC policy

- A filing-derived value is eligible only after the unified resolver's effective
  availability timestamp. Existing buffered and append-only observation rules
  remain mandatory.
- Quarterly standalone flows are reconstructed without future knowledge:
  `Q1 = Q1 YTD`, `Q2 = H1 YTD - Q1`, `Q3 = 9M YTD - H1 YTD`, and
  `Q4 = FY - 9M YTD`. TTM is the sum of the latest four eligible standalone
  quarters.
- The builder must fail closed on incompatible concept, unit, currency, fiscal
  context, duration, accession, duplicate context, dimensional ambiguity, or
  missing component.
- Each selected value retains concept, accession, form, acceptance and
  effective availability, period start/end, fiscal year/period, unit, source
  reference, observation hash, and rule version.
- Endpoint shares must prefer dated `dei:EntityCommonStockSharesOutstanding`
  or a proven filing-level endpoint fact. Period-average basic shares cannot be
  the primary endpoint-share substitute. It may be used only in a separately
  labelled robustness analysis.
- A gross-profit reconstruction from revenue less cost of revenue is permitted
  only when both facts share a compatible accession, duration, fiscal context,
  unit, and point-in-time eligibility.
- Historical filing-header SIC mapped to a fixed FF12 table may become a
  portfolio risk grouping only after P9C.1 proves sufficient free, reproducible
  coverage. It is not historical GICS.

## Pre-result feature scope

Raw eligible values are transformed to same-formation centered percentiles.
They are then compressed into fixed, signed economic-family values. The first
candidate may use at most the following six families:

1. **Momentum and trend:** existing 12-1 momentum and six-month relative
   strength, with 52-week-high proximity and residual momentum admitted only if
   P9C.1 establishes coverage and the pre-fit redundancy audit keeps them.
2. **Reversal:** the existing 20-session short-term reversal definition.
3. **Value:** book-to-market plus true-TTM earnings yield and operating-cash-flow
   yield when point-in-time coverage passes.
4. **Profitability and quality:** true-TTM ROA, operating-cash-flow
   profitability, gross profitability, and TTM accrual quality, retaining only
   pre-result admissible definitions.
5. **Investment and issuance:** asset growth and split-reconciled net issuance.
6. **Risk:** realized volatility and idiosyncratic volatility.

Liquidity remains a capacity/cost diagnostic for this protocol and is not a
primary alpha family. Exact family membership, signs, stale limits, and
aggregation must be frozen after coverage and redundancy inspection but before
any Phase 9C outcome comparison. No more than three economically distinct
feature expansions beyond the existing approved inputs may enter this version.

## Missing data and coverage

- Phase 9C does not use a complete-case dataset.
- A missing raw feature receives the neutral centered rank `0` only after its
  explicit reason is recorded. Each family has a pre-fit availability measure.
- No backward fill, later filing, cross-company imputation, or full-history
  statistic is allowed.
- `score coverage` and `informative coverage` are separate. Neutral filling
  cannot satisfy a feature-family coverage gate.
- The audit must report, by formation and family, usable values, neutral fills,
  stale exclusions, accounting exclusions, and issuers with fewer than the
  minimum informative families.
- Whether family availability enters the model is frozen before outcome
  inspection. If tested, it is one pre-registered missingness specification,
  not an open-ended search.

## Weighting and chronological validation

The effective time sample is the calendar, not the number of security rows.

- Each calendar month receives aggregate training weight `1`.
- That weight is divided equally among the month's weekly formations and then
  equally among eligible securities in each formation.
- Outer validation blocks remain Jul-Dec 2023, Jan-Jun 2024, Jul-Dec 2024, and
  Jan 2025 through the last label-safe pre-July-2025 formation.
- Within each outer fold, tuning uses only earlier chronological data. The last
  approximately nine label-safe months are divided into three continuous inner
  validation blocks when history permits; every boundary applies the same
  outcome-overlap purge.
- Weekly rank IC is aggregated first to the calendar month. Means, uncertainty,
  and gates give every calendar month equal weight.
- Primary uncertainty uses paired moving-block bootstrap over calendar months
  with a three-month block and 10,000 deterministic resamples. A stationary
  block bootstrap is sensitivity evidence only. Resampling does not create
  additional independent history.

## Fixed candidate budget

At most three Phase 9C challengers plus the required references may be examined:

1. **Primary:** family-shrunk ridge rank model with
   `lambda in {0.1, 1, 10, 100}`. Inner selection maximizes mean monthly rank IC;
   when alternatives are within `0.002`, choose the larger penalty.
2. **Backup:** linear pairwise logistic ranker with deterministic, normalized
   within-formation pair sampling specified before fitting.
3. **Optional backup:** a low-degrees-of-freedom additive model, only if its
   dependency and degrees of freedom are frozen before fitting.

Large neural networks, unrestricted boosted trees, random splits, full-history
normalization, and outcome-led feature search are excluded. All configurations
across allowed models must remain within a pre-registered budget of 12.

## Required references and fair attribution

Phase 9C must distinguish deployment, training-method, and portfolio effects:

- **Deployed active reference:** replay the exact active artifact and its frozen
  coefficients without refitting.
- **Active-family refit:** refit the current active feature set under the Phase
  9C weekly rank protocol. This isolates training-protocol changes from new
  feature information.
- **Phase 9C challenger:** use the frozen new families and model.

For portfolio attribution, every reference and challenger is evaluated under
both of these rules:

1. exact monthly Top 20, equal weighted; and
2. monthly Top 20 entry with Top 30 retention, equal weighted after formation.

The buffered rule cannot be credited as model improvement. The primary
promotion comparison uses identical construction for both models.

## Measurements

Report at minimum:

- mean monthly Spearman rank IC, dispersion, ICIR, and paired monthly delta;
- top-minus-bottom decile relative return;
- monthly Top-20 gross and net relative return at 5, 10, 25, and 50 bp one-way
  costs;
- one-way turnover, additions, removals, retention, and break-even cost;
- consecutive rank stability, coefficient stability, and family-sign stability;
- informative and score coverage by family and formation;
- results for pre-defined SPY trend and volatility regimes as diagnostics, not
  tuning targets;
- all exclusions, complex corporate actions, and lineage failures.

## Freeze gates

Numeric gates become immutable when P9C.1 closes. The proposed gates, subject
only to pre-result feasibility adjustment, are:

1. zero point-in-time, lineage, label-overlap, or reproducibility violations;
2. 100% lineage for included values, aggregate score coverage at least 95%,
   minimum monthly score coverage at least 90%, and separately frozen
   informative-family coverage thresholds;
3. mean monthly rank IC at least `0.012` and at least `0.004` above the deployed
   active reference under the same Phase 9C sample;
4. positive mean rank IC in at least three of four outer blocks, with the worst
   block greater than `-0.020`;
5. paired block-bootstrap probability that the IC delta is positive of at least
   90%, reported with its interval and effect size;
6. positive top-minus-bottom spread;
7. 25-bp Top-20 net relative return above zero and at least `0.001` per month
   above the same-construction active reference, with at least three of four
   blocks positive;
8. mean one-way turnover no greater than `0.42` and no more than `0.03` above
   the same-construction active reference;
9. consecutive rank stability at least `0.80`; and
10. material coefficient/family signs consistent in at least three of four
    outer fits.

These values are project judgments, not facts established by literature. P9C.1
must document their sensitivity and rationale before freezing them. Holm
adjustment and White Reality Check or Hansen SPA may be reported as
multiple-testing robustness; with roughly 40 independent months, they cannot
substitute for effect size, stability, and economic plausibility.

If any hard gate fails, the result is `no-freeze`. Post-result changes require a
new Phase 9C protocol version; thresholds may not be relaxed after inspection.

## Reproducibility contract

Before fitting, persist the protocol hash, Git commit, cohort and source
versions, exact formulas and signs, concept ladders, stale limits, exclusion
codes, calendars, folds, purge intervals, sample weights, model grids,
portfolio rules, costs, bootstrap seed, and gates. Two fixed-date replays must
produce identical feature, label, dataset, prediction, and evaluation hashes.

## Source-document limitation

The planning report analyzed for this protocol contained non-portable internal
citation markers rather than stable URLs, DOI values, or a bibliography. Its
claims are planning inputs, not yet an auditable literature record. A portable
bibliography is required before the protocol can be described as
literature-verified.
