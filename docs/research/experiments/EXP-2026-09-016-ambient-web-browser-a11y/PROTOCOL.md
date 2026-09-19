# EXP-2026-09-016 — Protocol

Written 2026-09-19, before any browser run against the ambient pages.

## Question

Do ambient Plans 07 and 08 work in a real browser for a person with a real
history? That history comes from EXP-2026-09-015's sandbox world, with
questions asked and answered, applied changes, developments, and a conversation
proposal on a lab project. Can every control be reached and operated from the
keyboard? Does the feature pass automated WCAG 2.1 AA checks at desktop and
phone width?

## Hypotheses (pre-registered)

- **H1 (flows).** At 1280×800, each of these is a DOM assertion that passes:
  - "Needs your answer" shows the open questions with a labelled answer group;
    answering one by button shows Mylo's reply in a status region and removes
    it from the badge count.
  - "What changed" lists the profile edit, the told fact and the confirmed
    items with an Undo on each. Undoing the profile edit removes the "heard"
    chip from the profile page, and the undone row stays in the history.
  - "What Mylo knows" shows its four sections.
  - "Settings" shows two switches with accessible names; turning questions off
    and on round-trips.
  - The project page shows the conversation proposal marked "Heard in
    conversation" with when it was said. Accepting it changes the stated
    blockers and adds a "Project state edited" row to "What changed".
  - The lab overview shows "What changed in the lab's projects".
  - The account page shows the settings card.
  - The notification bell lists an ambient notification whose link opens
    "Mylo & you" in the same tab.
- **H2 (keyboard).** The page's tabs follow the WAI-ARIA tabs pattern: arrow
  keys move the selection and Tab enters the panel. Every button in the
  ambient regions can be reached with Tab and has a visible focus indicator
  (a computed outline or box-shadow differs from the unfocused state).
- **H3 (automated accessibility).** axe-core (`wcag2a`, `wcag2aa`, `wcag21a`,
  `wcag21aa`), scoped to `[data-ambient]` regions: zero violations of impact
  `serious` or `critical` on every ambient surface at both widths. `moderate`
  and `minor` findings are reported.
- **H4 (phone).** At 390×844, no horizontal page scroll on any of these pages,
  and every answer button is at least 24×24 CSS px (WCAG 2.2 target size,
  minimum).
- **H5 (clean).** No console errors on any page.

Reported without a bar: whether repeated controls ("Undo", "Edit",
"Delete") have names that say what they act on.

## Setup

- System: the commit in `manifest.yaml`. The API is a second backend container
  (`code/sandbox_stack.sh`, from EXP-2026-09-009's) on its own sandbox
  database with `AMBIENT_ENABLED=true`, on its own Redis database. The web
  server proxies to it with its own `.next`.
- Data: `mycelium_sandbox_ambweb`, a copy of `mycelium_sandbox_ambient` as
  EXP-2026-09-015 run 4 left it, migrated to the commit. `code/prep.py` then
  uses the real functions wherever they exist:
  - make `amb_b3_cyra` the PI of her lab (the world has no memberships);
  - run the nightly applier (`apply.apply_answers`), which writes the "heard"
    profile items from her answered yeses;
  - re-ask two of her questions as fresh open ones, copying the real
    questions' text and choices, because run 4 answered them all;
  - record one told project fact through `review.record`;
  - plant one blocker in Project B2's stated state, and a confirmed lab
    development that closes it;
  - run the real `deliver_ambient_questions` for the bell, the announcements
    and the proposal.

  Every planted row is listed in `data/prep.json`.
- Browser: Playwright Chromium on the host, signed in as `amb_b3_cyra`
  (password `x`). axe-core 4.x is injected from `web/node_modules`. The
  phone pass is read-only and runs first; the desktop pass makes the
  changes.

## Procedure

```bash
SANDBOX_DB=mycelium_sandbox_ambweb docs/research/experiments/EXP-2026-09-016-ambient-web-browser-a11y/code/sandbox_stack.sh up
uv run python docs/research/experiments/EXP-2026-09-016-ambient-web-browser-a11y/code/browser_check.py \
  --base http://localhost:18002 --api http://localhost:18001 --username amb_b3_cyra --password x \
  --prep docs/research/experiments/EXP-2026-09-016-ambient-web-browser-a11y/data/prep.json \
  --out data/sandbox-browser/exp016
```

Budget: under 45 minutes including the stack build.

## What would falsify this

Any H1 assertion, any H2 check, any serious or critical axe violation (H3),
any H4 check, or any console error (H5) failing.
