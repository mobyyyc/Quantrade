# Product Information Architecture

## Product frame

Quantrade is a private, daily equity-research companion. Its job is to help the
owner decide which small number of names deserve further research after the
market close. It is not a brokerage, portfolio tracker, trading terminal, or
filter-heavy screener.

The defining use moment is the owner at a desk around 8:15 p.m., reviewing the
day's completed research in low ambient light. The product uses a warm dark,
restrained interface with one clear decision per screen.

## Primary navigation

| Destination | Route | Screen job | Primary question |
| --- | --- | --- | --- |
| Today | `/` | Summarize the latest research run and provide a calm entry point. | What deserves attention today? |
| Rankings | `/rankings` | Show a short, dated ranked list with provenance and eligibility. | Which eligible names should I inspect? |
| Search | `/search` | Find a known ticker or company without adding filtering complexity. | Where is the company I want to research? |
| Stock detail | `/stocks/[securityId]` | Explain one company's dated score, evidence, risk, and freshness. | Why is this name here, and what should I verify? |
| Research | `/research` | Explain the model, data capability, methodology, and known limits. | What does this score mean, and what can it not tell me? |

Search is a route and a persistent affordance. Watchlists and paper portfolios
remain Phase 7 additions, not navigation placeholders in V1.

## Screen hierarchy

### Today

1. A dated research-status line and data-capability label.
2. One `Quant View` anchor: the current research score or an explicit unavailable
   state, never a portfolio-value hero.
3. A short list of three to five research candidates, each with score, rank,
   freshness, and a plain-language reason to inspect.
4. One concise data or model note when the run is unavailable, stale, or Tier B.

### Rankings

1. Date and model context, always visible.
2. A simple ranked list, not a filter grid. Rows show company identity, research
   score, rank, signal label, and freshness.
3. A lightweight date control for available score dates.
4. An explicit empty state when no dated scores are published.

### Stock detail

1. Security identity, selected score date, research score, and plain-language
   status.
2. A price context chart with an accessible textual summary.
3. `Why it appears`: two or three largest factor contributions plus their
   direction and percentile context.
4. `What to verify`: risk, liquidity, freshness, Tier B, and unavailable-factor
   notes.
5. Progressive disclosure for methodology, source lineage, model card, and raw
   data dates.

### Research

1. What the score measures and does not measure.
2. Current model card and data-capability tier.
3. Feature families and explanation methodology.
4. Validation and execution assumptions.
5. Limitations, rejected methods, and source-attribution links.

## Responsive navigation

- Desktop uses a compact top bar with the five destinations and an always-visible
  search entry point.
- Mobile prioritizes Today, Rankings, Search, and Research in a thumb-friendly
  bottom navigation. Stock detail is entered from a row and returns to its
  originating context.
- A visible text label and current-location treatment accompany every icon.
- Desktop and mobile preserve the same information order. Mobile removes
  secondary detail before it changes the user's decision path.

## Data-state hierarchy

Every data-bearing view must represent one of four states before rendering
content:

1. `Published`: dated score and provenance are present.
2. `Unavailable`: no score was published, with a specific reason.
3. `Stale`: the latest score date is older than the expected market session.
4. `Loading`: skeleton structure mirrors the final content order.

No screen uses a fabricated zero, placeholder rank, or generic success message
in place of a missing research result.
