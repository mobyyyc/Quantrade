# Market-data provider boundary

Quantrade's routine market ingestion uses a provider-neutral contract. Alpaca remains the only enabled V1 provider, but normalized ingestion no longer depends on Alpaca response fields, adjustment names, authentication, URLs, or symbol formatting.

## Boundary

An adapter implements `MarketDataProvider` and returns:

- canonical daily bars using `unadjusted`, `split_adjusted`, or `total_return_adjusted` semantics;
- canonical corporate actions;
- the exact raw response bytes, pagination token, source references, parser versions, and provider identity needed for provenance;
- provider-specific availability-rule keys already registered in PostgreSQL.

The shared ingestion commands handle missing-only planning, batching, compact receipts or raw retention, normalized database writes, and immutable run manifests. Both commands select the configured provider from `MARKET_DATA_PROVIDER`; `--provider` is an explicit per-run override.

## Adding a provider

1. Implement the `MarketDataProvider` protocol in a provider adapter. Authentication, transport, wire parsing, symbol aliases, and adjustment translation stay inside that adapter.
2. Add a credential-safe factory to `market_provider_registry.py`.
3. Register provider-specific point-in-time availability rules through a reviewed database migration.
4. Add adapter contract fixtures for pagination, all three adjustment bases, malformed responses, share classes, and corporate actions.
5. Reconcile the candidate provider against the normalized ledger before enabling it in `MARKET_DATA_PROVIDER`.

No normalized table, feature, score, or portfolio code should change when a provider is added.

## Failover policy

Failover is explicit at the run boundary, never silent within a run. A run records one provider identity for every source page. Quantrade does not merge a failed provider's partial page stream with a fallback stream because doing so would obscure lineage and may mix adjustment semantics.

Operational failover therefore means:

1. the active run fails safely before score publication;
2. the operator selects an audited registered provider;
3. the idempotent missing-only ingestion is rerun;
4. receipts and manifests identify the replacement source exactly;
5. reconciliation validates its normalized output before normal scheduling resumes.

This boundary prepares failover without claiming that a second free provider has already passed coverage and adjustment audits.
