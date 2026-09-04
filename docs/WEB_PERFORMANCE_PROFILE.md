# Web performance profile

This profile records the P15.2 production-rendering baseline and the changes
that were justified by measurement. It is not a synthetic benchmark or a
promise about hosted latency.

## Method

- Next.js 16.3.1 production build served locally with `next start`.
- Local PostgreSQL research database containing 500 score rows in the latest
  publication and 500 in the previous publication.
- Ten sequential requests per route; TTFB measured with `curl` after server
  startup. HTML/React Server Component response size was measured as UTF-8.
- The main dated-score query was checked with `EXPLAIN (ANALYZE, BUFFERS)`.

## Findings

The database was not the bottleneck. The 500-row dated-score query completed in
4.89 ms, and its latest-run, deployment, security, listing, and prediction joins
used existing indexes. Adding another index or a database-result cache was not
justified for the current data volume.

The expensive pages were crossing oversized `DatedScore` objects into Client
Components. That duplicated fields which the browser never used:

| Route | Before | After | Reduction | Final median TTFB |
| --- | ---: | ---: | ---: | ---: |
| Today | 431,692 B | 30,210 B | 93.0% | 313 ms |
| Rankings | 784,842 B | 329,646 B | 58.0% | 85 ms |
| Portfolio | 14,267 B | 14,267 B | — | 4 ms |
| Research | 34,111 B | 34,111 B | — | 174 ms |
| Stock detail | 50,182 B | 50,182 B | — | 18 ms |

Local Today TTFB remained CPU-bound and variable despite the large transfer
reduction, so no unsupported TTFB claim is made. Its network and hydration cost
is materially lower.

## Changes

- Client ranking components now receive compact score projections containing
  only fields they render.
- The Today ranking is explicitly a top-20 preview; the complete publication
  remains available on Rankings.
- The mini watchlist requests only its saved companies' scores after hydration,
  in parallel with their prices. The score API accepts at most 50 unique,
  validated security IDs.
- No time-based cache was added. Daily publications are mutable operational
  state until completion, and cache invalidation is not yet required to reach
  the measured local target.

Re-run the production build and profile after materially increasing the score
universe, adding authenticated users, or moving PostgreSQL off-host.
