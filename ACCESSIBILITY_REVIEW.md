# Accessibility Review

## P15.3 audit, 2026-09-05

Completed a source, automated-browser, keyboard, and screenshot review of Today,
Rankings, Watchlist, Portfolio, Research, Search, and stock detail. This is not
a formal WCAG conformance claim. The audit uses the isolated `quantrade_e2e`
database, not production research data. No live daily update was triggered.

## Findings and corrections

- **Mobile navigation:** the previous ARIA modal allowed focus to leave the
  drawer and did not restore focus. A native modal dialog now makes background
  content inert, contains forward/reverse Tab navigation, closes with Escape,
  restores the opener, locks background scrolling, and closes at desktop width.
- **Rankings:** virtualized preview rows could leave the accessibility tree as
  users scrolled. The already-bounded top-20 preview now renders every row in
  normal document flow. All links remain keyboard reachable; scrolling and
  edge fades remain. Row focus outlines sit inside clipped scroll containers.
- **Contrast:** secondary `--subtle` text changed from `#6b7280` to neutral
  `#929292`. Its computed contrast is at least 5.47:1 on the four design-system
  surfaces (`#080808`, `#111111`, `#161616`, `#1c1c1c`). Existing red and green
  numeric text remains at least 4.52:1 and 7.47:1 respectively on those surfaces.
  Directional values retain signs/text, so color is not the only cue.
- **Charts:** retained the descriptive trend/value/period label and arrow-key
  inspection; added Home/End shortcuts and an expandable semantic table with
  every supplied observation, full ISO dates, USD prices, caption, column/row
  headers, and a keyboard-scrollable region. The copy explicitly says missing
  sessions are not filled; it does not imply that sparse history is complete.
- **Screen-reader structure:** corrected invalid definition-list markup in
  Portfolio facts, stock input counts, Research coverage, and forward-label
  readiness. Supporting descriptions now belong to their values.
- **Reflow:** long Research model identifiers now wrap instead of causing
  horizontal page scrolling at a 320px viewport.

Impeccable informed the focus, hierarchy, and contrast review. The owner's
neutral-black palette, movement-free controls, and no-skeleton rules take
precedence over generic skill defaults.

## Verification

- `corepack pnpm lint:web`: passed.
- `corepack pnpm build:web`: passed, including TypeScript.
- `corepack pnpm --filter @quantrade/web test:e2e`: **11 passed**.
- Axe WCAG A/AA checks (`wcag2a`, `wcag2aa`, `wcag21aa`, `wcag22aa`): no detected
  violations on all seven routes at 1280px, 390px, and 320px.
- Expanded chart table and open mobile dialog also pass full default Axe scans.
- Keyboard assertions cover skip-to-main, search shortcut, drawer containment
  in both directions, Escape/focus return, route selection, ranked links with
  visible focus, chart endpoints, and table expansion.
- Reduced-motion check confirms smooth scrolling is disabled.
- No document-level horizontal overflow on the audited route/viewport matrix.
- Inspected captured chart/table and mobile drawer screenshots. Screenshots
  and traces remain local test artifacts, not committed assets.

The Axe dependency is development-only. Existing functional tests still cover
search, dated scores, saved stocks/prices, mocked update progress, and official
portfolio history. Production data, model artifacts, and schedules are untouched.

## Remaining release validation

Automated scans do not establish screen-reader usability or cover every state.
Before external beta, manually test NVDA/Firefox and VoiceOver/Safari reading
order, live announcements, watchlist editing/removal, chart exploration, and
route changes. Also test real 200%/400% browser zoom, forced-colors mode, and
large production datasets, long notes, sparse histories, and all error/empty
states. Narrow viewport checks are not a substitute for browser zoom testing.
