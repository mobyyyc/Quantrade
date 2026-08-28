# Rejected Hypotheses and Methods

These are immutable governance decisions, not claims about live or historical
performance. Each entry records why an idea is outside the V1 research scope.

| Key | Statement | Rejection reason | Evidence |
| --- | --- | --- | --- |
| `same_close_execution` | A close-derived score can be executed at that same closing price. | Rejected: it introduces look-ahead execution. The protocol requires the next eligible regular-session open. | `EXPERIMENT_PROTOCOL.md` |
| `unregularized_model_candidate` | An unregularized linear model can be promoted as a V1 candidate. | Rejected: P5.4 permits only ridge or elastic-net comparisons, and only after the baseline passes approval. | `MODEL_APPROVAL_POLICY.md` |
| `ungated_external_sentiment` | Public social sentiment can be added as a research input without a separate access, timestamp, and holdout gate. | Rejected: current free candidates do not provide a stable, reproducible approved ingestion path. | `SENTIMENT_DATA_AUDIT.md` |
| `amihud_illiquidity_20d_v1` | The 20-day Amihud candidate adds sufficiently distinct information to the active feature set. | Rejected: its 0.9135 median absolute monthly correlation with active median dollar volume exceeds the frozen 0.90 redundancy ceiling. | `NEXT_GENERATION_FEATURE_DIAGNOSTICS.md` |
| `short_term_reversal_20d_v1` | The 20-day reversal candidate is stable enough for the next model comparison. | Rejected: median consecutive rank correlation was 0.0370 and median top-20 turnover was 0.95, failing both frozen stability gates. | `NEXT_GENERATION_FEATURE_DIAGNOSTICS.md` |
| `robust_huber_grid_v1` | Robust Huber regression with the accepted next-generation features improves the active model under the frozen gates. | Rejected: all four variants had lower mean daily rank IC than the active reference and missed the positive-month gate. | `NEXT_GENERATION_MODEL_COMPARISON.md` |
| `gradient_boosted_stumps_grid_v1` | Deterministic boosted stumps improve ranking quality without sacrificing stability or cost robustness. | Rejected: both variants had lower rank IC; they also failed fold-stability and/or cost and spread gates. | `NEXT_GENERATION_MODEL_COMPARISON.md` |
| `pairwise_ranker_grid_v1` | A pairwise ranking objective improves the ordered stock cross-section. | Rejected: both variants produced slightly negative mean daily rank IC and failed ranking, spread, stability, cost, and positive-month gates. | `NEXT_GENERATION_MODEL_COMPARISON.md` |
| `active_linear_spy_regime_interactions_v1` | Interacting the active momentum and relative-strength features with a point-in-time 60-session SPY trend improves ranking, especially in range-bound markets. | Rejected: overall and range-bound rank IC declined, post-cost relative return weakened, and five pre-registered gates failed. | `REGIME_INTERACTION_CHALLENGER_COMPARISON.md` |
