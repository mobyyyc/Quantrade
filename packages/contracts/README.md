# Shared contracts

This package defines the provider-neutral, versioned boundary between research
outputs and future APIs or product surfaces.

## Source of truth

The language-neutral JSON Schemas in `schemas/v1` are canonical. Matching
TypeScript types in `src` are ergonomic consumers for the web/API layer; the
Python research service should emit payloads that conform to the JSON Schemas.

| Domain | Schema | Contract types |
| --- | --- | --- |
| Security identity and listings | `security.schema.json` | `SecurityRecord`, `ListingRecord` |
| Daily market bars | `market-data.schema.json` | `DailyPriceBar` |
| SEC filings and facts | `filing.schema.json` | `FilingRecord`, `FilingFact` |
| Versioned feature definitions | `feature.schema.json` | `FeatureDefinition` |
| Dated model outputs | `score.schema.json` | `ScoreSnapshot` |
| Dated universe membership | `universe.schema.json` | `UniverseMembershipSnapshot` |

## Invariants

- Contract versions are explicit; a breaking change creates `v2` rather than
  changing a persisted `v1` payload.
- Monetary and market quantities are decimal strings, not binary floats.
- Provider responses are normalized before crossing this boundary.
- Source attribution includes a raw-artifact reference and retrieval time.
- Every market fact and filing fact has `availableAt` and `ingestedAt`; model
  logic may only use records with `availableAt` at or before its decision time.
- Score snapshots are immutable and always identify their model, feature,
  protocol, cutoff, and data-capability tier.
- Feature definitions are immutable: a different formula, inputs, direction, or
  as-of rule requires a new feature version and definition hash.

Cross-record constraints—such as `high >= low`, a filing fact's matching
security ID, and an unavailable score's reason—are enforced by P1.3 storage
rules and P2 data-quality checks.
