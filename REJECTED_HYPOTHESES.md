# Rejected Hypotheses and Methods

These are immutable governance decisions, not claims about live or historical
performance. Each entry records why an idea is outside the V1 research scope.

| Key | Statement | Rejection reason | Evidence |
| --- | --- | --- | --- |
| `same_close_execution` | A close-derived score can be executed at that same closing price. | Rejected: it introduces look-ahead execution. The protocol requires the next eligible regular-session open. | `EXPERIMENT_PROTOCOL.md` |
| `unregularized_model_candidate` | An unregularized linear model can be promoted as a V1 candidate. | Rejected: P5.4 permits only ridge or elastic-net comparisons, and only after the baseline passes approval. | `MODEL_APPROVAL_POLICY.md` |
