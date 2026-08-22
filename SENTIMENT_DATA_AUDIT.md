# Sentiment-Data Audit

## Scope

Date: 2026-08-21

This audit evaluates only whether a free external sentiment source can be added
as an isolated, point-in-time research input. It does not evaluate sentiment
alpha and does not authorize a scoring feature.

## Result

No source is approved. Sentiment remains outside the model and must not be
shown as a signal, score driver, or performance explanation.

| Candidate | Finding | Decision |
| --- | --- | --- |
| Stocktwits developer API | The developer site says it is reviewing its APIs, terms, and documentation and is not accepting new registrations. | Reject for now: no reproducible access path. |
| Reddit Data API | Access and terms are evolving, with registration, permission, and use restrictions. Commercial or high-volume research may require a separate agreement. | Reject for now: access and retention are not stable enough for a reproducible research panel. |

## Gate for reconsideration

Re-open this audit only when a source provides all of the following:

1. Documented authorization and stable access terms.
2. A ticker-to-content mapping with source timestamps available at decision time.
3. Explicit retention, attribution, and privacy handling.
4. A frozen sample, missingness report, and holdout-only evaluation plan.
5. Evidence that the feature improves the approved baseline after costs without
   weakening point-in-time controls.

## Sources

- Stocktwits, [developer status](https://api.stocktwits.com/developers).
- Reddit, [Data API Terms](https://redditinc.com/policies/data-api-terms) and [developer API documentation](https://www.reddit.com/dev/api/).
