# Phase 9D exact-zero eligibility audit — September 9, 2026

Status: P9D.1 research audit passed; live eligibility remains unchanged.

Audit key: `phase_9d_exact_zero_eligibility_audit:v1`

## Decision

The deployed `tier_b_monthly_elastic_net_sec_clean_v3` artifact serializes six
feature columns, but only three coefficients are mathematically non-zero:
momentum 12–1, trailing volatility 60d, and median dollar volume 20d. Missing
values for the other three columns cannot alter the raw prediction and therefore
should not exclude a row in the corrected research policy.

The correction is suitable for the P9D research anchor. It is **not enabled for
live scores by this task**. A live eligibility rollout would change the peer set,
display scores, ranks, and explanations, and still requires explicit approval.

## Historical audit results

The authenticated Phase 9C panel contains 91,500 rows: 500 fixed current-survivor
companies across 183 weekly formations from January 2022 through June 2025.
Prices were restricted to the historical 8:00 p.m. Toronto cutoff. SEC facts used
the same acceptance-plus-five-minute rule documented by P12.8.

| Check | Result |
| --- | ---: |
| Previously eligible rows | 82,609 (90.2831%) |
| Corrected eligible rows | 89,392 (97.6962%) |
| Newly eligible rows | 6,783 |
| Minimum corrected weekly coverage | 95.6000% |
| Previously eligible raw predictions compared | 82,609 |
| Byte mismatches | 0 |
| New rows missing a non-zero input | 0 |

Every frozen gate passed: aggregate coverage is above 95%, every weekly
formation is above 90%, newly admitted rows are attributable only to missing
exact-zero inputs, and old raw predictions are byte-identical.

## User-visible impact if separately approved later

Raw predictions for existing eligible rows do not move. Cross-sectional display
values do move because 6,783 valid observations join their weekly peer sets:

- 82,275 existing company-week display scores change, by 1.0231 points on
  average and at most 4.1623 points;
- 81,543 existing company-week ranks change, by 23.21 positions on average and
  at most 42 positions; and
- explanation math for existing rows does not change. The corrected universe
  would add 20,349 explanation rows (three active inputs for each new row).

These are ranking-universe effects, not changes to the model coefficients or raw
predictions.

## Implementation and reproducibility

`quantrade_research.model_eligibility` is now the shared implementation for
exact coefficient classification and raw prediction arithmetic. The live scorer
calls it in its legacy all-input mode by default. The audit calls the corrected
exact-zero mode. No numeric tolerance is allowed: the rule is serialized
`coefficient != 0.0`, so even the smallest representable non-zero coefficient
remains required.

Two complete audit runs produced the same logical audit SHA-256:
`d4d1ed92f7e7a6fc770d4e56703798f766b90937861989ca31e96a314a2b697a`.
The local detailed artifact is
`data/derived/phase_9d_exact_zero_eligibility_audit_v1.json`; its file SHA-256 is
`dd7bb338eee1ec3749d4555b5e37cde21aa3dc6745898748f18478f2d2a20120`.

Re-run from the repository root with PostgreSQL available and `.env` configured:

```powershell
py -3.14 -m quantrade_research.phase_9d_eligibility_audit --env-file .env
```

The audit is read-only with respect to PostgreSQL and does not download data,
publish scores, register a model, or change the active deployment.

## Evidence boundary

This remains Tier-B current-survivor research with static present-day sectors.
It is not an unbiased historical-performance claim. P9D.2 may consume the
corrected research anchor under the amended fold-local protocol; P9D.1 alone
does not support deployment or model promotion.
