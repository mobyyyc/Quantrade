# Current-model Exact-Zero Eligibility Rollout

**Decision:** approved for future live scores on September 10, 2026

**Active model:** `tier_b_monthly_elastic_net_sec_clean_v3`

**Eligibility contract:** `exact_zero_coefficients_v1`

**Score snapshot protocol:** `score_snapshot_exact_zero_v1`

## What changed

Future live scoring now requires only inputs whose serialized model coefficient
is mathematically non-zero. Missing zero-weight inputs are replaced by their
frozen training mean solely to preserve the artifact's complete arithmetic
sequence. No tolerance is used: any coefficient other than exactly `0.0`
continues to require its input.

The active artifact, its coefficients, raw prediction formula, and existing
score snapshots are unchanged. Previously eligible rows therefore retain the
same raw predictions. The larger eligible peer set can change future percentile
display scores and ranks; that is the intended, versioned universe effect.

Historical replay explicitly remains on `all_serialized_inputs_v1` with the
legacy `0.1` score protocol. A completed live date is also reused rather than
recalculated, so rollout begins with the first future publication after this
change.

## Evidence

The Phase 9D audit compared 82,609 previously eligible historical rows and found
zero byte-level raw-prediction mismatches. Its authenticated logical SHA-256 is
`d4d1ed92f7e7a6fc770d4e56703798f766b90937861989ca31e96a314a2b697a`.

A read-only dry run against the September 10, 2026 live publication found:

| Measure | Count |
| --- | ---: |
| Published snapshots | 500 |
| Previously eligible | 462 |
| Eligible under corrected rule | 495 |
| Newly eligible | 33 |
| Still excluded | 5 |

All 33 additions were missing only zero-weight inputs. The five remaining
exclusions still lack at least one non-zero momentum, volatility, or liquidity
input. The detailed security-level reasons and deterministic logical hash are in
the local ignored artifact
`data/derived/live_exact_zero_eligibility_rollout_v1.json`.

Reproduce the read-only dry run with:

```powershell
py -3.14 -m quantrade_research.live_eligibility_rollout --env-file .env `
  --destination data/derived/live_exact_zero_eligibility_rollout_v1.json
```

## Rollback

Set the following local configuration before a future update and restart an
already-running web server:

```dotenv
SCORE_ELIGIBILITY_CONTRACT=all_serialized_inputs_v1
```

This produces future snapshots under the distinct
`score_snapshot_all_inputs_v1` protocol. It does not delete or update existing
scores. Restore `exact_zero_coefficients_v1` to return to the approved rule.
