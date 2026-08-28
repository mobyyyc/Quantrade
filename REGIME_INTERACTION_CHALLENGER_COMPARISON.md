# Regime-Interaction Challenger Comparison

## Result

The single pre-registered challenger failed 5 frozen gate(s). This is a development-only
comparison. The locked holdout was not used and the active model was not changed.

## Common-sample metrics

| Measure | Active elastic-net | Regime challenger |
| --- | ---: | ---: |
| Mean daily rank IC | 0.0331 | 0.0273 |
| Range-bound rank IC | 0.0005 | -0.0051 |
| Top-minus-bottom spread | 1.01% | 1.06% |
| Return after 20 bps | 12.02% | 6.39% |
| Positive months | 68.42% | 63.16% |
| Rank stability | 0.9903 | 0.9837 |
| Monthly turnover | 33.33% | 42.78% |
| MAE | 5.71% | 5.71% |
| RMSE | 7.80% | 7.80% |

## Gate result

- Failed `rank_ic_improvement`: delta=-0.005723740834958433; minimum=0.005
- Failed `cost_robustness`: challenger=0.06388421472930772; active=0.12015793044592349
- Failed `positive_month_share`: challenger=0.631578947368421; minimum=0.6342105263157895
- Failed `range_bound_rank_ic_absolute`: challenger=-0.005129202184969026; minimum=0.005
- Failed `range_bound_rank_ic_improvement`: delta=-0.0056738253749897153; minimum=0.005

## Provenance

- Dataset SHA-256: `55f62409712122b00fc219c182f99924ab92ffb75ac7b475c15a7cd2df7d1957`
- Combined feature-registry SHA-256: `fbba8491fc59568e180e29d9d416dfe0e29e5d85c019234cc8765439c6cfdfcb`
- SPY lineage SHA-256: `c7950851aa3c9eeab93a6e2800c82ea12abd52961d6bfb934cf674608bd68444`
- Result SHA-256: `be64f219ee391eeab16a097def8b903f52897a64ff3446e182640a469f58a040`

## Reproducibility

Two independent comparisons produced byte-identical JSON and Markdown before
this verification note was appended. Their file SHA-256 values were
`f11cc3ba657b6f26c3bde83e2f91609d9da0b58872581cb3d390f76f5ede49d1`
and `710ebfe587b6968b2f59f90feeb2923ca2bf7c317e6cd104acdeff5c1ddcc9ab`.

P9A.5 formally rejected the challenger in
`REGIME_INTERACTION_CHALLENGER_DECISION.md`. No artifact was frozen and the
live model and user-visible rankings remain unchanged.
