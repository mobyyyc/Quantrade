# Feature Definitions

This registry is the product and research contract for every feature used by
Quantrade. A feature is a dated input to a later model, not a trade signal or
investment recommendation. Its key, version, formula, required inputs, and
decision-time rule are immutable. A material change creates a new version.

All features use the point-in-time panel: only facts and bars with
`available_at <= decision_at` are eligible. A missing input makes the feature
unavailable; it must never be silently imputed or substituted.

| Key @ version | Family | Direction | Definition |
| --- | --- | --- | --- |
| `momentum_12_1@v1` | Momentum | Higher is better | Split-adjusted close at `t - 21` divided by close at `t - 252`, minus one. |
| `relative_strength_6m@v1` | Momentum | Higher is better | Security six-month split-adjusted return less the benchmark return over the same 126 sessions. |
| `earnings_yield_ttm@v1` | Value | Higher is better | Historical definition: TTM `NetIncomeLoss` divided by split-adjusted market capitalization. |
| `earnings_yield_ttm@v2` | Value | Higher is better | TTM `NetIncomeLoss`, falling back only to SEC standard `ProfitLoss`, divided by split-adjusted market capitalization. |
| `return_on_assets_ttm@v1` | Profitability | Higher is better | Historical definition: TTM `NetIncomeLoss` divided by the average of beginning and ending total assets. |
| `return_on_assets_ttm@v2` | Profitability | Higher is better | TTM `NetIncomeLoss`, falling back only to SEC standard `ProfitLoss`, divided by the average of beginning and ending total assets. |
| `trailing_volatility_60d@v1` | Risk | Lower is better | Annualized standard deviation of 60 split-adjusted daily log returns. |
| `median_dollar_volume_20d@v1` | Liquidity | Higher is better | Median unadjusted close multiplied by volume over 20 sessions. |

## Input and time rules

- Price features use completed regular sessions only. Momentum, relative
  strength, and volatility use `split_adjusted` bars; dollar volume uses
  `unadjusted` bars.
- Benchmark observations for relative strength must satisfy the same
  availability rule as the security observations.
- Fundamental features use SEC filing facts only when the filing acceptance
  time is available by the decision timestamp. A fiscal period end is not an
  availability timestamp.
- `t` is the formation session. No feature may use a bar, corporate action, or
  filing fact that became available after the chosen decision timestamp.

The executable registry lives in
`services/research/src/quantrade_research/features.py`; its canonical JSON
payload produces a SHA-256 definition hash. The normalized store records the
same metadata and prevents definition updates or deletes.

P3.2 implements the two momentum-family definitions in
`services/research/src/quantrade_research/momentum.py`. They reject incomplete
windows, duplicate dates, non-positive prices, bars unavailable by the decision
timestamp, and non-matching security/benchmark session windows.

P3.3 implements `earnings_yield_ttm@v2` and `return_on_assets_ttm@v2` in
`services/research/src/quantrade_research/fundamentals.py`. To avoid silently
assembling unreported quarters, v2 uses one eligible annual `NetIncomeLoss`
fact, falling back only to the SEC standard `ProfitLoss` fact, whose duration
is 330–370 days. Return on assets also requires eligible
`Assets` facts exactly at that reported period's start and end; earnings yield
requires an eligible positive shares-outstanding fact and formation close.

P3.4 implements `trailing_volatility_60d@v1` and
`median_dollar_volume_20d@v1` in
`services/research/src/quantrade_research/risk_liquidity.py`. Volatility uses
60 daily log returns (and therefore 61 closes), sample standard deviation, and
the square root of 252 annualization. Dollar volume uses unadjusted closes and
volumes, requiring a complete 20-session window.

P3.5 adds fail-closed diagnostics in
`services/research/src/quantrade_research/feature_diagnostics.py`. Each
security-feature pair must publish either a value or an explicit unavailable
reason. Reports show per-feature coverage and missingness, correlations only
across paired available values, and turnover of direction-aware top buckets
between two formation dates.

P4.1 normalizes each available feature within its dated sector cohort in
`services/research/src/quantrade_research/ranking.py`. Percentiles are tie-aware
and always oriented so `1` is better: lower-is-better features are inverted.
Sector classifications must be known by the decision timestamp. A cohort with
fewer than two available peers is explicitly unavailable rather than ranked
against a different sector.

P4.2 builds `baseline_equal_weight_v1` in
`services/research/src/quantrade_research/baseline.py`. The model averages all
required percentile ranks equally and presents that normalized value on a 0–100
scale. It does not learn weights or substitute missing ranks: any unavailable
required rank makes the composite explicitly ineligible.

P4.3 turns every baseline rank into an explanation row in
`services/research/src/quantrade_research/explanations.py`: it includes the
sector percentile, fixed equal weight, and contribution (`percentile × weight`).
Explanation rows for unavailable ranks retain their reason rather than a made-up
contribution. Migration `0006_add_score_explanations.sql` stores these rows as
immutable children of a score snapshot.

P4.4 implements the protocol's next-open portfolio handoff in
`services/research/src/quantrade_research/rebalance.py`. It selects exactly the
highest eligible 20 baseline scores at equal weights, values every prior holding
at the strictly later execution-session open, then sells the prior basket before
buying the new one. Costs and liquidity constraints are deliberately added in
P4.5, not assumed here.

P4.5 adds the provisional research evaluation gates in
`services/research/src/quantrade_research/evaluation.py`: every target needs a
dated median dollar volume of at least USD 10 million, the baseline applies a
5-bps one-way cost with 1/10/20-bps sensitivity reports, and dated portfolio
NAVs are compared directly with benchmark NAVs. Metrics are research diagnostics
only while the project remains Tier B.
