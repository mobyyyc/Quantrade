# Forward model evidence reporting

Quantrade's daily workflow already preserves immutable live scores, completed
forward labels, official monthly portfolio outcomes, and model-health snapshots.
The forward-evidence report turns those records into one read-only monitoring
artifact. It never trains, selects, promotes, or changes a model.

Run the cumulative post-deployment report with:

```powershell
.\scripts\run-forward-evidence-report.ps1
```

Optional bounds must remain on or after the active model's deployment date:

```powershell
.\scripts\run-forward-evidence-report.ps1 -PeriodStart 2026-09-01 -AsOfDate 2026-09-30
```

Each run creates a new immutable directory under
`data/derived/forward-evidence/` containing:

- `evidence.json`: deterministic machine-readable evidence and logical hash;
- `summary.md`: coverage, drift, rank stability, forward-label readiness, and
  official basket-versus-SPY results; and
- `manifest.json`: completion status plus file SHA-256 hashes.

The active deployment timestamp is the earliest allowed boundary. Historical
replay and the consumed holdout are excluded. Forward-label counts include only
eligible snapshots from canonical completed live runs of the active model.
Pending labels are displayed as pending, never as zero returns.

Basket evidence is stricter: only portfolios already formed under
`monthly_last_session_next_open_v1` are included. The report does not construct
a top-20 basket retrospectively. Until an official month-end formation and its
future window complete, basket-versus-SPY is explicitly unavailable.

The report is appropriate for periodic monitoring and a later Q5 model-readiness
checkpoint. It is not permission to retune against the same observations.
