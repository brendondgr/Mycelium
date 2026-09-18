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

## Discussion gate

No step in this plan is implemented until the implementing agent has presented,
and the owner has approved, a short design brief: the files and models it will
touch, every migration, every prompt and what happens when the model is
unavailable, every
default value and setting name, and what is deliberately not being done. A
deviation discovered mid-implementation stops the work and reopens the brief.
