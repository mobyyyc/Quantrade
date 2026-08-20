# Quantrade Project Plan

## V1 decision

V1 is a private beta and future public-release candidate. It must feel product-quality, but it is research-first and does not provide brokerage execution, personalized investment advice, or promises of returns.

The initial data policy is free-first. The team will use free sources until a documented limitation blocks valid research or product quality, then evaluate paid providers using the criteria in `DATA_STRATEGY.md`.

## Product objective

Help a user answer three questions for a US equity: what is happening, why, and what does the currently validated quantitative model suggest, including risk and uncertainty.

## V1 scope

- Daily end-of-day scores for a defined US-equity universe.
- Point-in-time daily market data, corporate-action handling, SEC fundamentals, and optional macro context.
- A compact factor set: momentum, value, profitability, and risk/liquidity.
- Cross-sectional ranking, a transparent baseline model, and cost-aware walk-forward backtests.
- Ranking, search, stock detail, and internal research-dashboard experiences.
- Model cards, score explanations, data freshness, and a clear research disclaimer.

## Explicit V1 exclusions

- Intraday or real-time trading signals.
- Brokerage connectivity, live orders, or personalized advice.
- Social sentiment, options flow, earnings-call NLP, global markets, and deep learning.
- A claim that backtest results are investable until universe and delisting coverage pass the data-quality gate.

## Milestones

1. Research charter and data decision.
2. Reproducible foundations and provider-neutral contracts.
3. Point-in-time historical-data pipeline and quality checks.
4. Feature and factor research.
5. Transparent baseline ranking model.
6. Cost-aware backtesting and chronological validation.
7. Versioned production scoring and read API.
8. Private-beta web experience and research dashboard.
9. Monitoring, operational documentation, and controlled expansion.

## Release gates

- Every score is reproducible from source data cutoff, feature version, model version, and configuration.
- No score is published from stale, incomplete, or failed source data.
- The backtest uses information available at the decision time and next-session executable prices.
- Any model promoted beyond the baseline beats pre-defined out-of-sample gates after costs.
- Every user-facing score exposes its as-of timestamp, evidence, risk, and model version.
