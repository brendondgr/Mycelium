# Mobile Friendly Skill

Use this skill when designing or implementing Mycelium pages that must work on
phones, tablets, and small laptop screens.

## Core Rules

- Start with mobile-first layouts and progressively enhance for desktop.
- Include the viewport meta tag on every page.
- Use responsive grids, `fr`, percentages, and `clamp()` where appropriate.
- Prevent horizontal scrolling at 320px and common mobile widths.
- Keep body text at least 16px with readable line height.
- Make interactive targets at least 44x44px where practical.
- Avoid hover-only interactions.
- Ensure images, feed cards, and long report bodies resize without layout shift.

## Mycelium-Specific Checks

- **App shell:** the sidebar collapses into `portal-mobile-nav.tsx` without
  hiding core routes, and the lab/personal switcher stays reachable.
- **Feed pages:** every feed is a one-card-per-row list. The `MatchRing` sits in a
  top-left notch occupying one grid row; the card body spans both columns
  beneath. Verify the ring's caption wraps to the ring's own width rather than
  widening the gutter.
- **Filter rails:** the sticky left rail must not trap scroll or overlay the
  results column on small screens; collapsible facets start closed.
- **Editor modals:** `EditorModal`'s left tab rail becomes a horizontal scroller
  under `sm`. Every panel stays mounted (inactive ones `hidden`) so switching
  tabs never loses in-progress edits.
- **Infinite reveal:** the `sr-only` "Load more" button in `FeedSentinel` is the
  keyboard and small-screen path. Do not remove it.
- **Report bodies:** long-form markdown must preserve readable line length.
- **Job states:** a running scan or a queued report must stay visible without a
  desktop-only side panel.

## Performance Expectations

- Keep the public site fast and SEO-friendly — it ships no framework JavaScript,
  so keep it that way.
- Feeds are fetched whole and revealed progressively on the client. Do not swap
  that for a paged fetch without checking `useInfiniteReveal`'s callers.
- Use skeletons or meaningful loading states instead of blank panels.

## Output Expectations

- Call out any element that risks overflow, clipped content, tiny tap areas, or
  unreadable text.
- Specify mobile behavior for navigation, feeds, filter rails, modals, and
  reports.
- Pair this skill with `ui-frontend` for visual decisions and with
  `ada-compliance` for accessibility-sensitive workflows.
