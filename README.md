# Quantrade

Quantrade is a private-beta quantitative US-equity research platform. It is designed to turn validated market and fundamental research into simple, understandable, dated stock views.

It is a research and decision-support tool. It does not provide personalized investment advice, guarantee returns, or execute trades.

## Status

Private-beta application, research pipeline, and operational safeguards are
implemented. Real-data operation still requires a configured PostgreSQL
database, durable artifact storage, and the free-provider credentials described
in `.env.example`.

## Guiding documents

- [Product context](PRODUCT.md)
- [Design system seed](DESIGN.md)
- [Project plan](PROJECT_PLAN.md)
- [Architecture](ARCHITECTURE.md)
- [Data strategy](DATA_STRATEGY.md)
- [Roadmap](ROADMAP.md)
- [Research charter](RESEARCH_CHARTER.md)
- [Experiment protocol](EXPERIMENT_PROTOCOL.md)
- [Free-data provider audit](FREE_DATA_AUDIT.md)
- [Data capability decision](DATA_CAPABILITY_DECISION.md)
- [Historical free-track coverage](data/derived/historical-coverage/)
- [Operational monitoring](OPERATIONAL_MONITORING.md)
- [Recovery runbook](RECOVERY_RUNBOOK.md)
- [Release runbook](RELEASE_RUNBOOK.md)

## Initial V1 direction

- Private, product-quality beta for a simple daily research workflow.
- Free-data-first: SEC EDGAR, Alpaca Basic, and FRED/ALFRED.
- Transparent factor ranking before advanced machine learning.
- Point-in-time data integrity, cost-aware backtesting, and model versioning before user features.

## Historical free research track

The current-survivors historical lane is explicitly Tier B: it is a fixed,
survivorship-biased S&P 500 cohort with static current sectors. After a market
backfill, create an auditable local coverage report with:

```powershell
$env:PYTHONPATH = (Resolve-Path 'services/research/src').Path
py -3.14 -m quantrade_research.historical_market_coverage `
  --start 2016-01-01 --end 2026-06-30 `
  --output data/derived/historical-coverage/sp500_current_survivors_v1_2016-01-01_2026-06-30.json `
  --env-file .env
```

The generated report is deliberately local and ignored by Git: it contains the
actual provider coverage and exclusions for that run. It must be reviewed before
building a training export.
