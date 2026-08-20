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

The current page is only a foundation status screen. Product routes and data
views arrive after the data and research pipeline are established.
