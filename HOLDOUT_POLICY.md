# Final Holdout Policy

## Locked period

The final holdout for `EXPERIMENT_PROTOCOL.md` version `0.1` is **2025-07-01
through 2026-06-30**, inclusive. It is a completed, recent twelve-month period
that remains unavailable for model selection, feature changes, or parameter
tuning.

The holdout is evaluated once after the baseline and any permitted comparison
are finalized through earlier chronological walk-forward validation. Any change
to these dates requires a new protocol version and a dated governance record;
the existing lock is never overwritten.

## Experiment log

Every pre-holdout experiment records its code/model and protocol versions,
feature-registry hash, training and validation end dates, timestamp, and an
immutable result URI. An experiment whose validation reaches 2025-07-01 or
later is rejected from the selection log.
