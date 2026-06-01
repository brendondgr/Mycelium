# ADA Compliance Skill

Use this skill when auditing, designing, or implementing web content that must
meet WCAG 2.2 AA accessibility expectations.

## Core Rules

- Use semantic HTML first.
- Do not rely on color alone to communicate meaning.
- Ensure keyboard access for every interactive control.
- Keep visible focus states, logical heading order, and descriptive labels.
- Require text contrast of at least 4.5:1 for normal text and 3:1 for large
  text and non-text UI.
- Provide alternatives for media, motion, charts, and embedded content.

## Audit Areas

- Images and non-text content: alt text, decorative handling, complex
  description text.
- Audio and video: captions, transcripts, audio descriptions, and controls.
- Structure and semantics: headings, lists, tables, `lang`, and reading order.
- Color and visuals: contrast, zoom reflow, spacing, and color-independent
  meaning.
- Keyboard and navigation: no traps, logical tab order, skip links, and visible
  focus.
- Forms: labels, required field treatment, error messages, autocomplete, and
  review/confirm flows.
- Links and buttons: descriptive names and accessible destination hints.
- Page-level behavior: unique titles, consistent navigation, and no seizure
  risks.
- Motion and dynamic content: pause/stop controls, alternatives to gestures,
  and reduced-motion support.
- Code compatibility: ARIA only when needed, live regions for status, and
  accessible embeds.

## Output Expectations

- Produce a concrete checklist or page audit.
- Call out blocked criteria separately from advisory improvements.
- Name the exact elements or pages that need changes.

