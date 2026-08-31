# Data Retention Policy: Compact Point-in-Time Research

**Status:** Approved design contract for the storage-and-ingestion hardening phase.  
**Scope:** New routine daily updates after the implementing migration. Historical
data already stored in the current raw-artifact layout is not deleted by this
policy alone.

## Decision

Quantrade will retain the structured data and compact provenance needed to
reproduce a point-in-time research decision. It will not retain full SEC filing
documents, filing HTML, PDFs, or repeated provider response payloads for routine
daily updates.

This is a private Tier-B research policy. It preserves the facts that the model
was allowed to use and the identity of their source, but it does not provide an
offline copy of every original provider response.

## What must be retained

Each retained market, filing, or financial-fact record must remain typed and
queryable in PostgreSQL. It must include the fields below where applicable.

| Record | Required point-in-time fields | Required provenance |
|---|---|---|
| Daily price bar | session date, session, adjustment basis, OHLCV, observed time, available time | provider, endpoint, retrieval time, content hash, parser version |
| Corporate action | provider action ID, action type, effective date, terms, available time | provider, endpoint, retrieval time, content hash, parser version |
| SEC filing | CIK/security, accession number, form, filed date, SEC acceptance time, available time | SEC submissions endpoint, retrieval time, content hash, parser version |
| SEC financial fact | accession number, taxonomy, concept, unit, value, period dates, fiscal labels, available time | company-facts endpoint, retrieval time, content hash, parser version |
| Score/feature snapshot | decision time, data cutoff, feature/model/protocol versions, feature contribution | immutable source-receipt references and run manifest |

`available_at` remains the hard eligibility boundary. A later retrieval may
never make data eligible for an earlier decision.

## Compact source receipts

Each provider response used by ingestion will have one small source receipt.
The receipt stores:

- provider and endpoint/source reference;
- SHA-256 content hash and byte count;
- retrieval timestamp and parser version;
- response category and optional HTTP metadata needed for diagnostics;
- a link to the structured rows extracted from it.

The source receipt is evidence of what was received without retaining a local
copy of the complete response. Equal payloads are represented by the same
content hash; repeated retrievals are represented as separate lightweight
retrieval events, not duplicate files.

## Routine daily-update boundary

The routine daily update may retrieve only:

1. missing market sessions after the latest stored session;
2. SEC daily-index dates from the previous completed decision through the
   current decision date, inclusive;
3. submissions metadata for in-universe companies identified by that index;
4. financial facts only when a newly discovered supported filing can change a
   model input.

It must not download full SEC filing documents. It must not reprocess every
company's historical facts after an unrelated filing. It must not scan the
entire cohort as a silent fallback when the SEC daily index is unavailable.

If the required SEC discovery index cannot be retrieved after bounded retries,
the filing stage must fail or defer visibly and remain resumable. A score
publication must not be presented as a fully refreshed filing-aware result.

## Data format rules

- PostgreSQL is the operational source for typed facts and point-in-time
  queries.
- Training exports are wide, versioned datasets derived from those typed rows;
  they are not provider payload archives.
- Content hashes use lowercase SHA-256 and identify bytes, not a semantic claim
  that a provider never revised a value.
- Dates/timestamps use typed SQL `DATE` and `TIMESTAMPTZ` values, not strings.
- Values retain their provider unit and source accession. Unit conversions are
  feature-layer operations and must be versioned.
- A correction or amendment is a new accession/versioned input, never an
  overwrite that erases an earlier eligible fact.

## Existing data and cleanup

The current historical dataset remains read-only during implementation. No
existing raw JSON or database rows may be deleted until all of the following
are complete:

1. compact source receipts and new daily ingestion pass their tests;
2. historical score replay and training-export hashes match the approved
   baseline for a fixed sample;
3. a coverage report confirms no required fact, price bar, action, or manifest
   reference was lost;
4. a recoverable export/checkpoint exists; and
5. an explicit cleanup task is approved.

The cleanup task must report files removed, database space reclaimed, retained
date coverage, and any intentional limitation introduced by this policy.

## Known limitation

Because routine provider payloads are not kept locally, an investigation can
verify a source URL, retrieval receipt, hash, and extracted fields, but cannot
open a local archival copy of the original payload. If external audit-grade
document retention becomes necessary, it requires a separate storage policy and
possibly licensed data rights.

## Database backup retention

Operational PostgreSQL backups are separate from raw-provider retention. A
verified custom-format backup is created daily and retained for 30 days, with a
minimum floor of seven newest archives. Expiration runs only after the new
archive passes checksum and restore-catalog validation. Metadata sidecars expire
with their matching archives; partial or unverifiable archives never trigger
retention.
