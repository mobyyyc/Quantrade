# Monthly feature-family data readiness audit

**Audit date:** 2026-08-28  
**Scope:** P9B.2 of the monthly feature-family research reset  
**Decision:** The free Tier-B historical foundation is sufficient for price-only features now. The proposed accounting feature families must remain fail-closed until the safeguards in this report are implemented and tested.

## What is already in place

Quantrade keeps a fixed, survivorship-biased current-members cohort separate from the deferred verified point-in-time universe. Historical market bars use a documented 6:00 p.m. Toronto availability rule, and replay decisions occur at 8:00 p.m. Toronto.

For SEC data, each filing is keyed by its unique accession number and has the SEC acceptance timestamp in `accepted_at` and `available_at`. Feature queries filter facts by `available_at <= decision_at`; a later accepted filing is therefore excluded from an earlier decision. The SEC history importer follows the SEC-provided historical submissions references and rejects conflicting metadata for the same accession.

The store also records content hashes, source references, parser versions, retrieval metadata, and source-receipt links. New compact receipts avoid retaining routine SEC response payloads while retaining provenance.

The 2026-08-28 read-only database audit found:

| Evidence | Result |
| --- | --- |
| Unique filing accessions | 1,824,039 of 1,824,039 filing rows |
| Filing availability | all 1,824,039 rows currently use `available_at = accepted_at` |
| Relevant SEC forms | 11,939 10-K, 38,152 10-Q, and 47 20-F filings |
| Existing candidate accounting concepts | Assets, NetIncomeLoss/ProfitLoss, revenue variants, cost-of-revenue variants, and operating-cash-flow facts are present |
| Share-count facts | 75,381 `dei:EntityCommonStockSharesOutstanding` facts |
| Corporate actions | 53 forward splits, 4 reverse splits, plus dividends and merger-related actions |

These counts demonstrate useful coverage; they do **not** establish that every issuer, period, unit, or concept is comparable enough to include. Missing or invalid inputs must remain exclusions.

## Capability assessment

| Requirement | Status | Reason and required treatment |
| --- | --- | --- |
| Accession-aware filing lineage | ready | Each filing has a unique accession, and facts retain `filing_id`. An amendment has a separate accession and can become eligible only after its own availability time. |
| Prevent a later filing from entering an earlier decision | ready | The feature loaders and replay queries filter by `available_at <= decision_at`; existing tests reject a future-dated fact. |
| Preserve amendment identity and relationships | partial | The importer normalizes `10-Q/A` and `10-K/A` to their base form. The accession is retained, but there is no stored raw-form field or explicit amendment-to-original link. Add both before amendment diagnostics or amendment-sensitive features. |
| Preserve revisions to a fact from the same filing | blocked | `filing_facts` upserts by filing/concept/unit/period and updates `fact_value`. A later Company Facts response can therefore rewrite the stored value for the same accession. Immutable source receipts show that a response changed, but they do not reconstruct the fact value that was known at an earlier decision. Introduce append-only fact observations or a version table before historical accounting features are replayed. |
| SEC publication-latency buffer | blocked | The current rule is acceptance time exactly. Create a versioned `sec_filing_acceptance_plus_5m` rule, set fact eligibility to `accepted_at + 5 minutes`, and record the rule on every feature/snapshot produced under it. The current 8:00 p.m. decision does not remove the need for this explicit rule. |
| Annual net-income and ROA baseline | ready for the existing baseline only | The current implementation selects annual `NetIncomeLoss`/`ProfitLoss`, checks availability, and uses aligned Assets endpoints. It intentionally does not infer unfiled quarters. |
| True TTM flows | blocked | `earnings_yield_ttm` and `return_on_assets_ttm` currently use an annual reported flow despite their historical names. Implement a period-aware annual-or-quarterly builder with annual + comparable year-to-date quarter arithmetic, same-concept selection, filing availability checks, and fail-closed handling for missing quarters. |
| Asset growth | conditional | Assets facts and two-period annual selection exist, but a dedicated feature needs a reusable comparable-year endpoint selector, amendment policy, and a coverage/exclusion audit. It should use public facts only, never a later restatement. |
| Net share issuance | blocked | Historical shares-outstanding facts exist and price bars are split-adjusted, but the stored share facts are not reconciled through corporate actions. Build a split-aware comparison between the two dated share observations; exclude mergers, spin-offs, missing ratios, and ambiguous periods. |
| Gross profitability or accrual quality | blocked | Relevant revenue, cost, and cash-flow concepts exist, but issuer-specific concept selection and TTM construction are not implemented. Select one feature only after a concept-coverage audit; do not blend incompatible extension concepts silently. |
| Corporate-action availability | partial | Corporate actions are retained with availability timestamps and historical actions use a documented Tier-B 6:00 p.m. rule. The rule is not independently point-in-time verified, so it is appropriate for the private Tier-B track only and must be surfaced in provenance. |
| Static sector grouping | ready as a robustness grouping only | The static cohort and sector classification are explicitly Tier B/non-point-in-time. Primary cross-sectional ranks must remain market-wide. |

## Required implementation gates

No historical accounting feature may be added to a candidate dataset until all applicable gates pass:

1. **Append-only SEC fact versions.** Store each parsed fact observation with its receipt/content hash, accession, parser version, retrieval time, and an immutable value. The as-of loader must choose the latest observation whose *filing availability* is at or before the decision and whose observation itself was not created from a later revision snapshot.
2. **Amendment metadata.** Preserve the submitted form verbatim, derive the base form separately, and record a best-effort amendment/original relationship. The selector must make the amendment eligible only after its own buffered time.
3. **Five-minute rule.** Add a versioned availability rule for `accepted_at + 5 minutes`; make it the sole SEC rule for P9B accounting candidates. Feature explanations, snapshots, manifests, and exports must name its rule version/hash.
4. **Period-aware flow builder.** Build tested helpers for annual flows and TTM flows. They must reject overlapping, duplicate, incomplete, unit-inconsistent, future-available, or extension-concept inputs.
5. **Split-aware share-count builder.** Compare dated share facts only after a corporate-action reconciliation. It must publish an exclusion rather than guess when the path cannot be proven.
6. **Coverage and determinism tests.** For every feature: test late filing exclusion, late amendment exclusion, same-accession revision handling, missing period exclusion, split event handling, and identical hashes from two replays of the same decision date.

## Implemented after this audit

The first two safeguards are now implemented in migration `0028_add_sec_fact_versioning.sql`:

- an append-only `filing_fact_observations` table stores immutable parsed values with source lineage and an observation hash;
- all new SEC observations use the versioned `sec_filing_acceptance_buffered@v1` rule, which makes them eligible five minutes after SEC acceptance;
- future ingestion preserves an original submitted form and an amendment flag, while retaining the existing canonical form for compatibility;
- the old mutable canonical `filing_facts` rows remain for the already-approved baseline only. New monthly accounting research must read the append-only observation table.

The existing canonical facts are deliberately **not** copied by the schema migration: copying 1.8 million rows in one transaction would block ordinary database work. A later resumable, chunked operation will create clearly labelled `legacy_snapshot` observations. It will not claim to reconstruct every historical provider revision; that limitation remains part of Tier-B provenance.

## Consequence for P9B.3

P9B.3 may safely start with the price-only short-term-reversal feature because it already reads split-adjusted bars through the point-in-time availability filter.

The accounting portion of P9B.3 is dependent on the six gates above. Implement the data safeguards first, then add the candidate calculations in this order:

1. asset growth;
2. net share issuance;
3. one quality feature selected from gross profitability or accrual quality after coverage measurement.

Do not expose a model trained with the current-survivors cohort as unbiased historical performance. All resulting data and models retain the Tier-B survivorship/static-sector limitations.
