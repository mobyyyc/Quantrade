# Corrected model evaluation — September 7, 2026

Status: P9D.0b repair verified; diagnostic research only, no deployment.
Protocol: `MODEL_EVALUATION_REPAIR_PROTOCOL.md` (registered before corrected fits).

## What changed

- Reference coefficients and training statistics are now refit per chronological
  window using the original SEC-clean monthly elastic-net family and target.
  Its six penalty configurations are selected within earlier inner windows only.
- The existing weekly six-family ridge uses four inner-only penalty choices.
- Both models are evaluated on identical reference-complete outer rows and the
  same corporate-action-aware, next-open 20-session wealth-relative labels.
- Actual label-end dates are checked, not just the recorded purge audit flag.
- Reference peer ranks are constructed over the full feature-panel universe
  before joining future labels. Late bars are conservatively excluded from the
  legacy reference reconstruction, and SEC facts receive a five-minute buffer.
- Final-artifact replay is no longer an out-of-sample reference. The old runner
  is blocked unless explicitly invoked for archival reproduction.
- Output directories cannot be overwritten. No training command registers or
  deploys a model, ingests data, or writes to PostgreSQL.

## Paired results

The four outer windows span July 2023–May 2025. They contain 44,230 matched
stock/date predictions per model across 99 weekly formations and 23 calendar
months. Of 47,641 available labelled outer rows, 3,411 lack complete reference
inputs and are excluded from BOTH sides; that sample limitation is not hidden.

| Diagnostic | Monthly elastic-net family, refit | Weekly six-family ridge, refit |
| --- | ---: | ---: |
| Equal-month mean rank IC | 0.018820 | 0.006031 |
| July–December 2023 IC | 0.000093 | 0.044510 |
| January–June 2024 IC | 0.035290 | -0.017070 |
| July–December 2024 IC | 0.054027 | 0.034287 |
| January–May 2025 IC | -0.020721 | -0.046332 |

Rank IC measures agreement between predicted ordering and realized ordering;
it is not a percentage accuracy or expected return. Both models are weak and
unstable in parts of the sample. The elastic-net family has the higher observed
aggregate ranking diagnostic in this comparison; this is NOT proof that the
deployed final artifact achieves the same out-of-sample performance.

Challenger-minus-reference IC: **-0.012789**. The deterministic three-month
moving-block bootstrap gives a 95% interval of **[-0.049628, 0.027310]**, with
25.36% of resampled deltas above zero (10,000 resamples, seed 20260830). This is
not a posterior probability that one model is truly better. The interval includes
zero, so superiority is not established. There is no basis here for promoting
the six-family ridge over the current model family.

The local report also contains weekly Top-20 gross relative-return diagnostics.
Those overlapping 20-session windows are not a monthly tradable portfolio,
net-of-cost backtest, annualized return, or official performance. They are not
used to select or promote a model. Monthly portfolio, cost, turnover, stability,
coverage, and untouched-forward gates remain separate requirements.

## Reproducibility and artifacts

Two completed runs produced identical outer predictions, fold fits, and final
research fits. The replay took approximately 50 seconds after its start manifest
was written. All 361 research tests passed, including nine repair tests covering
actual-outcome overlap, holdout rejection, non-finite inputs, fold integrity,
future-row isolation, peer-universe independence, deterministic bootstrap,
immutable output, and the archival-run guard.

Canonical local run: `data/derived/evaluation-repair/20260907-v1-replay/`.
First successful run: `data/derived/evaluation-repair/20260907-v1-checked/`.
An initial unsuccessful implementation run is retained at `20260907-v1/`; it
has no completed report and is not an evaluated model. Its missing ridge getter
argument was corrected before both successful runs.

- Predictions SHA-256: `96e4caaeeb2ce0d5b99e4bdb3210e4b22f3c4ae2e965b6f26a690b12736023a2`
- Fold fits canonical SHA-256: `0c03fb7ba41ecc2cd0a376307df8dbea65df3923abff77b72fb67de1547d17b9`
- Final fits canonical SHA-256: `0fdcf3c5a73ceadf3fdb9477c16ce1d02f91280455dc2a6a44b433490bf707e0`

Final research fits use the last outer block's inner-selected penalties, NOT a
choice optimized against the outer results. Elastic net uses L1 0.001/L2 0.1;
ridge uses penalty 1.0. The elastic-net coefficient order is momentum 12–1,
relative strength 6m, volatility 60d, dollar liquidity 20d, earnings yield, ROA.
The ridge order is momentum/trend, reversal, value, profitability/quality,
investment/issuance, risk. These are research-only parameter records, not
deployment-ready artifacts or an approved replacement for the live registry.

## Limits and next steps

This is an end-to-end comparison of two recipes, not an isolated test of
elastic net versus ridge: their training targets, features, and sampling differ.
The data remain Tier-B current-survivor/static-sector research. Development
history has informed earlier research decisions; refitting cannot undo that
researcher exposure. July 2025–June 2026 was not read and remains consumed,
report-only history. Earlier no-freeze records remain intact, but their exact
final-artifact comparisons must not be interpreted as fair out-of-sample proof.

The live model is unchanged. P9D.1 eligibility correction and the later
cross-fitted accounting-residual challenger are NOT implemented by this repair.
Resume P12.7 operational reliability next, per the approved priority override.

## Repeat the training/evaluation

From the repository root, with PostgreSQL running and local `.env` configured:

```powershell
.\scripts\run-model-evaluation-repair.ps1
```

The script creates a new timestamped run folder, prints one progress message per
major stage/block, and reports its output path. It requires neither new provider
downloads nor opening the website. No holdout or live deployment is performed.
