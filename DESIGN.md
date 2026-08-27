---
name: Quantrade
description: A calm, evidence-led quantitative equity research companion.
---

# Design System: Quantrade

## Overview

**Creative North Star: "The Quiet Research Desk"**

Quantrade is a dark, calm product surface for making one better research decision at a time. It borrows the spacious, chart-first clarity of the supplied Wealthsimple references while serving a different purpose: quantified evidence and risk, not brokerage action. The interface opens with the few signals that matter now, then progressively reveals factor detail, methodology, and backtest context.

The system rejects complicated stock screeners, generic trading terminals, crypto-dashboard spectacle, and literal Wealthsimple imitation. Desktop and mobile use the same content priority: large essential numbers, plain-language context, familiar controls, and carefully contained detail.

**Key Characteristics:**

- Near-black neutral restraint, not generic navy-and-gold finance styling.
- One clear decision or insight per viewport.
- Chart-led exploration with compact, touch-friendly time ranges.
- Evidence and uncertainty shown together.
- Fast, quiet feedback rather than decorative motion.

## Colors

The palette is nearly monochrome: an `#080808` canvas, neutral charcoal surfaces, quiet gray labels, and crisp white text create the working field. Green and red are reserved for actual positive and negative market movement; they are never decorative UI accents. Primary actions are white pills with black text. Surface separation uses `#111111`, `#161616`, and `#1C1C1C` with soft neutral borders, never blue or purple tints.

**The Evidence-First Color Rule.** Color is never decoration or the sole carrier of meaning. Positive, negative, selected, warning, and neutral states always include text, symbols, or position as a second cue.

**The Directional Color Rule.** Green and red are rare and earned. They mark
real positive or negative market movement only. Primary actions, navigation,
headings, labels, and generic UI state use neutral tones.

## Typography

**Display Font:** Inter, then the operating-system sans-serif stack
**Body Font:** Inter, then the operating-system sans-serif stack
**Label/Mono Font:** Tabular numerals are enabled globally; the system mono
stack is available where a code-like treatment is genuinely useful.

**Character:** Large figures are calm anchors, not promotional hero metrics. Labels, supporting statistics, and explanation text remain practical, high-contrast, and easy to scan.

### Hierarchy

- **Display:** Large price, score, or market-context figure. It appears once per screen and is always accompanied by an explicit label or context.
- **Headline:** The current research question or section purpose.
- **Title:** Stock identity, grouped insight, and section-level navigation.
- **Body:** Plain-language explanation with a comfortable reading measure.
- **Label:** Compact descriptions for data, controls, timestamps, and risk states.

**The One Anchor Rule.** One numerical value may dominate a screen. Every other value must support the decision rather than compete with it.

## Elevation

Depth comes from tonal layering, crisp borders, and spatial separation, not
glass surfaces. Elevation appears only where it clarifies an interactive
control or a bounded modular surface.

**The Calm Layer Rule.** If a panel needs a heavy shadow, blur, or glow to be
recognizable, its hierarchy is wrong.

- **Primary white pill:** `0 4px 14px rgb(255 255 255 / .12)` plus a deep
  occlusion shadow. Hover increases the aura only; it never moves the control.
- **Dark pill:** an inset one-pixel white highlight and a restrained black
  occlusion shadow. Selected navigation adds a subtle perimeter border.
- **Surface panel:** `0 10px 30px -10px rgb(0 0 0 / .8)` with a faint inset
  white highlight. This applies to grouped rows, forms, empty states, and
  modular detail panels.

## Components

The component vocabulary is intentionally small: primary and quiet buttons,
search, score/risk status labels, grouped data rows, and
progressive-disclosure sections.

### Buttons

- **Shape:** Interactive controls use full-pill geometry, generous touch targets, and familiar text or icon labels. Major panels use 16 to 24 pixel radii.
- **Primary:** Reserved for one clear action in a local context.
- **Hover / Focus:** Hover may change color, border luminance, or shadow only.
  It never translates, scales, or changes text geometry. Keyboard focus uses a
  two-pixel translucent white outline with a three-pixel offset.
- **Pressed:** Pressed controls reduce only their shadow. They never scale,
  preventing text or layout jitter while a pointer button is held.
- **Cursor:** Links and buttons always use the pointer cursor. Text fields
  retain the native text cursor.
- **Secondary / Ghost:** Used for navigation, time ranges, and reversible secondary actions.

### Cards / Containers

- **Corner Style:** Gently rounded and purposeful, never nested card grids.
- **Background:** Tonal separation from the canvas, with borders carrying most of the structure.
- **Internal Padding:** Spacious around a single insight; compact only for comparable rows.

### Navigation

- Standard, predictable routes for Today, Rankings, Watchlist, and Research.
  Search is a persistent affordance, not a primary destination.
- Mobile navigation uses a left-side drawer, preserving enough room for future
  destinations without compressing a bottom bar. Desktop navigation favors
  directness.
- Current location is visible through more than color alone: white text,
  a neutral selected surface, and a subtle perimeter border.
- Unselected navigation items are plain text controls without pill frames;
  the pill treatment is reserved for the selected route.

### Signature Component

**Quant View:** A compact, dated summary that pairs score, signal, risk, data freshness, and two or three real factor contributors. It must always link to its methodology and must never resemble a trade recommendation button.

### Rankings and Model Portfolio

- Daily rankings are changing research context. They may identify candidates, but they never imply that the official portfolio rebalanced that day.
- The model portfolio is a separate monthly object: the top 20 eligible active-model names from the final market session of a completed calendar month, equally weighted and recorded at the next regular-session open.
- Portfolio copy must show both the formation date and execution date, and state that holdings remain fixed until the next scheduled monthly formation.
- Never derive the visible model portfolio from whichever daily ranking happens to be on screen.

## Do's and Don'ts

### Do:

- **Do** put the user’s current research decision before secondary market data.
- **Do** use a chart, a dated score, and plain-language drivers together on a stock page.
- **Do** reveal methodology and backtest detail progressively, not by hiding it.
- **Do** provide visible focus states, keyboard paths, reduced motion, text labels, and chart summaries that meet the accessibility baseline in `PRODUCT.md`.
- **Do** adapt the supplied Wealthsimple references into an original Quantrade system.

### Don't:

- **Don't** build a complicated screener with dense filter panels, endless columns, and indicator overload.
- **Don't** use generic trading-terminal or crypto-dashboard styling, including neon spectacle on a dark canvas.
- **Don't** copy Wealthsimple brand assets, copy, or proprietary interface details.
- **Don't** use glassmorphism as a default, gradient text, colored side-stripe cards, or duplicated hero-metric cards.
- **Don't** use green and red as the only signals for gain, loss, risk, selection, or validation state.
