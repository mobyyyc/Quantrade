# Phase 9D anchored-residual training — September 10, 2026

Status: P9D.3 complete; deterministic outer predictions ready for P9D.4.

Model key: `anchored_accounting_residual_ridge_v1`

## Outcome

The preregistered two-input residual ridge was fit inside the existing four
chronological Phase 9C outer folds. The implementation evaluates exactly three
penalties (`1`, `10`, and `100`), uses only the registered investment/issuance
and profitability/quality correction families, and fits no intercept. It does
not search additional features, penalties, model families, or constraints.

For every row, the candidate score is the chronological cross-fitted
elastic-net anchor centered rank plus the ridge-predicted residual. The trainer
wrote 44,828 deterministic outer predictions and four fold-local fit records.
It serialized the labels needed by P9D.4 but deliberately did not calculate or
inspect any outer performance result in this task.

## Chronological fitting and selection

Within each outer fold, the penalty is selected only from earlier inner
validation episodes. Training observations are admitted only when their
20-session outcome is complete strictly before the corresponding validation
window begins. Calendar months receive equal total weight.

The registered tie break selects the larger penalty when its mean monthly rank
IC is within `0.002` of the best inner result. The selected outer-fold fits were:

| Outer block | Training rows | Validation rows | Penalty | Investment/issuance coefficient | Profitability/quality coefficient |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 9,716 | 11,555 | 1 | -0.02633823 | 0.10029185 |
| 2 | 19,481 | 11,643 | 100 | -0.00005611 | 0.00146119 |
| 3 | 31,114 | 11,663 | 100 | -0.00004917 | 0.00137779 |
| 4 | 42,776 | 9,967 | 100 | -0.00006966 | 0.00117892 |

The first outer fold skips two initial inner episodes because the amended
protocol cannot produce an honest earlier-history cross-fitted anchor for those
dates. This is an explicit exclusion, not an imputed or relaxed fit.

## Integrity and reproducibility

All training gates passed:

- exactly three registered configurations and two registered correction inputs;
- four outer fits and 44,828 corresponding predictions;
- zero training-outcome overlap violations;
- no rows from the consumed July 2025–June 2026 holdout;
- authenticated source dataset, fold manifest, registration, fits, and row
  lineage; and
- no outer performance evaluation and no live-model change.

Two complete runs reproduced identical hashes:

- prediction file SHA-256: `1f60e8748c459fbfbccf4737ec1625f29ea80ed33436081e123cd8f816fa478d`;
- prediction logical SHA-256: `0c99cb653a9898f3b7e9e3105f60ed9af34d8fab57e5c7584d980325983fb3ac`;
- fit-manifest SHA-256: `2becbc41efa5614d0156cb80e24408838775cff4aa991e41c46263581082f44a`;
  and
- report SHA-256: `55a826cf5eb0703bc7549dd629c7d81aeacabbe797a22c4f71c574995efbdeb8`.

The canonical local run is stored under
`data/derived/phase_9d-residual-training/20260910-v1/`. Derived model artifacts
remain local and ignored by Git; the implementation, tests, protocol, and this
reproducibility record are versioned.

Reproduce the fit from the repository root after setting `PYTHONPATH`:

```powershell
$env:PYTHONPATH = (Resolve-Path 'services/research/src').Path
py -3.14 -m quantrade_research.phase_9d_residual_training `
  --output data/derived/phase_9d-residual-training/<new-run-id>
```

The trainer refuses to overwrite an existing run directory.

## Evidence boundary

P9D.3 answers only whether the frozen challenger can be fit reproducibly without
chronology violations or model expansion. P9D.4 is the first task allowed to
calculate outer ranking, portfolio, cost, turnover, stability, bootstrap, and
coverage evidence and issue `freeze_for_forward_shadow` or `no-freeze`.

The consumed holdout remains unopened. These Tier-B current-survivor results are
survivorship biased and use static present-day sectors. They cannot independently
confirm a model, justify deployment, or support a public performance claim.
