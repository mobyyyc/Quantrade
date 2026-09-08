# Elastic-net swap review

Registered September 7, 2026 before this direct comparison.

Compare only the authenticated deployed elastic-net specification and the new
final research elastic-net specification. Refit each fixed recipe on earlier-only
monthly training rows for the existing four chronological outer windows. All
inputs, labels, validation rows, and next-open 20-session conventions are shared.
Do not reuse either final fit to score its own training period. Do not tune more
configurations after this comparison or reopen July 2025–June 2026 for selection.

Report paired rank IC, Top-20 relative returns, membership turnover, forecast
errors, and three-month block-bootstrap uncertainty in monthly IC differences.
Use the existing clean monthly dataset's split-adjusted labels and legacy
turnover-based cost sensitivities as explicitly limited diagnostics, not as a
substitute for the corporate-action-aware execution ledger or a tradable NAV.
The candidate penalty was selected using this development history previously;
this direct fixed-recipe comparison is therefore retrospective diagnostics,
not a fresh nested selection experiment or independent confirmation.

Swap only if superiority is supported AND existing promotion requirements are
met. Correct evaluation code alone is not evidence of superior model performance.
If evidence is inconclusive, worse, or lacks untouched confirmation, retain the
live model, scores, and portfolio history. No owner exception is authorized.

## Completed result: no swap

The registered active artifact was authenticated and reproduced from its original
training dataset; the candidate's parameters reproduced exactly as well. Both
use L1 0.001. Current L2 is 0.001; new L2 is 0.1. This is a regularization change,
not a new data source or architecture.

Compared 10,012 identical validation rows over 22 month-end formations, July
2023–April 2025. Every fold refit uses only outcomes completed before validation.

| Diagnostic | Current recipe | New recipe |
| --- | ---: | ---: |
| Mean month-end rank IC | -0.000215 | -0.000683 |
| Mean Top-20 gross 20-session relative return | +0.3753% | +0.2100% |
| Legacy 25-bp turnover-cost relative-return diagnostic | +0.2765% | +0.1112% |
| Mean membership turnover | 39.52% | 39.52% |
| Return forecast MAE | 5.5732 percentage points | 5.5719 percentage points |

The new recipe's mean IC is lower in all four outer blocks. Its IC improvement
interval is [-0.001141, +0.000065]; only 4.79% of block-bootstrap resampled deltas
are positive. This is not a posterior probability of model superiority. Both
mean IC values are essentially zero on these month-end observations, so these
results do not establish that either recipe has reliable predictive skill.

Top-20 membership is identical in 15 of 22 formations; the remaining seven differ
by one stock each. A tiny forecast-error improvement does not offset weaker
ranking and basket diagnostics for the app's ranking objective. The cost figures
above use the existing simplified turnover-cost calculation and split-adjusted
labels; they are not corporate-action-complete, compounded official performance.

This table differs from the previous 0.0188 versus 0.0060 comparison: that compared
elastic net with ridge on WEEKLY formations and wealth labels. This comparison
isolates two elastic-net settings on identical MONTH-END data and legacy labels.
Do not mix the two samples or interpret the figures as contradictory live returns.

Decision: **retain `tier_b_monthly_elastic_net_sec_clean_v3`**. No model registry,
deployment, scores, or official portfolios were modified. The requested "if better"
condition is not met, and untouched confirmation requirements were not waived.

Reproduce the read-only check from the repository root:

```powershell
py -3.14 -m quantrade_research.elastic_net_swap_review
```

Source dataset SHA-256: `fedea95f6a44db6316c9dc01e073f1dad0e1a7ac67ef8ae7ed0ef1c7c6592b26`.
Active artifact SHA-256: `36d6accf1c207fa448a4e6908ee7b525e7c811af66fc28fd36c4b4d66bc00294`.
Candidate final-fits hash: `0fdcf3c5a73ceadf3fdb9477c16ce1d02f91280455dc2a6a44b433490bf707e0`.
