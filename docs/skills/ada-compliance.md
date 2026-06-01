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
- Provide alternatives for media, motion, charts, graph views, and embedded
  content.
- Respect `prefers-reduced-motion`.

## Mycelium Audit Areas

- Public pages: landmark structure, descriptive links, accessible forms,
  responsive content, and SEO-friendly semantic headings.
- Authenticated app shell: skip links, keyboard navigation, focus management,
  visible active route state, and no keyboard traps in sidebars or menus.
- Dashboards and charts: accessible names, data tables or summaries, non-color
  encodings, and clear status text.
- Knowledge graph explorer: keyboard-accessible search, filters, selected-node
  details, text summaries, and alternatives to canvas-only information.
- Research reports: semantic sections, citation links, evidence trails,
  comments, export buttons, and accessible document previews.
- Grants and fellowships: form labels, eligibility explanations, deadline
  warnings, score explanations, and review/confirm flows.
- Alerts and jobs: live regions for status changes, readable timestamps, and
  accessible error recovery.

## Output Expectations

- Produce a concrete checklist or page audit.
- Separate WCAG blockers from advisory improvements.
- Name the exact route, component, or interaction that needs changes.
- Include keyboard, screen reader, contrast, reduced-motion, and mobile checks.
