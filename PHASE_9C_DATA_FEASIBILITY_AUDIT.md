# Phase 9C Data Feasibility Audit Plan

Audit key: `phase_9c_data_feasibility_v1`

Status: planned; no Phase 9C historical download or model fitting is authorized
by this document.

Audit rule: inspect metadata and existing coverage first; fail closed and
separate unavailable capabilities from implementation defects.

## Audit outcome required

P9C.1 must produce a versioned machine-readable report and a human decision
record that answers whether Quantrade can build the Phase 9C label and feature
families from its existing free-data architecture. It must freeze the exact
admissible scope before any candidate outcome is inspected.

The audit has five independent workstreams. A failure in one workstream removes
only the dependent feature or label path unless it invalidates the common
point-in-time sample.

## A. Corporate-action-aware wealth labels

Inspect the existing unadjusted, split-adjusted, total-return-adjusted, and
corporate-action records for cohort securities and SPY over the development
period.

Required evidence:

- session coverage at every proposed entry and 20-session exit;
- ordinary cash-dividend coverage, ex-date, amount, currency, and entitlement
  convention;
- split coverage and consistency with raw/split-adjusted price ratios;
- identical adjustment convention for stocks and SPY;
- counts of mergers, spin-offs, symbol changes, special distributions, reverse
  splits, and unclassified actions crossing labels;
- deterministic reconciliation against provider total-return bars where those
  bars exist; and
- exclusion counts and security/date examples for every unresolved class.

Pass rule: ordinary dividends and splits reconcile under one documented wealth
ledger with no unexplained difference above a frozen tolerance. Complex actions
need not be solved; every crossing label must instead be deterministically
withheld. If provider history cannot prove ordinary-dividend completeness, the
primary label remains blocked.

## B. Point-in-time quarterly and TTM SEC engine

Audit the existing canonical facts and immutable observations without creating
a second full SEC store.

Required evidence:

- coverage by issuer, fiscal period, concept, unit, currency, form, accession,
  and source-observation type;
- availability of Q1, H1, 9M, and FY components needed to reconstruct standalone
  quarters;
- duplicate and conflicting contexts, dimensional facts, 52/53-week years,
  fiscal-year changes, amendments, and sign anomalies;
- percent of candidate TTM values supported entirely by eligible facts at each
  decision;
- agreement between reconstructed four-quarter sums and later reported annual
  totals as a diagnostic only, never as a backfill;
- direct versus safely reconstructed gross-profit coverage; and
- byte-identical results for repeated historical decisions before and after a
  later amendment becomes available.

Pass rule: a TTM value is usable only when four eligible standalone quarters
can be proven with compatible contexts and full lineage. Feature-specific
informative-coverage thresholds are frozen from the audit before returns are
joined. Missing components remain missing.

## C. Endpoint shares and issuance

Required evidence:

- coverage of dated `dei:EntityCommonStockSharesOutstanding`;
- coverage of any filing-level endpoint shares with compatible dimensions;
- reconciliation around every stored split and structural action;
- comparison showing how often the former
  `WeightedAverageNumberOfSharesOutstandingBasic` fallback would change the
  direction or magnitude of issuance; and
- a separate count for cases where no defensible endpoint shares exist.

Pass rule: weighted-average basic shares are not admitted to the primary
Phase 9C endpoint-share path. The feature is missing when endpoint shares and
the corporate-action path cannot be proven.

## D. Historical SIC and FF12 risk grouping

Required evidence:

- whether filing-header `ASSIGNED-SIC` or an equivalent accession-dated field is
  already stored or reproducibly obtainable without retaining full filings;
- issuer and formation coverage, changes through time, conflicts between forms,
  and missing foreign/private-issuer cases;
- versioned SIC-to-FF12 mapping and unmapped-code report; and
- source URI, accession, acceptance time, retrieval time, and content hash for
  every selected classification.

Pass rule: at least 95% formation-level coverage with deterministic lineage is
required before FF12 can constrain portfolio concentration. Otherwise the
primary model remains market-wide and the capability is deferred. Historical
SIC must never be labelled historical GICS.

## E. Market-feature and weekly-calendar coverage

Required evidence:

- eligible session counts for 12-1 momentum, six-month relative strength,
  52-week high, realized volatility, residual momentum, idiosyncratic
  volatility, and SPY regressors;
- formation-calendar proof for every weekly and monthly decision;
- delisted/missing/suspended symbols and non-positive prices;
- pairwise correlations, monotonicity, and redundant-feature groups calculated
  without inspecting future returns; and
- each calendar month's resulting sample weight, proving the aggregate equals
  one regardless of whether the month has four or five weekly formations.

Pass rule: a feature can enter the frozen family definition only if its minimum
formation coverage and provenance pass the pre-result threshold and its
redundancy decision is recorded before labels are joined.

## Required leakage and determinism tests

The implementation following this audit must add tests proving:

1. a later SEC filing or observation cannot change an earlier feature;
2. an amendment affects only decisions after its own buffered availability;
3. a later market bar cannot enter an earlier formation;
4. a dividend or split is applied once, to both eligibility and wealth
   accounting, and is not double-counted by adjusted prices;
5. unresolved corporate actions withhold rather than repair a label;
6. validation training excludes every overlapping 20-session outcome;
7. transformations and missingness logic are fitted or applied within each
   chronological fold only;
8. monthly aggregate training weights remain equal;
9. every exported row has complete label lineage and explicit Tier-B
   provenance; and
10. two replays of a fixed historical date produce identical hashes.

## Audit deliverables

- `phase_9c_data_feasibility_v1.json` with counts, coverage, exclusions, rule
  versions, query/code hashes, and decision per workstream;
- a concise human-readable closure document with `pass`, `restricted`,
  `deferred`, or `blocked` for every capability;
- a frozen feature-family manifest and stale-limit table;
- a frozen label-accounting manifest;
- a portable bibliography for the external research claims used to justify
  Phase 9C; and
- an updated protocol hash before any Phase 9C model fitting.

## Explicit non-actions

P9C.1 does not download full SEC filings or PDFs, build the weekly dataset,
train a candidate, inspect candidate returns, alter the active model, or change
the web app. Any targeted retrieval required to close an observed metadata gap
must be proposed as a later approved task with an estimated request and storage
budget.
