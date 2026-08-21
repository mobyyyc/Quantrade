# Accessibility Review

## Scope

This review covers the P6 private-beta research routes. It is a code and
interaction review, not a claim of formal WCAG conformance.

## Implemented safeguards

- Every page has a keyboard-visible skip link that moves directly to the main
  research content.
- Links, controls, and the current route expose visible focus indicators.
- Desktop and mobile navigation use semantic `nav` landmarks and identify the
  current page with `aria-current`.
- The date picker and search controls have programmatic labels.
- Research lists use ordered-list semantics; the detail link gives assistive
  technology a meaningful destination.
- The mobile navigation controls are at least 44 CSS pixels high.
- Research status, rank, and eligibility use visible text, not color alone.
- Motion is limited to short control feedback and is reduced for users who set
  an operating-system reduced-motion preference.
- The unavailable chart state is written text rather than an inaccessible,
  decorative stand-in.

## Release checks still required

- Perform keyboard and screen-reader checks with connected research data.
- Test browser zoom and small mobile viewports with real long issuer names.
- Before publishing a price chart, add a text alternative with its period,
  trend, latest value, and material gaps.
