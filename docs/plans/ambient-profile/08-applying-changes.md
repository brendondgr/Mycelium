# Plan 08 — Applying Changes to the Record

**Status:** draft. **Depends on:** Plans 04–07. **Unblocks:** Plan 09.
**Correlation ID:** `20260917-ambient-profile-08`

## Objective

The only path by which anything Mylo understood becomes part of the declared
interests or the project state. It is a **proposal path**, extended from the
reflection module the repo already has, plus a compact review with undo for the
fast layer. The rule: the person's own words change only when the person says
so; Mylo's interpretation changes freely but stays labelled as Mylo's.

## Steps

1. **Extend `ReflectionProposal`** with new rules beside the existing four
   (`add_method`, `add_exclusion`, `set_milestone`, `review_state`). Each new
   rule is a concrete edit in the shape a PATCH would take, with the evidence
   explanation attached (Plan 06, step 8):
   - `add_area` / `swap_area` — an enduring interest that has room, or a swap
     for a stale one (Plan 04 budget rule).
   - `add_keyword` / `add_exclusion_from_conversation`.
   - `set_preference`, `set_trajectory`, `add_learning_goal` — into the new
     contract fields (Plan 05).
   - `state_fast.*` — stage, milestone date, venue target, blocker opened or
     closed, expertise need, from a development.
   - `state_slow.*` — problem, claimed contribution, method, components: only
     when a development or an understanding **conflicts** with the stated
     text, and phrased as "this seems to have changed — has it?".
   - `retire_interest` — a stale declared area with no evidence for 90 days,
     as a question, never a removal.
   All inherit expiry (14 days), cooldown after rejection (28 days), and the
   "never re-propose a rejected edit inside the cooldown" rule.

2. **Provenance on write.** An accepted proposal writes the field with
   provenance `stated` (the person accepted it) and records the accepting
   channel and the proposal id in `sources` on interests or the state's
   provenance map. A field Mylo proposed but nobody accepted is never written
   to the declared record at all; it lives in the evolving layer as `inferred`.

3. **What applies without asking** (OD-A3). A project fact the person told
   Mylo directly — recorded as a development with undo and a bell
   notification, because they said it is part of the project. Everything
   else — curiosity, explorations, preferences, trajectory, learning goals,
   skills, every declared-profile edit, every project-state edit — waits for
   a yes. There is no "apply my confirmed patterns" tier in the first cut; it
   may be reconsidered only after Plan 10 shows confirmation precision for a
   kind is near certain, and it would still never touch a stated field.

4. **The review lives on the web** (Plan 07's "Mylo & you" page) and is
   summarised in the personal weekly (Plan 09): what was confirmed and applied,
   what is pending, what faded or was declined. Each applied row has undo. Undo
   writes `ObservationFeedback = rejected`, reverts the field or entry, logs
   the revert as its own change, and starts the cooldown.

5. **Project proposals on the web.** Extend `reflection-card.tsx` to show the
   evidence, the reasoning trace summary, and accept / reject / edit — the same
   question as the DM (Plan 06), answered on either surface, closed on both.

6. **Retraction fan-out.** When Plan 01 records a retraction, any confirmed change or
   proposal citing only retracted evidence is withdrawn; a proposal with
   remaining evidence is re-scored by Plan 04.

7. **Lab-associated projects.** A proposal on a lab project is raised to the
   project's members with the manager role and to the PI; any of them can
   accept. Acceptance and the accepting person are recorded and reported in
   the lab's weekly (Plan 09). A personal proposal is never visible to a lab.

8. **API.** Proposals already have `/api/reflections/`; extend the serializer
   with the new rule kinds, the evidence, and the trace; add
   `/api/ambient/review/` for the change feed and undo.

9. **Tests.** Each rule producing the right PATCH shape; a rejected proposal
   not re-raised in cooldown; undo of a confirmed change; a lab proposal invisible to a
   non-member; stated fields untouched by any automatic path.

## Acceptance

- Grep the codebase for writes to `Profile.interests` and `ProjectState`: the
  only new writer is the proposal acceptance path.
- A week of confirmed changes leaves every stated field byte-identical.
- Undo on a confirmed change restores the previous ranking input at the next
  nightly run.

## Open decisions

- **OD-08a** Whether a stated project fact should be echoed back once
  ("noted as a fact for the imaging project — from tomorrow's run") the first
  few times, so the person learns what Mylo does with them. Draft: yes,
  always echoed, never asked.

## Brief as built (2026-09-19)

Implemented overnight on the owner's instruction; the gate's decisions are
recorded here for review.

- **A personal edit's proposal is the question itself.** Plan 06 already asks
  the person, with one choice per edit that exists for them (add to interests,
  a new theme, a swap, a skill, a learning goal, a preference, a direction).
  Their yes is the acceptance; there is no second `ReflectionProposal` for the
  same edit. `apps/ambient/apply.py` (`apply_answers`, first in
  `deliberate_ambient`) carries each yes out at the next nightly run, as the
  question said it would.
- **How it writes** (step 2): through `validate_interests`, with a row in
  `interests.sources.ambient` — field, value, question id, date, where
  answered, `provenance: "stated"`. "Add to my interests" goes into the theme
  with the fewest areas; a new theme gets a slug id (an unclustered profile
  keeps its implicit `c-all` theme); a swap removes exactly the stale theme the
  question named and refuses if it has gone. A correction ("right idea, wrong
  words") is written in the person's words. A seventh theme is refused by the
  contract and reported, never forced.
- **Undo** (step 4): each edit is an `AppliedChange` holding the field before
  and after (for a theme change, areas and clusters together). Undo restores
  exactly that — and **refuses** when the field no longer holds what the edit
  wrote, because the person edited it since; an undo must never discard their
  later edit. Plan 07's undo path logs it and starts the cooldown.
- **Project state** (steps 1, 7): new `ReflectionProposal` kinds
  `close_blocker` and `drop_method` (content migration `0032`), plus
  `add_method`, raised by `apps/content/ambient_proposals.py` from
  developments in effect, matched literally to the stated blockers and methods
  as the alerts match them. A lab development goes to the project's editors; a
  personal one (said in a DM) only to its speaker. 14-day expiry, 28-day rest
  after a decline, never re-raised once accepted. Accepting through the
  existing reflection action applies it and records a `state_edit`
  `AppliedChange` (`ambient.read.note_state_change`) with undo.
- **Retraction** (step 6): a pending proposal whose development is undone,
  declined, superseded or forgotten is expired at the next run.
- **Web** (step 5): the reflection card marks conversation proposals, says
  when it was said and shows Mylo's explanation; profile chips from a yes carry
  a "heard" mark whose accessible text says when and where it was confirmed.
- **Not built, deliberately:** proposals for keywords, exclusions,
  `state_slow` conflicts ("this seems to have changed — has it?"), milestone
  dates and "retire a stale interest". Each needs evidence Plan 10 has not
  produced yet; the rule is unchanged — nothing reaches a stated field
  without a yes. OD-08a (echo a told fact back): answered yes by Plan 06's
  reply to a told fact.
- **Tests:** `apps/ambient/tests/test_apply.py` (each edit's shape, exact
  undo, undo refused after a later edit, applied once, a no writes nothing,
  the contract refusing, an AST check that `apply.py` is the app's only writer
  of `Profile.interests`); `apps/content/tests/test_ambient_proposals.py`
  (proposal shapes, only editors, private to its speaker, rest after decline,
  withdrawn on retraction, a non-target cannot accept or see it, accept changes
  only the named field, undo refused after a later edit, a rejection records
  nothing).

## Discussion gate

No step in this plan is implemented until the implementing agent has presented,
and the owner has approved, a short design brief: the files and models it will
touch, every migration, every prompt and what happens when the model is
unavailable, every
default value and setting name, and what is deliberately not being done. A
deviation discovered mid-implementation stops the work and reopens the brief.
