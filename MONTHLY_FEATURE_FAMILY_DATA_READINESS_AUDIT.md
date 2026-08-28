# Monthly feature-family data readiness audit

**Audit date:** 2026-08-28  
**Scope:** P9B.2 of the monthly feature-family research reset  
**Decision:** The free Tier-B historical foundation is sufficient for the pre-registered monthly feature panel. Accrual quality is selected over gross profitability strictly from pre-result accounting coverage. Every accounting feature remains fail-closed when its comparable-period or lineage rules are not satisfied.

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
| Prevent a later filing from entering an earlier decision | ready | The unified resolver filters its effective availability by decision time. Its tests prove that a later observation changes only later decisions. |
| Preserve amendment identity and relationships | partial | The importer normalizes `10-Q/A` and `10-K/A` to their base form. The accession is retained, but there is no stored raw-form field or explicit amendment-to-original link. Add both before amendment diagnostics or amendment-sensitive features. |
| Preserve revisions to a fact from the same filing | ready with Tier-B legacy limitation | Canonical facts are append-only, future observations are immutable, and observations of one accession-level fact share a logical resolver identity. A legacy provider revision that was never captured remains unrecoverable and disclosed. |
| SEC publication-latency buffer | ready | The resolver uses the versioned five-minute rule. Future values also wait for actual observation time when that is later. |
| Annual net-income and ROA baseline | ready for the existing baseline only | The current implementation selects annual `NetIncomeLoss`/`ProfitLoss`, checks availability, and uses aligned Assets endpoints. It intentionally does not infer unfiled quarters. |
| True TTM flows | blocked | `earnings_yield_ttm` and `return_on_assets_ttm` currently use an annual reported flow despite their historical names. Implement a period-aware annual-or-quarterly builder with annual + comparable year-to-date quarter arithmetic, same-concept selection, filing availability checks, and fail-closed handling for missing quarters. |
| Asset growth | ready | The panel selects comparable 330–400 day Assets endpoints, applies decision-time availability, retains accession lineage, and excludes missing/non-positive inputs. |
| Net share issuance | ready for Tier-B research | The panel prefers comparable DEI shares, uses one documented annual basic-share fallback, reconciles intervening split ratios, and rejects structural actions or invalid ratios. |
| Gross profitability or accrual quality | ready: accrual selected | Accrual quality was selected before outcome inspection from 98.4% comparable coverage. Direct gross profit was rejected at 44.6% coverage. |
| Corporate-action availability | partial | Corporate actions are retained with availability timestamps and historical actions use a documented Tier-B 6:00 p.m. rule. The rule is not independently point-in-time verified, so it is appropriate for the private Tier-B track only and must be surfaced in provenance. |
| Static sector grouping | ready as a robustness grouping only | The static cohort and sector classification are explicitly Tier B/non-point-in-time. Primary cross-sectional ranks must remain market-wide. |

## Required implementation gates

No historical accounting feature may be added to a candidate dataset until all applicable gates pass:

1. **Append-only SEC facts.** Freeze existing canonical facts against updates/deletes and store each future changed observation with its receipt/content hash, accession, parser version, retrieval time, and immutable value. Do not duplicate the entire legacy store. The as-of loader must prevent a future observation from entering an earlier decision.
2. **Amendment metadata.** Preserve the submitted form verbatim, derive the base form separately, and record a best-effort amendment/original relationship. The selector must make the amendment eligible only after its own buffered time.
3. **Five-minute rule.** Add a versioned availability rule for `accepted_at + 5 minutes`; make it the sole SEC rule for P9B accounting candidates. Feature explanations, snapshots, manifests, and exports must name its rule version/hash.
4. **Period-aware flow builder.** Build tested helpers for annual flows and TTM flows. They must reject overlapping, duplicate, incomplete, unit-inconsistent, future-available, or extension-concept inputs.
5. **Split-aware share-count builder.** Compare dated share facts only after a corporate-action reconciliation. It must publish an exclusion rather than guess when the path cannot be proven.
6. **Coverage and determinism tests.** For every feature: test late filing exclusion, late amendment exclusion, same-accession revision handling, missing period exclusion, split event handling, and identical hashes from two replays of the same decision date.

## Implemented after this audit

The forward-looking storage safeguards are implemented in migration `0028_add_sec_fact_versioning.sql`:

- an append-only `filing_fact_observations` table stores immutable parsed values with source lineage and an observation hash;
- new SEC observations record the versioned `sec_filing_acceptance_buffered@v1` rule; the resolver must conservatively use the later of acceptance-plus-five-minutes and actual observation time;
- future ingestion preserves an original submitted form and an amendment flag, while retaining the existing canonical form for compatibility;
- the importer no longer overwrites a canonical fact on conflict. A database-level update/delete guard is still required to freeze the legacy table completely.

The database contains roughly 21.1 million canonical fact rows. A resumable snapshot runner was proven with a 5,000-row pilot, but a full copy is unnecessary for the revised architecture. Migration `0030_freeze_canonical_sec_facts.sql` removes the pilot rows and progress ledger, prevents future legacy snapshots, and blocks updates/deletes on canonical facts while continuing to allow inserts. Only compact monthly feature values and their selected lineage will be materialized. The legacy data still cannot reconstruct a provider revision that was never captured; that limitation remains part of Tier-B provenance.

## Consequence for P9B.3

P9B.3 completed after the applicable safeguards above were implemented. The compact panel contains short-term reversal, asset growth, split-reconciled net share issuance, and the pre-selected accrual-quality feature. Missing or ambiguous rows remain explicit exclusions.

Do not expose a model trained with the current-survivors cohort as unbiased historical performance. All resulting data and models retain the Tier-B survivorship/static-sector limitations.

## P9B.2b–2c closure evidence

The unified resolver is implemented in `sec_fact_resolver.py`. It applies these rules without copying the legacy store:

- frozen legacy facts become eligible at SEC acceptance plus five minutes under the explicit Tier-B legacy assumption;
- future observations become eligible at the later of acceptance-plus-five-minutes and actual observation time;
- canonical rows with an append-only observation are excluded from the legacy branch, so a newly downloaded value cannot be backdated;
- observations of one accession-level fact share a logical identity, while amendments retain their separate accession identities;
- resolving an earlier decision after a later observation produces the same earlier result.

The concept audit used only facts eligible by **2025-06-30 at 8:00 p.m. Toronto**, before any candidate return was inspected. Its cohort was the 500-security development sample represented in the frozen score snapshots.

| Candidate input | Comparable evidence | Securities | Coverage |
| --- | ---: | ---: | ---: |
| Annual Assets endpoints for asset growth | 26,549 comparable periods | 494 | 98.8% |
| `dei:EntityCommonStockSharesOutstanding` with at least two dates | median 61 dated observations | 465 | 93.0% |
| Annual `us-gaap:WeightedAverageNumberOfSharesOutstandingBasic` fallback | annual facts available | 492 | 98.4% |
| Direct annual `us-gaap:GrossProfit` | 8,276 annual facts | 223 | 44.6% |
| Annual net income + operating cash flow + aligned Assets | 6,456 comparable periods | 492 | 98.4% |

Accordingly, the pre-result quality choice is **accrual quality**:

`(annual net income − annual operating cash flow) / average total assets`

Lower accruals receive the favorable sign. `NetIncomeLoss` is preferred and `ProfitLoss` is the documented fallback for the same annual period. Gross profitability is rejected for this phase because direct comparable coverage is materially below the 80% gate; it is not reconstructed by silently mixing revenue and cost concepts.

Net share issuance prefers dated DEI shares. When two comparable DEI observations are unavailable, it uses annual basic weighted-average shares for both endpoints without mixing concepts within the comparison. Both paths reconcile intervening split ratios and reject structural mergers/spin-offs rather than guessing.
