# Next-Generation Feature Diagnostics: `next_gen_free_v1`

## Decision

P9.3 is complete. Two candidates may proceed to pre-holdout model comparison;
two are rejected at their current versions.

| Candidate | Coverage | Minimum monthly coverage | Closest active feature (median absolute correlation) | Median rank stability | Median top-20 turnover | Decision |
| --- | ---: | ---: | --- | ---: | ---: | --- |
| `downside_volatility_60d@v1` | 98.24% | 97.00% | `trailing_volatility_60d` (0.8721) | 0.8314 | 0.50 | **Proceed** |
| `return_on_assets_change_yoy@v1` | 95.50% | 93.00% | `earnings_yield_ttm` (0.2407) | 0.9813 | 0.00 | **Proceed** |
| `amihud_illiquidity_20d@v1` | 97.63% | 96.60% | `median_dollar_volume_20d` (0.9135) | 0.9207 | 0.25 | **Reject:** exceeds the frozen 0.90 redundancy ceiling. |
| `short_term_reversal_20d@v1` | 98.33% | 97.20% | `relative_strength_6m` (0.3534) | 0.0370 | 0.95 | **Reject:** stability is below 0.10 and turnover exceeds 0.90. |

Proceed means only that the feature passed these data-quality diagnostics. It
does not establish predictive value and does not add the feature to the active
model. P9.4 must compare models using the two proceeding candidates on purged
development folds.

## Sample and integrity

- Protocol: `next_gen_feature_diagnostics_v1`
- Cohort: `sp500_current_survivors_v1` (Tier B, survivorship-biased, static
  current-sector grouping)
- Sample: 42 final monthly formations from January 31, 2022 through June 30,
  2025; 500 securities; 21,000 expected observations per feature
- Holdout: not read or used; July 2025 through June 2026 remains excluded
- Point-in-time violations: zero for every candidate
- Candidate result hash:
  `998e8e362a6742b554ca0a129b3210dd2ac7e58584f34ea647a2dc283e9b2b2a`
- Two independent exports produced identical file SHA-256:
  `fbc6545774ee1e6da6f59ae5fdb86a3a5225830c909f612cc8865326921c46ef`

The executable report refuses to overwrite an existing artifact. It can be
reproduced locally with:

```powershell
py -3.14 -m quantrade_research.candidate_feature_diagnostics --output data\derived\feature-diagnostics\next_gen_free_v1.json --env-file .env
```

## Missingness

Every exclusion remained explicit; no value was imputed or repaired.

| Candidate | Exclusions across 21,000 expected observations |
| --- | --- |
| `amihud_illiquidity_20d@v1` | 343 missing formation bars; 148 non-positive dollar-volume observations; 7 insufficient histories |
| `downside_volatility_60d@v1` | 343 missing formation bars; 26 insufficient histories |
| `return_on_assets_change_yoy@v1` | 656 insufficient two-year annual histories; 232 missing asset endpoints; 57 non-consecutive annual periods |
| `short_term_reversal_20d@v1` | 343 missing formation bars; 7 insufficient histories |

## Interpretation boundary

This is private Tier-B research using a fixed cohort of current S&P 500
survivors. The results are not unbiased historical-index evidence, investment
advice, or a guarantee of future performance. Rejected feature versions remain
rejected unless a materially different definition is registered under a new
version and evaluated without using the holdout.
