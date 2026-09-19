# Plan 05 — The Evolving Profile Layer

**Status:** draft. **Depends on:** Plan 04 and
CN-01 (`apps/knowledge`, shipped 2026-09-18). **Unblocks:** Plans 06,
07, 08, 09, 10.
**Correlation ID:** `20260917-ambient-profile-05`

## Objective

Store what Mylo currently understands about a person and a project **beside**
the declared profile and project state, at three speeds, and make that
understanding reach **retrieval, ranking, and explanation** — not only the
writing prompt. The declared profile stays the person's own words and keeps its
budget. The evolving layer is Mylo's evidence-backed interpretation, always
inspectable, always correctable, and never the thing that spends a cluster.

## The stores

1. **Understanding as conversational edges** (per user, in the shared
   knowledge core, CN-01 — this answers OD-A1: not a sidecar and not a table of
   its own, but `Edge` rows with `tier = conversational` against shared
   `Concept`s). Each edge carries its `understanding_kind` ∈ {enduring,
   curiosity, preference, trajectory} as the relation's qualifier, and
   `weight`, `first_seen`, `last_reinforced`, `half_life_days`, `status`
   (`pending`, `active`, `faded`, `rejected`), and the evidence pointers
   (observation ids). Because declared profile entries are mirrored into the
   same graph as `declared` edges, "already covered", "declined near-synonym",
   and "what Mylo knows beside what you wrote" are all one lookup. A
   conversational edge is readable by the person and by their own ranking
   only — never by a lab-mate and never by collaboration search (the tier
   table in `../collaboration-network/README.md`). Rows are written as `pending` by Plan 04's suggest
   outcome; only `confirmed` rows (a yes in Plan 06) are read by ranking or
   explanation. `rejected` rows are kept so the agent does not raise them
   again for 30 days, and after that only if the consistency test is met
   again. Every row is **editable and deletable by the person** on the web
   (Plan 07); a person's edit is a stated entry.
   In the rows below, "row" means one of these edges. Rows are never discarded on
   a subscription lapse — the memory pauses and keeps. A confirmed `curiosity` row is an
   **exploration**: it carries a `review_on` date after which Mylo asks
   "keep this?", and it never counts against cluster or topic caps.

2. **`ProjectDevelopment`** (per project). Dated events: `kind` (dataset
   arrived, experiment failed, venue changed, blocker closed, blocker opened,
   milestone moved, method dropped, method adopted, result obtained),
   `text`, `explanation`, `occurred_on`, `recorded_on`, `speaker`, `force`,
   `status` (`active`, `superseded`, `confirmed`, `rejected`), and the
   observation ids. This is the "what is useful now" record. It does not edit
   `ProjectState`; Plan 08 proposes state edits from it.

3. **`ProjectAttention`** (per user per project): the 7- and 28-day attention
   share from Plan 03, recomputed nightly.

## What the memory is for

This store is the long-lived record of what Mylo understands about a person:
their enduring interests, what they are exploring, what they prefer, where
they want to go, what they can do. It accumulates over time and is theirs to
edit. It is what Mylo's suggestions are grounded in: Mylo suggests things the
person has already shown they want — a topic they keep returning to, a
direction they said they were heading, a need a project stated — because
they said so, and never a direction Mylo invented. It reaches those
suggestions through Plan 04's suggest outcome and reaches ranking and
explanation through the steps below.

## Three speeds

4. **Confirmed, then nightly.** Curiosity and ambient developments are
   written as pending and become active on a yes (Plan 06), taking effect at
   the next nightly run — there is no real-time refit, and the person is told
   "from tomorrow's run". The one automatic write is a project fact the
   person told Mylo directly, recorded with undo and likewise read by the
   next run. An exploration fades at its review date unless kept;
   a development is superseded by a later one on the same subject. All of it
   is visible on the web (Plan 07) with what, how, and why.
5. **Slow, by confirmation.** Enduring interests, preferences, trajectory, and
   anything in the declared profile change only through a confirmed proposal.
6. **Conflict, by proposal.** A development or an understanding that
   contradicts a stated project claim or goal raises a proposal, never an edit.

## New understanding kinds in the contract

7. Extend the interests contract (`accounts/interests.py`) with three optional
   fields that hold **confirmed** understanding only: `preferences` (list of
   short strings: "empirical over theoretical", "reproducible code matters"),
   `trajectory` (a short free-text direction plus an optional target stage and
   horizon), and `learning_goals` (topics the person wants to learn, explicitly
   not skills). All three carry provenance in `sources`. None of them count
   against cluster or topic caps. The validator's unknown-key rule means this
   is a deliberate schema change with a migration of existing rows (no-op).

## Reaching retrieval and ranking

8. **Exploration vectors, never one average.** Each **confirmed**
   exploration edge contributes its concept's vector, with its decayed weight,
   as an additional query for the profile — scored per concept and taking the
   best match, not folded into one averaged vector. Averaging a person's
   explorations flattens mixed interests into a vector that represents none of
   them (`../collaboration-network/design.md` §5.3). The contribution is
   capped at `AMBIENT_DRIFT_WEIGHT` (default small, e.g. 0.15) relative to the
   declared statement + keywords embedding, which stays dominant. The
   blend happens in `targets.py` when the `MatchTarget` is built, so every
   stage downstream sees it. Recorded as a ranking-logic change: the eval
   harness must be re-run and numbers put in the changelog (global rule).
9. **Attention-weighted project parts.** The project a person is actually on
   this week gets its per-project part first in the report and a slightly
   deeper slate; an idle project is not dropped, just not first.
10. **Developments reach the matchers.** `alerts.py` triggers read active
    developments: a closed blocker stops `unblocks` firing for it; a moved
    milestone re-runs `timeline`; a dropped method changes what `overlap_risk`
    compares against — through the proposal path where the field is stated,
    directly where it is only a development.
11. **Preferences reach explanation and ordering.** Stage-two write-ups
    (`cluster_fit.py`) receive confirmed preferences so a beat can say "has
    code and an ablation, which you weigh". A preference re-rank boost is a
    later, measured step, not part of this plan.
12. **Trajectory reaches opportunities.** Fellowship and grant matching read
    `trajectory` alongside `seeking` and stage: a person moving toward
    clinical work sees clinical training fellowships they are eligible for
    ranked higher. The eligibility gate is unchanged.

## Context versioning

13. Every nightly run stamps the `context_version` it ranked and wrote with: a
    hash over the declared profile, the confirmed understanding, and the active
    fast layer. It is stored on `DailyBriefing` and on write-ups. When the
    version changes, affected explanations refresh on the next run; old
    reports remain interpretable because the version they used is known.

## Steps

14. Models and migrations for `ProjectDevelopment` and the contract fields;
    the conversational-edge writer through `apps/knowledge/service.py`
    (no new ambient table for understanding).
15. The pending-row writer, the confirmation activation hook, and the review-date fade task (nightly, in `manual_all.py`).
16. `targets.py` drift blend behind `AMBIENT_DRIFT_ENABLED` (ships off).
17. Attention ordering in `briefing.py` project parts.
18. Developments wired into `alerts.py`.
19. Preferences and trajectory into the profile text at `briefing.py:623` and
    into `cluster_fit.py` and the fellowship band prompts.
20. `context_version` on `DailyBriefing` and write-up keys.
21. Eval harness run before and after step 16 with results in the changelog and
    a research-record experiment folder.

## Acceptance

- A curiosity row with no reinforcement for two half-lives reads `faded`.
- The drift blend changes a query vector by no more than the cap.
- A stated field is byte-identical before and after a week of confirmed changes.
- The eval harness shows no regression on the declared-only arm with drift off.

## Open decisions

- **OD-05a** Drift cap default and whether it scales with the number of active
  curiosity edges. Recommendation: fixed cap; tune in Plan 10.
- **OD-05b** Whether attention ordering applies to lab reports. Recommendation:
  personal only; a lab's attention is a different measure.

## Brief as built (2026-09-19)

Implemented overnight on the owner's instruction; the judgement calls:

- **Edges carry their kind.** `Edge.qualifier` (the understanding kind),
  `Edge.review_on` (an exploration's "keep this?" date) and
  `Edge.edited_by_person` (knowledge migration `0005`). Written only through
  `knowledge/service.py`: `record_conversational` now takes the concept the
  ledger already linked, and reinforces (restarts the clock) only on *new*
  evidence, so rerunning a night is not the person coming back to a topic.
- **`ProjectDevelopment`** lives in `apps/ambient` (migration `0007`), with a
  `pending` status beside the plan's four, an origin (told / conversation),
  and a `change` kind the extractor now reports (prompt `a3`). A told fact is
  `active` at once; ambient development talk is `pending`. Later supersedes
  earlier on the same (project, concept, visibility).
- **`apps/ambient/evolve.py`** is the nightly writer (step 15), run by
  `deliberate_ambient` after explaining: findings → pending edges and
  developments; fade at two half-lives; retraction fan-out (it also covers
  Plan 08 step 6 for everything Plan 05 builds).
- **Reaching ranking — per theme, not a blended vector.** Step 8's "additional
  query per concept, capped" is built as: each confirmed exploration joins a
  person's paper search as **its own theme** (after the declared ones), and in
  the global ranking its score counts at `AMBIENT_DRIFT_WEIGHT` (0.15) of a
  declared theme's (`fusion.combine_clusters(cluster_weights=…)`). Its own
  slate keeps its own order. **Deviation:** the acceptance line "the drift
  blend changes a query vector by no more than the cap" does not apply — no
  vector is blended; the tested equivalent is that an exploration cannot
  outrank an equally strong declared candidate. Ships off
  (`AMBIENT_DRIFT_ENABLED=false`); off, ranking is byte-identical.
- **Trajectory reaches opportunity *judgement*** (the grant/fellowship prompts,
  beside stage), not retrieval: that would be a second ranking change.
- **Preferences reach explanation** via the prompts' profile text. They are
  not in any write-up's reuse key: the global rule never re-bills a write-up
  for a context change, so new preferences shape the next write-up asked for.
- **`context_version`** is stamped on `DailyBriefing` only (content migration
  `0030`), for the same reason.
- **Attention ordering** (step 9) orders a person's report projects by 7-day
  share and gives a clear leader (≥ `AMBIENT_ATTENTION_LEAD_SHARE`, 0.4)
  `AMBIENT_ATTENTION_EXTRA_ITEMS` (2) more items. Personal reports only.
- **Developments reach the alerts** (step 10): a closed blocker is left out of
  `unblocks`, a dropped method out of the `overlap_risk` approach — both by a
  literal content-word match (`matchers/developments.py`). A moved milestone
  needs a date, which is Plan 08's proposal; nothing here edits state.

## Discussion gate

No step in this plan is implemented until the implementing agent has presented,
and the owner has approved, a short design brief: the files and models it will
touch, every migration, every prompt and what happens when the model is
unavailable, every
default value and setting name, and what is deliberately not being done. A
deviation discovered mid-implementation stops the work and reopens the brief.
