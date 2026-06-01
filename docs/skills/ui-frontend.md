# UI Frontend Skill

Use this skill when designing or implementing frontend UI after the site
structure is known.

## Dependency

- For websites and dashboards, use `website-architecture` first.
- Do not invent route, auth, or data-flow assumptions from UI preferences
  alone.
- Pair this skill with `ada-compliance` for accessibility-sensitive UI work and
  with `mobile-friendly` for responsive behavior and touch-target checks.

## Design Rules

- Choose an intentional visual direction instead of a generic system look.
- Avoid default font stacks and avoid color palettes that feel accidental.
- Keep the interface mobile-first and readable on a 320px viewport.
- Respect WCAG 2.2 AA contrast, focus, and keyboard requirements.
- Use motion sparingly and respect `prefers-reduced-motion`.

## Component System

- Colors and themes: token-driven, contrast-safe, color not used as the only
  signal.
- Typography: fluid type, readable body size, sane line length, semantic
  heading order.
- Layout: responsive grids and flex layouts, no forced horizontal scroll.
- Motion: purposeful transitions and staged reveals only.
- Controls: 44x44 minimum touch targets, strong focus states, no hover-only UI.
- Overlays: custom dropdowns, menus, and modals with keyboard support.
- Icons and data viz: accessible labels, direct text fallback, and non-color
  encodings when needed.

## Output Expectations

- Define the UI approach before writing code.
- Name the key components, pages, and states that need implementation.
- Include responsiveness and accessibility checks in the implementation plan.
