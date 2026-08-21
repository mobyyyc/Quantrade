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
- [Operational monitoring](OPERATIONAL_MONITORING.md)
- [Recovery runbook](RECOVERY_RUNBOOK.md)
- [Release runbook](RELEASE_RUNBOOK.md)

## Initial V1 direction

- Private, product-quality beta for a simple daily research workflow.
- Free-data-first: SEC EDGAR, Alpaca Basic, and FRED/ALFRED.
- Transparent factor ranking before advanced machine learning.
- Point-in-time data integrity, cost-aware backtesting, and model versioning before user features.
