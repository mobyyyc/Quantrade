# Real-state UX matrix

Status: passed on 2026-09-14 for roadmap task Q2.3.

## Scope

The browser checks use the isolated `quantrade_e2e` PostgreSQL database and the same server-rendered pages and read-model queries as the private application. Provider failure is intercepted at the HTTP boundary so the UI can be tested deterministically without contacting an external service.

| State | Representative surface | Evidence checked |
| --- | --- | --- |
| Empty | Search and Watchlist | No-result and no-saved-company states remain useful at 320 px, pass Axe WCAG 2.2 AA rules, and do not overflow. |
| Partial | Rankings and stock detail | A real withheld score is counted in coverage, excluded from ranking, and explained on its company page without estimating missing data. |
| Stale | Today and Research | A newer stored market session leaves the last publication visible and clearly reports that new market data awaits scores. |
| Failed | Today daily update | A failed update is announced as an assertive alert, leaves the button retryable, and never presents completion. |
| Month-end | Portfolio | The real 20-position fixture, completed outcome, and missed formation render at 390 px; mobile labels distinguish returns from operational status. |
| Long list | Watchlist and Portfolio | Twenty saved companies and twenty holdings remain scrollable or readable, keyboard reachable, and free of horizontal overflow. Missing prices settle as unavailable instead of remaining in a loading state. |

All core routes (`/`, `/rankings`, `/portfolio`, `/watchlist`, `/research`, `/search`, and stock detail) are also checked at 1280, 390, and 320 px. The suite covers keyboard navigation, the mobile focus trap, reduced motion, chart keyboard control and table fallback, named scroll regions, and automated WCAG 2.2 AA rules.

## Fixes made from measured failures

- Removed a narrow-screen overflow caused by long model-version identifiers on withheld-score details.
- Replaced incorrect mobile portfolio labels for pending, withheld, and missed formations with row-specific labels.
- Made failed daily-update messages assertive alerts while preserving retry access.
- Added named region semantics to the full and mini watchlist scroll areas.
- Settled missing prices to `Price unavailable` after a successful partial response instead of showing an indefinite loading label.
- Raised recurring navigation, search, account, date, segmented, menu, editor, and undo controls to the 44 px interaction target.
- Corrected singular withheld-company copy.

## Post-fix audit score

| Category | Score | Basis |
| --- | ---: | --- |
| Accessibility | 4/4 | Axe WCAG 2.2 AA checks pass; keyboard, focus, reduced-motion, chart alternative, alerts, and scroll regions are covered. |
| Responsive behavior | 4/4 | All core routes pass at 1280, 390, and 320 px without horizontal overflow; long and operational states receive additional mobile checks. |
| State clarity | 4/4 | Empty, partial, stale, failed, month-end, and long-list states are explicit and do not fabricate data. |
| Design-system consistency | 4/4 | Fixes retain the established neutral palette, typography, geometry, focus, and no-jiggle interaction rules. |

## Verification commands

```powershell
pnpm --filter @quantrade/web lint
pnpm --filter @quantrade/web build
pnpm --filter @quantrade/web test:e2e
```

Result: 21 browser tests passed, including five dedicated real-state matrix tests.
