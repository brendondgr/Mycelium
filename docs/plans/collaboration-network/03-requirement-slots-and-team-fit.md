# Plan CN-03 — Requirement Slots and Team Fit

**Status:** draft. **Depends on:** CN-01. **Unblocks:** CN-05.
**Correlation ID:** `20260918-collaboration-network-03`

## Objective

Turn what a call or a project needs into structured **requirement slots**, mark
which ones the seeker and their own lab already cover, and show that as one
line on every opportunity card (`design §11` steps 1–2). No person outside the
seeker's own lab is involved, so slot quality is validated with real users at
zero privacy risk before anything searches outward.

## Slots from calls

1. Extend `apps/scraper/collect/extract.py`. Today it extracts
   `required_expertise` (0–4 grounded phrases). It becomes
   `requirement_slots`: 0–6 entries of `{facet: problem | method | data | role,
   text, required: bool}`, each grounded in the call's own text by the
   existing grounding check. `role` covers requirements that are not a facet
   ("a co-investigator at a minority-serving institution"): they are shown and
   never matched. `required_expertise` is kept, derived from the slots, until
   `team_gap.py` reads slots directly, so nothing downstream breaks mid-way.
2. The prompt version bumps, so open calls are re-extracted by a bounded
   backfill (`collect_opportunities --reextract-slots`, capped per night).
   Silence in the call means no slots, never an unknown one (the rule
   `team_gap.py` already states).
3. Each slot's text is linked through the CN-01 linker in **global** scope — a
   call is public.

## Slots from projects

4. A project's slots are its stated state: `problem`, `method`, `data`, and
   `needs.expertise`, already mirrored as `declared` project edges by CN-01,
   **in the project's own scope** (principle 6). Inferred fields are shown as
   slots only after a person accepts them, as today.

## Coverage

5. `apps/collab/coverage.py`: for a seeker (a user, a lab, or a project target)
   and a set of slots, each slot is:
   - **covered by you** — the seeker's own edges (`read.own_edges`, active
     tiers only), concept match or facet cosine ≥
     `COLLAB_COVERAGE_COSINE` (default 0.80);
   - **covered by your lab** — a lab-mate's **declared** edge
     (`read.lab_declared_edges`), within `member_fit.scope_members` — the same
     consented scope and the same "stated, not inferred" rule `team_gap.py`
     keeps (principle 10);
   - **gap** — neither.
   Deterministic and model-free.
6. Computed at scoring time for every (target, opportunity) pair already being
   scored and stored in `RelevanceScore.signals["team_fit"]`, so the read path
   stays one query (the `member_fit` storage rule). Only usernames are stored;
   names resolve live.
7. `matchers/team_gap.py` moves onto slots and `coverage.py`. Its alert keeps
   firing only for stated requirements.

## The team-fit line

8. On every grant, conference, and fellowship card, personal and lab:
   "You cover 2 of 3 · Gap: environmental health", or on a lab surface
   "Covered by Ana, Ben · Gap: environmental health". Tapping it opens the
   slot list with each slot's source sentence reference ("from the call's
   eligibility section") and coverage.
9. Three feedback controls, stored append-only in `SlotFeedback`:
   "this isn't a requirement", "we do cover this", "you missed one" (free
   text). This is the labelled set CN-08 measures slot precision with.
10. "Find collaborators" is **not** shown yet. It appears in CN-06, behind
    `COLLAB_SEARCH_ENABLED`.

## Q3

11. `coverage.for_call(lab, call)` returns every slot with who covers it and
    how; the proof query. Its test uses a fixture lab and a fixture call with
    one covered, one lab-covered, and one gap slot.

## Steps

12. `apps/collab` app (coverage, `SlotFeedback`, migrations).
13. Slot extraction in `extract.py`, prompt bump, backfill.
14. Coverage and the `team_fit` signal at scoring time.
15. `team_gap.py` onto slots.
16. The card line and the feedback controls
    (`components/portal/collab/team-fit-line.tsx`, mounted by the feed cards
    through `opportunity-bits.tsx`), `lib/portal/collab/`.
17. Q3; changelog; repo map; `docs/api-contract.md`.

## Acceptance

- A call that states no requirement shows no line, not "0 of 0".
- A lab-mate is never named for a slot on the strength of a demonstrated or
  conversational edge.
- A project's slots never produce a `global` concept.
- `team_gap` alerts are unchanged on the frozen fixture set, apart from the
  cases the slot change is meant to fix, which are listed in the changelog.

## Open decisions

- **OD-CN03a** Coverage cosine default. Recommendation: 0.80, measured against
  "we do cover this" feedback in CN-08.
- **OD-CN03b** Whether the line shows on personal cards for people with no lab.
  Recommendation: yes; "covered by you" alone is still useful.

## Sandbox validation (before moving on)

Extends the harness with **planted calls**: for each fake funding call, the
spec fixes its required expertise (one to four slots, some matching a lab's
declared methods, some matching nobody in that lab, some roles that are not
facets), and the local model writes the call text from it.

- **Slot extraction** against the planted slots: precision and recall of
  slots by facet; `role` slots never matched. Bars pre-registered.
- **Coverage** against the planted labs: every (lab, call) pair's
  covered-by-you / covered-by-lab / gap marking checked against the declared
  profiles. Accuracy ≥ 0.95; a lab-mate named on demonstrated or
  conversational evidence is an invariant (must be zero).
- **Q3** for every lab and call.
- **Scale:** the team-fit signal computed for every (target, call) pair the
  nightly scoring would touch — 240 people, 48 labs, 200 calls — with the
  wall-clock cost of the extra step recorded.
- **Invariants:** no project-derived concept is global; `team_gap` alerts on
  a frozen set match the pre-change output except the listed fixes.

## Discussion gate

No step in this plan is implemented until the implementing agent has presented,
and the owner has approved, a short design brief: the files and models it will
touch, every migration, every prompt and what happens when the model is
unavailable, every default value and setting name, and what is deliberately not
being done. A deviation discovered mid-implementation stops the work and reopens
the brief.
