# Model Card: `baseline_equal_weight_v1`

## Status

**Research-only comparator. Not active.** This baseline was evaluated once in
the shared locked-holdout comparison. It underperformed SPY after the required
20-bps sensitivity and is not approved for private-beta deployment, public
performance claims, or investment use.

## Purpose

Provide a transparent reference model for ranking eligible US equities in the
private beta. It is a research diagnostic, not investment advice, a probability,
or a return forecast.

## Methodology

- Uses point-in-time, sector-aware percentiles for declared momentum, value,
  profitability, risk, and liquidity features.
- Averages every required available feature rank equally; a missing required rank
  makes a security ineligible.
- Forms scores after the regular-session close and evaluates execution at the
  next eligible regular-session open.
- Uses `EXPERIMENT_PROTOCOL.md` version `0.1` and the active feature registry.

## Data capability and limitations

- Current capability: **Tier B**. Historical constituent and delisting coverage
  have not been verified, so no unbiased historical-performance claim is valid.
- Free-provider market data and SEC facts must pass their point-in-time quality
  checks; a failed check blocks the score rather than being repaired silently.
- The model has no learned weights. Ridge and elastic-net candidates may only be
  compared after this baseline passes the private-beta approval gates.
- The final holdout, 2025-07-01 through 2026-06-30, is consumed. Its result may
  be reported but cannot be used to tune or retry this baseline.
