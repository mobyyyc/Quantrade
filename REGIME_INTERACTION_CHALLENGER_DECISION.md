# Regime-Interaction Challenger Decision

## Decision

Reject `active_linear_spy_regime_interactions_v1`. The challenger failed five
pre-registered development gates and is not eligible for an inference artifact,
model card, shadow registration, approval, or deployment.

The active private-beta elastic-net model remains unchanged.

## Decision record

- Decision key: `regime_interaction_challenger_rejection_v1`
- Decision date: 2026-08-27
- Scope: Tier-B private research
- Result: rejected; no freeze
- Passing candidates: 0 of 1
- Selected challenger: none
- Holdout used: no
- Model artifact created: no
- Shadow scoring started: no
- Deployment changed: no
- User-visible rankings changed: no

## Failed gates

1. Overall mean daily rank IC declined from 0.0331 to 0.0273 instead of
   improving by at least 0.005.
2. Post-20-basis-point benchmark-relative return declined from 12.02% to
   6.39%.
3. Positive-month share declined from 68.42% to 63.16%, below its frozen
   non-inferiority floor.
4. Range-bound mean daily rank IC was -0.0051, below the required 0.005.
5. Range-bound rank IC declined by 0.0057 instead of improving by at least
   0.005.

The challenger passed point-in-time integrity, data quality, common-sample,
coverage, spread, fold-stability, positive-IC-share, rank-stability, turnover,
MAE, and RMSE gates. Passing those gates cannot compensate for a failed gate.

## Evidence

- Pre-registration: `REGIME_INTERACTION_CHALLENGER_PROTOCOL.md`
- Feature audit: `REGIME_INTERACTION_FEATURE_AUDIT.md`
- Comparison: `REGIME_INTERACTION_CHALLENGER_COMPARISON.md`
- Materialized dataset SHA-256:
  `55f62409712122b00fc219c182f99924ab92ffb75ac7b475c15a7cd2df7d1957`
- Combined feature-registry SHA-256:
  `fbba8491fc59568e180e29d9d416dfe0e29e5d85c019234cc8765439c6cfdfcb`
- SPY lineage SHA-256:
  `c7950851aa3c9eeab93a6e2800c82ea12abd52961d6bfb934cf674608bd68444`
- Repeated comparison JSON SHA-256:
  `f11cc3ba657b6f26c3bde83e2f91609d9da0b58872581cb3d390f76f5ede49d1`
- Deterministic comparison result SHA-256:
  `be64f219ee391eeab16a097def8b903f52897a64ff3446e182640a469f58a040`

Two independent comparisons produced byte-identical outputs. The July 2025
through June 2026 holdout was not used to fit, select, tune, or rescue the
challenger.

## Governance consequence

Phase 9A closes with no challenger frozen, so Phase 10 does not start. The
failed interaction specification and thresholds may not be changed after the
result to rescue this version.

Any future challenger requires a new evidence-led hypothesis, a new versioned
pre-registration, and a development-only comparison. It may not use this
rejected result as authorization to tune against the consumed holdout.
