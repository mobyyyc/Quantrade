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
| Rankings | `/rankings` | Show the dated ranked universe and compact provenance. | Which eligible names should I inspect? |
| Watchlist | `/watchlist` | Revisit personally saved companies and their latest research context. | Which names do I want to follow up on? |
| Search | `/search` | Find a known ticker or company without adding filtering complexity. | Where is the company I want to research? |
| Stock detail | `/stocks/[securityId]` | Explain one company's dated score, evidence, risk, and freshness. | Why is this name here, and what should I verify? |
| Research | `/research` | Explain the model, data capability, methodology, known limits, and paper track record. | What does this score mean, and what can it not tell me? |

Search is a route and a persistent affordance, rather than a destination in the
primary navigation. The paper portfolio is model track-record context within
Research, rather than a competing top-level destination.

## Screen hierarchy

### Today

1. A dated research-status line and data-capability label.
2. One `Quant View` anchor for the lead research candidate, or an explicit
   unavailable state.
3. A short list of three to five research candidates, each with score, rank,
   and a plain-language reason to inspect.
4. A compact preview of saved names when a watchlist exists.
5. A low-priority private update control after the research content.

### Rankings

1. Date and model context, always visible.
2. A simple ranked list, not a filter grid. Rows show company identity, research
   score, rank, and signal label.
3. A lightweight date control for available score dates.
4. An explicit empty state when no dated scores are published.

### Watchlist

1. Saved company identity, with ticker prominent and company name secondary.
2. Latest eligible research score and rank, or a plain unavailable status.
3. One contextual overflow menu for removal, with an Undo path.
4. An empty state that directs the user to global search and the stock-detail
   save action. The watchlist does not duplicate company search.

### Stock detail

1. Security identity, selected score date, research score, and plain-language
   status, plus a compact Save to watchlist action.
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

- Desktop uses a compact top bar with Today, Rankings, Watchlist, Research, and
  an always-visible search entry point.
- Mobile uses a left-side navigation drawer for the same four destinations, so
  future navigation can grow without compressing a bottom bar. Stock detail is
  entered from a row and returns to its originating context.
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
