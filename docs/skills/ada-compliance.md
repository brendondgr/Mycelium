# ADA Compliance Skill

Use this skill when auditing, designing, or implementing Mycelium web content
that must meet WCAG 2.2 AA accessibility expectations.

## Core Rules

- Use semantic HTML first.
- Do not rely on color alone to communicate meaning.
- Ensure keyboard access for every interactive control.
- Keep visible focus states, logical heading order, and descriptive labels.
- Require text contrast of at least 4.5:1 for normal text and 3:1 for large
  text and non-text UI.
- Provide alternatives for media, motion, and embedded content.
- Respect `prefers-reduced-motion`.

## Mycelium Audit Areas

- **Public pages:** landmark structure, descriptive links, accessible forms, and
  SEO-friendly semantic headings. The site's interactivity is CSS radio groups
  and a native `<details>` menu — verify each still announces its state and is
  operable from the keyboard, and that every scroll-driven reveal degrades to its
  visible default under `prefers-reduced-motion`.
- **App shell:** skip links, keyboard navigation, focus management, visible active
  route state, and no keyboard traps in the sidebar, lab switcher, or menus.
- **Editor modals:** `EditorModal` must keep its `tablist` / `tab` / `tabpanel`
  roles, roving arrow-key navigation, Escape-close, body scroll lock, and focus
  return.
- **Feed cards:** `MatchRing` must expose its percentage and fit tier as text, not
  as arc geometry alone. Cluster badges must not encode meaning in color alone.
- **Feeds:** the progressive reveal needs its `sr-only` "Load more" control; a
  filter change that collapses the feed must be announced, not silent.
- **Grants and fellowships:** form labels, eligibility explanations, deadline
  warnings, score explanations, and the reminder composer's offset builder.
- **Reports:** semantic sections in the rendered markdown, and a reachable link to
  the same content when the PDF is the primary artifact.
- **Alerts and jobs:** live regions for status changes (the bell, a running scan),
  readable timestamps, and accessible error recovery.
- **Locked affordances:** a gated control renders muted-but-focusable with the
  reason in its accessible name — never silently missing.

## Output Expectations

- Produce a concrete checklist or page audit.
- Separate WCAG blockers from advisory improvements.
- Name the exact route, component, or interaction that needs changes.
- Include keyboard, screen reader, contrast, reduced-motion, and mobile checks.
