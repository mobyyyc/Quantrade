# V1 Experiment Protocol

## Status

Version 0.2. This protocol governs every baseline backtest and research run until it is replaced by a dated, committed version. It operationalizes the scope in `RESEARCH_CHARTER.md`.

## Clock and decision sequence

All timestamps use America/Toronto time.

1. Historical replay uses `historical_replay_2000_toronto_v1`: a fixed 8:00 p.m. decision timestamp and only records public by that timestamp.
2. Live daily publication uses `live_after_validation_v1`: after market close, incremental ingestion and validation finish first, then `decision_at` captures the actual local time. The normal scheduler currently begins around 10:15 p.m.
3. A failed live attempt without immutable scores does not reserve its earlier cutoff. Its retry receives a new actual post-validation timestamp, so later-retrieved information is never backdated.
4. The score is never executed at that same closing price.
5. On a rebalance date, execute model trades at the next eligible regular-session open.

If completeness is not confirmed, no score is published. Missing market observations may be caught up later, but scores and official holdings are never backfilled. A missed month-end execution window is recorded as unavailable instead of being reconstructed with later knowledge.

## Rebalance rule

- Score snapshots are produced daily when source data passes checks.
- The baseline portfolio rebalances once per month.
- Formation date: the final eligible US trading day of each calendar month.
- Execution date: the next eligible US trading day at the regular-session open.
- The next formation date closes the prior portfolio at the following rebalance execution price before the new portfolio opens.

Market holidays, missing next-day opens, and halted securities are not silently substituted. Each is recorded as a data or execution exception.

## Feature availability

- Price-based features use data through the formation-date regular-session close.
- Fundamental features may only use filings accepted and available by the applicable versioned decision timestamp.
- Macro features may only use the relevant historical vintage available by the decision timestamp.
- Features must be calculated before ranking, then cross-sectionally normalized within the eligible universe.

## Baseline portfolio

- Long-only and fully invested, with no leverage, shorting, borrowing, or cash yield.
- Select the 20 highest-ranked eligible securities.
- Weight each selected security equally at formation.
- Do not apply sector caps in the first baseline. Report sector concentration as a diagnostic; sector-neutral construction is a later, separately pre-registered comparison.
- Assume fractional shares for analytical return calculations. Report capacity separately rather than concealing it with whole-share rounding.

If fewer than 20 securities are eligible, the run is invalid rather than silently changing the portfolio rule.

## Eligibility and liquidity

A security is eligible only when it has:

- A stable security identity and a current constituent-snapshot membership record.
- Sufficient trailing observations to calculate every required feature.
- A valid next-session regular-session open for execution.
- A trailing 20-session median dollar volume of at least USD 10 million.

The dollar-volume rule is provisional until P0.3 confirms the free source's volume and adjustment behavior. If the audit cannot validate it, liquidity-based capacity conclusions are disabled rather than estimated.

## Prices and corporate actions

- Use adjusted prices only for returns and price-based features after their adjustment methodology is reconciled.
- Use unadjusted next-session open prices for simulated entries and exits.
- Apply splits to position quantities and dividends to cash in the execution ledger.
- If the source cannot support this separation consistently, backtests remain research diagnostics and cannot pass the production-model gate.

## Costs and sensitivities

The baseline applies a 5-basis-point one-way cost to every entry and exit. It represents combined slippage and residual trading costs; explicit commission is set to zero.

Every reported result also includes 1, 10, and 20 basis-point one-way sensitivity cases. The strategy must not be judged only by the lowest-cost case.

## Benchmark and measurements

- Benchmark: SPY, held with the same formation and next-open execution convention.
- Primary prediction measure: 20-session stock return less the matching SPY return.
- Portfolio measures: cumulative return, CAGR, annualized volatility, Sharpe ratio, Sortino ratio, maximum drawdown, Calmar ratio, turnover, exposure, and benchmark-relative return.
- Ranking measures: Spearman rank information coefficient, hit rate, top-versus-bottom spread, factor coverage, factor correlation, and score stability.

All reported values must state the protocol version, model version, feature version, source-data cutoff, and data capability tier.

## Prohibited shortcuts

- No same-close fills for close-derived scores.
- No random time-series splits.
- No filling missing prices, fundamentals, or execution prices without a documented exception.
- No parameter tuning on the final holdout period.
- No replacing invalid or missing securities with convenient substitutes after seeing results.

## Definition of done for P0.2

- The protocol is committed before backtest implementation.
- The research charter and roadmap link to it.
- Future code can implement every timing, cost, and portfolio rule without interpretation.
