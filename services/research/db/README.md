# Research database

The PostgreSQL schema is owned by the research service. Migrations are ordered
and append-only; never edit a migration that may have been applied.

## Apply locally

After P1.4 provides a local-only `DATABASE_URL` and a PostgreSQL 15+ instance:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/migrations/0001_core_schema.sql
```

The first migration creates the `quantrade` schema and normalized tables for
raw artifacts, securities, identifier/listing history, daily bars, filings,
filing facts, and immutable score snapshots.

`raw_artifacts` stores provider lineage and object-storage references; the
payload itself remains in object storage. `available_at` is an explicit query
gate for point-in-time panel construction, not a cosmetic timestamp.
