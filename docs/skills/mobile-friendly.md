# Mobile Friendly Skill

Use this skill when designing or implementing responsive, mobile-first web
experiences that must work cleanly on phones and small tablets.

## Core Rules

- Start with a mobile-first layout.
- Include the viewport meta tag on every page.
- Use fluid grids, `clamp()`, `fr`, and percentage-based layouts instead of
  fixed widths.
- Prevent horizontal scrolling at common mobile widths.
- Keep body text at least 16px and preserve readable line lengths.
- Make touch targets at least 44x44px where possible.
- Avoid hover-only interactions.
- Ensure images, video, and embeds resize without layout shift.

## Mobile Checks

- Layout: single-column collapse on small screens, no clipped content.
- Typography: fluid type, comfortable line height, and readable metadata.
- Touch and navigation: large hit areas, visible active states, and bottom-
  reachable primary actions.
- Media: responsive `srcset`, lazy loading, width/height attributes, and
  `playsinline` for video.
- Performance: fast initial load, skeletons instead of blank states, and
  minimal blocking work.
- SEO parity: keep mobile and desktop content equivalent.
- Accessibility on mobile: semantic HTML, alt text, reduced motion, and screen
  reader support.

## Output Expectations

- Recommend concrete responsive breakpoints or layout changes.
- Call out any element that risks overflow, tiny tap areas, or unreadable text.
- Pair this skill with `ui-frontend` for visual design work and with
  `ada-compliance` for accessibility-sensitive changes.

