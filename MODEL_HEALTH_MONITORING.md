# Model Health Monitoring

Quantrade records an immutable health snapshot after each completed score publication and its same-date forward-outcome readiness snapshot. The monitor is diagnostic only. It cannot train, select, promote, or deploy a model, and it never changes published scores.

## Recorded evidence

Each snapshot binds the score date, decision time, model and protocol versions, cohort size, eligibility coverage, grouped exclusions, rank stability, active-feature health, forward-outcome readiness, and integrity checks to a deterministic SHA-256 hash.

Active-feature drift uses Population Stability Index (PSI) against observations from the previous 20 canonical completed score dates produced by the same model. At least 100 current and 100 reference observations are required; otherwise drift is explicitly marked as having insufficient reference data. Rank stability compares the current publication with the previous canonical completed publication from the same model.

The integrity checks verify:

- deployed artifact bytes against the registered artifact hash;
- agreement between the artifact, model card, and canonical feature-registry hash;
- every published score explanation against the active immutable input contract;
- existence of the same-date forward-outcome readiness snapshot.

## Warning thresholds

| Signal | Warning | Critical |
| --- | ---: | ---: |
| Eligible coverage | below 98% | below 90% |
| Active-feature missingness | above 2% | above 10% |
| Active-feature PSI | above 0.10 | above 0.25 |
| Top-20 churn | above 50% | none; diagnostic warning only |
| Mean normalized rank movement | above 15% | none; diagnostic warning only |

Threshold comparisons are strict: a value exactly equal to a boundary does not alert. Missing same-date forward readiness is a warning. Any artifact, registry, or explanation-lineage mismatch is critical.

## Reproduction and idempotency

Run the monitor for the latest completed publication:

```powershell
py -3.14 -m quantrade_research.model_health --env-file .env
```

Or reproduce a specific date:

```powershell
py -3.14 -m quantrade_research.model_health --env-file .env --score-date 2026-09-11
```

The first valid run creates the snapshot. Repeating it must print `already_verified`. If the same date recomputes to a different logical hash, the monitor fails rather than overwriting history. All health tables reject updates and deletes at the database layer.

The authenticated web endpoint is `GET /api/v1/model-health`. The Research page presents the latest status, integrity lineage, warnings, and progressively disclosed feature metrics. No automated action is attached to any status.
