# Quantrade Architecture

## System flow

```text
Data providers
  -> immutable raw records
  -> normalized point-in-time store
  -> versioned feature panel
  -> factor scores and model
  -> risk adjustment and calibrated score
  -> score snapshots and model cards
  -> read API
  -> private-beta web application
```

## Recommended boundaries

- `apps/web`: Next.js, TypeScript, read-only product and research surfaces.
- `services/research`: Python data ingestion, feature generation, experiments, backtests, and scheduled scoring.
- `packages/contracts`: provider-neutral schemas shared by the API and research services.
- PostgreSQL: normalized operational and research metadata.
- Object storage: immutable raw provider payloads and reproducible run artifacts.

## Time integrity

Every record must preserve, where applicable:

- `observed_at`: when a market observation occurred.
- `published_at`: when its source published it.
- `available_at`: earliest permitted model-use time.
- `ingested_at`: when Quantrade retrieved it.

The panel builder must reject any observation whose `available_at` is after the decision time. Financial-statement features must use filing availability, not only fiscal-period end dates.

## Model path

The first model is an interpretable sector-aware percentile rank of a small factor set. It predicts and ranks 21-trading-day benchmark-relative return, with decisions produced after close and simulated execution at the next regular-session open.

Risk adjustment uses only ex-ante volatility, drawdown, and liquidity. A 0-100 score and signal are calibrated from validation, never assigned arbitrary labels. Explanations are calculated from stored feature and factor contributions.

## Initial data model

- Security, listing, ticker history, and historical universe membership.
- Daily price bars, corporate actions, and data-source metadata.
- Filing, fact, period, accepted timestamp, and source-document reference.
- Feature definition/version, factor snapshot, model version, score snapshot, and explanation.
- Backtest run, configuration, transactions, equity curve, metrics, and artifacts.

## Non-negotiable controls

- Private keys only in server-side configuration.
- Provider adapters are interchangeable.
- Pipelines are idempotent and preserve prior approved score snapshots.
- Failed data-quality checks block publication.
- Model changes require an explicit version, card, validation record, and rollback path.
