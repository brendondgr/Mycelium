# UI Frontend Skill

Use this skill when designing or implementing Mycelium's visual system,
components, pages, dashboards, reports, graph views, and interaction patterns.

## Dependencies

- Use `website-architecture` before UI work so routes, auth, data flow, and the
  Next.js/Django boundary are known.
- Pair with `mobile-friendly` for responsive behavior.
- Pair with `ada-compliance` for WCAG 2.2 AA checks.

## Product Direction

Mycelium should feel like calm organic intelligence: warm, scholarly,
trustworthy, research-focused, and connected to the Mylo mushroom scout mascot.
Avoid generic SaaS-blue styling, harsh neon AI visuals, and decorative clutter.

## Brand Palette

Use semantic color tokens. These values come from the Mylo/Mycelium direction in
`docs/chats/color-scheme.md`.

```text
Light theme:
background      #F8F4EC
surface         #FFFDF8
surface-alt     #EFE7D7
primary         #5E7A3E
primary-hover   #4D6733
secondary       #8DA66F
accent          #C9A35A
accent-soft     #E7D8B8
text-primary    #2E3627
text-secondary  #5F6853
text-muted      #7F8775
border          #D9D0BE
divider         #E8E0D1
success         #6F8F4E
warning         #B88A3B
danger          #A85C52

Dark theme:
background      #161B14
surface         #1D241A
surface-alt     #253021
primary         #8DA66F
primary-hover   #A0B77F
secondary       #6F8A56
accent          #D3AE66
accent-soft     #5B4A2A
text-primary    #F2EBDD
text-secondary  #C9C1B2
text-muted      #9E988B
border          #394431
divider         #2B3427
success         #94B36B
warning         #D0A257
danger          #C97A70
focus           #B8D99A
```

## UI Stack

- Astro, Tailwind, MDX, GSAP, and light React islands for the public landing
  site.
- Next.js App Router and React for the authenticated lab app.
- Shared Tailwind v4 color tokens in `web/packages/config/src/theme.css`.
- shadcn/ui and Radix UI for accessible React primitives.
- Framer Motion for dynamic app transitions and workflow motion.
- TanStack Table for sortable, filterable research, opportunity, and member
  tables.
- TanStack Query for API-backed app state.
- React Hook Form and Zod for forms.
- Cytoscape.js first for knowledge graph exploration; consider Sigma.js later
  if graph scale demands it.
- TipTap for editable reports, citations, comments, and rich text sections.

## Component Rules

- Public pages should use custom Tailwind sections rather than app-heavy
  component chrome.
- Authenticated routes should use a dense but readable app shell with sidebar
  navigation, lab switcher, alerts, role-aware actions, and stable layouts.
- Use Mylo sparingly in onboarding, empty states, alerts, and discovery moments.
  The mascot should support the workflow rather than dominate it.
- Charts, graph views, badges, and opportunity scores must not rely on color
  alone.
- Motion should be quiet and purposeful, with `prefers-reduced-motion` support.

## Output Expectations

- Define page states before implementation: loading, empty, populated, error,
  permission denied, job running, and stale data.
- Name the primary components, route ownership, data dependencies, and actions.
- Include visual, responsive, and accessibility checks in every UI plan.
