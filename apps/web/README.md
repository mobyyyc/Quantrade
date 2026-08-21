# Quantrade web

The web application is the presentation layer for dated, source-attributed
research outputs. It must not calculate research signals or directly reshape
provider responses; those responsibilities belong to the research service and
shared contracts.

## Getting started

From the repository root:

```bash
pnpm dev:web
```

Open [http://localhost:3000](http://localhost:3000) to view the local app.

The private-beta routes render from dated research outputs when a normalized
research database is connected. Without it, they state the unavailable reason
instead of showing invented market examples.

## Dated research APIs

P6.2 exposes Node.js route handlers that read only normalized research outputs:

- `GET /api/v1/scores?date=YYYY-MM-DD`
- `GET /api/v1/scores/:securityId?date=YYYY-MM-DD`
- `GET /api/v1/model-cards/:modelVersion`

They require `DATABASE_URL` and return a clear `503` when research data is not
configured. They never calculate scores or reshape provider responses.

## Product design rules

P6.3 defines the private-beta navigation and language before product screens
are built. `INFORMATION_ARCHITECTURE.md` assigns one job to each route, and
`UI_CONTENT_RULES.md` prevents trade language, dense screener controls, hidden
freshness, or unsupported performance claims.

## Private-beta research views

P6.4 implements the product routes described by the information architecture:

- `/` for the latest research run and a concise shortlist
- `/rankings?date=YYYY-MM-DD` for a dated list
- `/search?query=...` for ticker or company discovery
- `/stocks/:securityId?date=YYYY-MM-DD` for score evidence and limits
- `/research` for methodology and model context

When normalized research data is not connected, the app renders an explicit,
useful unavailable state rather than invented sample scores or price charts.

## Private-beta safeguards

The scored routes include a clear research-only context notice, keyboard skip
navigation, visible focus states, and a reduced-motion fallback. See
[`ACCESSIBILITY_REVIEW.md`](../../ACCESSIBILITY_REVIEW.md) and
[`UNCERTAINTY_AND_DISCLAIMER_REVIEW.md`](../../UNCERTAINTY_AND_DISCLAIMER_REVIEW.md)
for the implemented review and the checks required before an external beta.
