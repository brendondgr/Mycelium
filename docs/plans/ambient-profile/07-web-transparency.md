# Plan 07 — Web Transparency: What Changed, How, and Why

**Status:** draft. **Depends on:** Plans 05, 06. **Unblocks:** Plans 08, 09.
**Correlation ID:** `20260917-ambient-profile-07`

## Objective

Every change Mylo makes or wants to make is visible in the web app, with
**what** changed, **how** it was applied, and **why** Mylo thought so, in a
place the person will actually see. Nobody should have to guess why a
recommendation moved or where a new theme came from. Every pending suggestion
can be answered on the web, and every applied change can be undone there.

This plan owns the frontend for Plans 05, 06, and 08. It follows
`docs/styles.md`, `web/CLAUDE.md`, the ui-frontend and mobile-friendly skills,
and reuses the portal primitives rather than inventing new ones.

## Surfaces

1. **The bell.** Extend the existing notifications with three kinds:
   `suggestion_pending` ("Mylo has a question about your themes"),
   `change_applied` ("Added *uncertainty estimation* as an exploration — you
   confirmed on Discord"), and `change_undone`. Each links to the row on the
   review page. Unread counts follow the existing bell rules.

2. **"Mylo & you" page** (a new workspace section, personal scope) with three
   tabs:
   - **Needs your answer.** Pending suggestions as cards: the finding in one
     sentence, Mylo's explanation (what, on which dates, where, how often,
     and why it read it that way — never a quote), the choices offered
     (reports, interests, new cluster if there is room, a project, no), what
     will not happen, and when a yes takes effect. Answering here closes the
     DM copy.
   - **What changed.** A dated feed of every applied change: the field, the old
     and new values or the added entry, who confirmed it and where, the
     reasoning trace summary, and Undo. Filters by kind and project.
   - **Faded and declined.** Explorations that expired, findings the person
     said no to, and when they become eligible again (30 days after the no).
   - **What Mylo knows.** The memory itself: every understanding entry
     (enduring, exploring, preference, direction, skill) and every project
     development, with its dates and Mylo's account of where it came from.
     Each is editable and deletable in place; an edit is the person's own
     word and is marked as such. It reads the person's edges from the shared
     knowledge core (`read.own_edges`, CN-01), so every entry carries its
     evidence tier — *you wrote this*, *your papers show this* (CN-02),
     *from conversation, confirmed on <date>* — and the page says plainly
     that conversation-derived entries are seen by nobody else and never
     make the person findable. This is the long-lived record every
     suggestion is grounded in, shown plainly so the person can keep it true.
   Empty states say so plainly ("Nothing pending. Mylo will ask here or on
   Discord when it notices something worth checking").

3. **Profile editor annotations.** In `profile-editor-modal.tsx`, every
   interest, preference, trajectory, and learning-goal entry shows a small
   provenance tag: *you wrote this*, *you confirmed Mylo's suggestion on
   <date>*, *exploration until <date>*. Hover or tap opens the reasoning
   summary. The declared themes are visually separate from explorations so the
   budget is legible.

4. **Project pages.** Extend `reflection-card.tsx`: proposals show evidence and
   trace; a **Developments** timeline lists dated developments with source and
   undo; the state editor shows *stated* / *inferred* / *confirmed on <date>*
   per field, which the state model already records.

5. **Feeds and report entries.** When an item is ranked or explained using a
   confirmed exploration, preference, or development, the card's cluster row
   gains a badge (*exploring: X*, *your blocker: annotation cost*) reusing
   `cluster-badge.tsx`. Clicking it opens the change that caused it.

6. **Reports page.** Each briefing in history shows its `context_version` and a
   link to "what Mylo understood when this was written".

7. **Lab surfaces** (lab scope): a lab "What changed" tab for shared projects
   only, showing accepted proposals and developments with who confirmed them.
   Personal items never render here; the API enforces it, the UI does not
   merely hide it.

8. **Settings.** Under the profile's Discord panel and in Account: listening
   opt-in/opt-out per platform, "personal findings from lab channels" on/off,
   a single **Shut off Mylo's questions** switch (the same one "shut off" in
   a DM flips), quiet period, and a plain statement of what is stored: *Mylo
   does not keep your messages. It keeps short summaries of interests and
   project changes, with the dates and the kind of place they came up, and
   only after you confirm them do they affect anything.* A **Delete my
   observations** action with confirmation, wired to Plan 01's retraction.
   On a free tier the whole panel is shown read-only with one sentence saying
   the feature is part of the paid plan; nothing is collected.

## API additions (`docs/api-contract.md` in the same change)

9. `/api/ambient/suggestions/` (list, answer), `/api/ambient/changes/` (list,
   undo), `/api/ambient/settings/`, `/api/ambient/observations/` (delete),
   plus the notification kinds. All object-level authorized to the person or,
   for lab rows, to project managers.

## Steps

10. Notification kinds and bell wiring.
11. The "Mylo & you" section, route, nav entry, scope guard, mobile layout.
12. Profile editor provenance tags.
13. Project page developments timeline and proposal evidence.
14. Feed badges and report context link.
15. Lab "What changed" tab.
16. Settings and the stored-data statement.
17. Accessibility pass (ada-compliance skill) and a phone-width pass.

## Discussion gate

Before implementation the agent presents: wireframes or a written layout for
the three tabs and the suggestion card, the exact copy for the stored-data
statement and the empty states, the notification kinds, and the API shapes.
Copy is signed off before it ships; it is the product's promise.

## Open decisions

- **OD-07a** Whether "Mylo & you" is its own section or a tab of the overview.
  Draft: own section; the overview stays the report.
- **OD-07b** Whether undo is time-limited. Draft: no; a change can always be
  reverted, and the revert is itself a logged change.
