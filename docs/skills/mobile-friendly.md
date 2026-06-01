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
- Ensure images, videos, graph canvases, tables, and report previews resize
  without layout shift.

## Mycelium-Specific Checks

- App shell: sidebar navigation must collapse into a mobile navigation pattern
  without hiding core routes.
- Dashboards: metric cards should stack cleanly, preserve labels, and avoid
  cramped chart legends.
- Tables: research, grants, fellowships, and member tables need mobile views
  such as cards, column priority, or horizontal containment with clear affordance.
- Knowledge graph: provide a usable fallback for small screens, such as search,
  filters, selected-node detail panels, and summary lists.
- Reports: long-form content should preserve readable line length and allow
  citations, evidence trails, comments, and export actions to remain reachable.
- Job states: running scans and report-generation statuses should remain visible
  without relying on desktop-only side panels.

## Performance Expectations

- Keep the public site fast and SEO-friendly.
- Lazy-load heavy dashboard charts, graph explorers, rich editors, and report
  previews where possible.
- Use skeletons or meaningful loading states instead of blank panels.
- Avoid loading graph visualization libraries on routes that do not need them.

## Output Expectations

- Call out any element that risks overflow, clipped content, tiny tap areas, or
  unreadable text.
- Specify mobile behavior for navigation, tables, dashboards, graph views, and
  reports.
- Pair this skill with `ui-frontend` for visual decisions and with
  `ada-compliance` for accessibility-sensitive workflows.
