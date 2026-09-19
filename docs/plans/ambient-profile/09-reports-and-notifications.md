# Plan 09 — Reports and Notifications: What Changed, For Whom

**Status:** draft. **Depends on:** Plans 05–08. **Unblocks:** Plan 10.
**Correlation ID:** `20260917-ambient-profile-09`

## Objective

The most valuable changes show up in the reports, and they show up in the
**right** report. Two separate streams:

- **Personal changes** — to one person's interests, preferences, trajectory,
  curiosity, or their personal projects — reach **that person only**, in
  their personal weekly and DM.
- **Lab-associated project changes** — developments, accepted proposals,
  attention shifts on a project that belongs to a lab — reach the **lab's
  updates channel and each member of that project**, in the lab weekly and in
  each member's personal weekly under that project's part.

A change made for one person and not for their lab is never announced to the
lab. A change to a lab project is announced to the lab and to its members.

## Steps

1. **A "What changed" section in the weekly**, rendered from structured data
   through the existing code frame (`weekly.py`), never free prose:
   - *Your understanding* (personal only): explorations confirmed, kept, or
     faded; proposals accepted or pending; the questions answered this week
     and on which surface. Every row links to the web change it describes.
   - *Projects* (personal weekly: the person's projects, own and lab; lab
     weekly: shared projects only): developments recorded, proposals accepted
     and by whom, blockers opened or closed, attention share ("most of your
     week went to the imaging pipeline").
   Every row cites the observation it rests on with the `[S:path]` state
   marker grammar or a new `[O#]` observation citation added to
   `report_grammar.py`, and the verifier (`weekly_verify.py`) learns to resolve
   `[O#]` against the packet.

2. **Extend the weekly packet** (`weekly_packet.py`, `weekly_build.py`) with
   the week's developments, accepted and pending proposals, attention shares,
   and the `context_version` used. The packet's scope rule already keeps
   personal material out of a lab packet; the new rows carry `visibility` and
   the builder drops `personal` rows from a lab packet.

3. **The interpretation sentence.** One code-framed line per personal weekly:
   "You confirmed an exploration of evaluation on Tuesday, so this week gives
   more attention to benchmarks and error analysis." It is generated from the
   confirmed exploration rows, not by a model, names the confirmation it rests
   on, and is followed by "Not right? Tell me", which opens the DM dialogue
   (Plan 06) or the web review (Plan 07).

4. **"Why this matters now."** Stage-two write-ups gain an optional fourth beat
   grounded in a development or a confirmed understanding: "your blocker on
   annotation cost is what this addresses". Rendered only when a development or
   understanding actually links; never padded.

5. **Routing.** Extend `delivery.py`'s cadence matrix:
   - Personal "what changed" → the person's DM with their weekly (or daily on
     the day a proposal is accepted, as one line, not a separate message).
   - Lab project changes → the lab's updates channel with the lab weekly, and
     to each member of that project in their own weekly's project part.
   - An accepted lab proposal → one line in the lab channel the day it is
     accepted, naming the field and the accepter, under the existing daily cap
     for lab posts.
   - Nothing on weekends; urgent alerts unchanged.

6. **Bell notifications.** Personal proposals and lab proposals both raise a
   bell notification through `alert_report.py`'s existing path so the web
   shows them without Discord.

7. **The daily.** The daily gains only one thing: the attention-ordered project
   parts (Plan 05) and, when a development changed what is useful, a
   "Needs your attention" line reusing the existing section. The daily is not
   the place for the change log.

8. **PDF and app.** The section renders in the PDF via the existing flowable
   builder and in the app via `MarkdownProse`, because it uses the shared
   grammar. The reports history page shows the `context_version`.

9. **Tests.** A personal change absent from a lab packet; a lab project change
   present in the lab packet and in each member's personal packet; `[O#]`
   citations resolving; the interpretation sentence absent when no curiosity
   is active.

## Acceptance

- A private trajectory change never appears in any lab surface.
- A lab project development appears in the lab weekly and in every member's
  weekly, once each.
- Every "what changed" row cites an observation or a proposal that resolves.

## Open decisions

- **OD-09a** Whether the lab channel gets a same-day line for developments
  (not just accepted proposals). Recommendation: no; the weekly is the unit for
  developments unless an alert trigger fires.

## Brief as built (2026-09-19)

Implemented overnight on the owner's instruction; the gate's decisions are
recorded here for review.

- **"What changed" is code, not model prose** (steps 1–2,
  `apps/content/weekly_changes.py`). Every `AppliedChange` that took effect this
  week is read through `apps.ambient.read.changes_between` and numbered `[O#]`
  (a new citation in `report_grammar.py`, rendered like `[P#]` by the PDF and
  `MarkdownProse`). The section sits in the weekly's frame after the checked
  body.
  - *Your understanding* (personal weekly only): explorations confirmed, kept
    or let go; understanding confirmed; profile edits; undos; how many
    questions were answered and where.
  - *Projects*: developments told or confirmed, stated state accepted and by
    whom, undos; the project the week's conversation went to; conversation
    proposals waiting.
  - Links go to "Mylo & you", one per section rather than per row, because the
    page has no per-change anchor.
- **Scope is the query.**
  - A person's rows are their own changes plus lab-visible ones on their
    projects.
  - A lab's rows are lab-visible changes on the projects it shares
    (`share_in_lab_reports`); a personal change cannot match.
  - The same rule was applied to Plan 07's lab "What changed" card, which had
    been showing unshared projects' changes to every lab member (fixed in
    3676d91).
- **The model may connect, never restate.** Each project's packet carries its
  change rows. The weekly prompt (`w2`) lets the model say in one sentence why
  an item matters now, citing both (`[P3][O2]`). The verifier removes any
  sentence citing an `[O#]` the packet does not hold. This is step 4 ("why
  this matters now") for the weekly.
- **The interpretation line** (step 3) is code-framed from a confirmed,
  not-undone exploration, and appears **only when `AMBIENT_DRIFT_ENABLED` is
  on**. Explorations move the ranking only then, and the sentence would
  otherwise be false.
- **`context_version`** is stored on the weekly row too.
- **Dailies** (steps 5 and 7): a "Changed today" block under "Needs your
  attention", in the web and PDF report and as a field in the Discord post.
  - Personal: profile edits, accepted stated-state edits, and a development
    that changed what the alerts flag, with the effect said plainly.
  - Lab: only a stated-state edit accepted on a shared project, with the
    accepter. A lab post is made for it even on an otherwise quiet day, and it
    remains one post a day.
  - OD-09a: no same-day lab line for a development.
- **The bell** (step 6): each conversation proposal rings its target's bell
  once (`suggestion_pending`, linking to the project page). The bell is
  dismissed when the proposal is withdrawn.
- **Not built, deliberately:** the "why this matters now" beat in the daily's
  per-item stage-two write-ups. Write-ups are cached per item and target, so
  adding a development beat means regenerating them whenever a development
  changes, and their quality is Plan 10's to measure. The weekly carries the
  link instead.
- **Tests:** `apps/content/tests/test_weekly_changes.py` (routing in every
  direction, `[O#]` resolution and removal, the interpretation line with drift
  off, on and undone, last week excluded, answers and waiting proposals
  counted, `context_version`, the grammar, the PDF marker, the daily lines, the
  lab embed); the bell in `test_ambient_proposals.py`; the lab card in
  `apps/ambient/tests/test_review.py`.

## Discussion gate

No step in this plan is implemented until the implementing agent has presented,
and the owner has approved, a short design brief: the files and models it will
touch, every migration, every prompt and what happens when the model is
unavailable, every
default value and setting name, and what is deliberately not being done. A
deviation discovered mid-implementation stops the work and reopens the brief.
