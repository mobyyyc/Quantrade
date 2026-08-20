# Quantrade Research Charter

## Status

Version 0.1. This is the pre-registered V1 research scope. A change to the target, universe, factor family, trading assumption, or evaluation rule requires a dated decision record before results are compared.

## Research question

Can a small, interpretable set of point-in-time market and fundamental factors rank eligible US equities by their subsequent 21-trading-day return relative to the S&P 500 proxy, after realistic execution assumptions?

The first objective is evidence, not an investable claim. A negative or inconclusive result is a valid outcome.

## Beta universe

- Initial operational universe: the current S&P 500 constituent snapshot, captured with its source date at ingestion.
- Eligibility: US-listed common equities with sufficient available daily-price and fundamental history for a requested score date.
- Benchmark: SPY adjusted-price return, subject to data-quality reconciliation.
- Research capability: Tier B until historical constituent membership and delisted-security coverage are verified.

Tier B means the project may use results to develop the private beta and compare hypotheses, but may not present them as unbiased historical S&P 500 performance.

## Target and score

- Primary target: 21-trading-day forward benchmark-relative return.
- Secondary diagnostics: rank information coefficient, hit rate against SPY, top-versus-bottom rank spread, coverage, turnover, and factor stability.
- Initial score: transparent, sector-aware percentile aggregation of momentum, value, profitability, and risk/liquidity factors.
- Initial model policy: no learned factor weights, tree models, neural networks, or sentiment inputs until the transparent baseline is complete and validated.

The user-facing 0-100 score is a calibrated presentation layer. It must not be treated as a probability, expected return, or trade instruction unless later validation supports that interpretation.

## Initial portfolio hypothesis

The first portfolio diagnostic is a simple equal-weight long-only basket of the highest-ranked eligible securities, compared with SPY. Portfolio size, sector caps, transaction-cost parameters, and execution timing are fixed in `EXPERIMENT_PROTOCOL.md`.

No optimization is permitted in the first baseline.

## Data policy

| Category | Initial source path | Required treatment |
|---|---|---|
| Daily market data | Alpaca Basic | Persist raw responses, record feed and retrieval time, audit adjustment behavior. |
| Fundamentals | SEC EDGAR | Use filing acceptance and availability time, not only fiscal period end. |
| Macro context | FRED/ALFRED | Use only dated observations available at the decision time. |
| Universe membership | Current constituent snapshot | Mark results Tier B until point-in-time membership is obtained. |

All raw records, normalized records, features, scores, and backtest outputs must be traceable to a source, timestamp, configuration, and code revision.

## Evaluation policy

- Chronological expanding-window and walk-forward validation only.
- A final holdout period is locked before model selection.
- Every backtest includes costs, turnover, drawdown, and benchmark comparison.
- Every signal is based solely on information available at the stated decision time.
- A model may not be promoted because of one strong period or one attractive Sharpe ratio.

## V1 exclusions

- Intraday signals, options, social sentiment, earnings-call NLP, and analyst estimates.
- Shorting, leverage, portfolio optimization, and brokerage execution.
- Claims of historical performance that require unverified constituent or delisting data.
- Automatic user alerts or trade language.

## Paid-data upgrade triggers

The project evaluates paid data only when a documented need blocks one of these outcomes:

1. Point-in-time universe membership with delisted securities.
2. Longer, auditable adjusted-price history.
3. Guaranteed corporate-action and fundamental-availability treatment.
4. Public-data display or real-time coverage.

## Definition of done for P0.1

- This charter is committed before data ingestion or factor implementation.
- The data capability tier is visible in all resulting research reports.
- The execution protocol is committed and does not contradict this charter.
