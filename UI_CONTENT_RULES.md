# UI Content Rules

## Language and claims

- Call the output a **research score**, never a buy, sell, trade, prediction, or
  expected return.
- Use `Research candidate` for a high-ranked eligible name and `Unavailable` for
  a name that lacks a publishable score.
- Pair every signal label with plain text. Color may reinforce a state but never
  carry its meaning alone.
- State the date first: `Research score for Aug 20, 2026`, not `Today` when the
  record may be stale.
- Never imply that a rank is an instruction, a probability, or a guarantee.

## Score and ranking content

- Display the score on a 0–100 scale only with its model and score date nearby.
- Show rank as `Rank 12 of 438 eligible names`, never rank without its universe
  context.
- Treat `neutral` as an uncalibrated presentation state. Do not market it as a
  positive or negative investment opinion.
- Show an unavailable reason in user language, for example `Not published:
  missing required price history`.
- Keep one primary numerical anchor per screen. Supporting values explain it;
  they do not compete with it.

## Evidence and uncertainty

- Pair each factor contribution with the factor name, direction, sector
  percentile, and one concise explanation.
- Place freshness, data-capability tier, and model version in the visible context
  area, not only behind an information icon.
- Use `Tier B research data` with a direct explanation that historical universe
  and delisting coverage are not verified.
- Put model limitations beside the score or research conclusion when they change
  its interpretation.
- Charts require a text alternative describing period, trend, latest value, and
  important gaps or unavailable data.

## Controls and empty states

- Prefer search, a date selector, and progressive disclosure. Do not introduce
  multi-column filters, sortable indicator matrices, or advanced-screening
  controls in V1.
- Every unavailable or empty state explains what is missing, why it matters, and
  the next safe action, such as selecting another score date or returning to
  Rankings.
- Use one clear primary action per local context. Research actions use verbs such
  as `View evidence`, `Open research`, and `Read methodology`.
- Use consistent labels across views: `Research score`, `Why it appears`,
  `What to verify`, `Data freshness`, and `Methodology`.
- Keep company search global. Watchlist does not duplicate a second search field;
  users save a company from its stock detail.
- Use a contextual overflow menu for destructive watchlist actions. Removal must
  offer a visible Undo path and cannot be the dominant row action.
- Watchlist rows may show the latest regular-session close and one-session
  dollar/percentage change when the normalized market-data record is available.
  If it is unavailable, state that plainly rather than inferring an intraday price.
- Do not repeat the complete research disclaimer on every page. Put dated score
  context next to the score, and retain the full limitations discussion on
  Research.

## Accessibility and presentation

- Meet WCAG 2.2 AA contrast and keyboard navigation requirements.
- Maintain visible focus indicators and at least 44 by 44 CSS-pixel touch
  targets for primary mobile controls.
- Respect reduced motion. Motion may confirm a state change but cannot conceal
  content or delay a decision.
- Format dates, percentages, and large values for the user's locale while keeping
  source timestamps inspectable in the research context.
