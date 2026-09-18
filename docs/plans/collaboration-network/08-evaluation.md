# Plan CN-08 — Evaluation

**Status:** draft. **Depends on:** CN-03 onward; runs continuously as each
plan ships. **Unblocks:** CN-07's scope widening; tuning of every threshold in
this series.
**Correlation ID:** `20260918-collaboration-network-08`

## Objective

Decide with numbers in the research record whether each part works, choosing
the tests before building (`design §12`). Every run follows
`docs/research/AGENT_INSTRUCTIONS.md`: scaffold with `make new-experiment`,
fill `PROTOCOL.md` first, record failed runs, never quote a metric that is not
in `manifest.yaml` and `RESULTS.md`.

## Measures

1. **Slot quality** (CN-03): precision from "this isn't a requirement",
   recall from "you missed one", on live feedback plus a hand-labelled sample of
   calls. Slot precision gates CN-05: outward search is not switched on while
   slots are poor.
2. **Coverage accuracy** (CN-03): the share of "we do cover this" corrections;
   tunes `COLLAB_COVERAGE_COSINE`.
3. **Concept linking** (CN-01): merge precision on sampled pairs, and split
   rate (the same idea under two concepts). **Shared with ambient-profile
   Plan 10**: one experiment folder, both series cite it, because both depend
   on the same threshold.
4. **In-field lane — predict likely collaborations.** Hide co-authorships after
   a cutoff (from `AuthorWork` co-author ids) and measure whether the in-field
   lane surfaces them, with the weakness `design §12` names stated in the
   results: it rewards collaborations that would have happened anyway.
5. **Bridge and resource lanes — surface valuable unlikely ones.** Human
   judgment from seekers on their own real projects and calls: a short rating
   per result, opt-in. Expectations set by `design §15`: spontaneous
   materialisation is 0.06–0.5%, so the measure is "would you contact this
   person", not "did you collaborate".
6. **Concentration.** The distribution of appearances per candidate (Gini),
   weeks at the cap, and opt-out rate after heavy exposure.
7. **Harm checks** (all must be zero): a conversational or project edge read
   by the matcher; a candidate returned outside the audience ∩ scope
   intersection; any notification or response that tells a candidate they were
   searched for; a concept from project state or conversation in `global`
   scope; a result for a candidate whose setting was off or expired at query
   time; a model-named candidate not in the shortlist.

## Steps

8. Protocols for measures 1–6 registered before CN-05 ships.
9. Instrumentation counters in `run_analytics.py` (searches, lanes returned,
   feedback rates, cap hits) — counts only, no names.
10. The harm checks as a scheduled query with an error report on any non-zero.

## Sandbox validation

The sandbox runs of CN-02 to CN-07 are this plan's first evidence, and the
concept-merge threshold sweep of `EXP-2026-09-005` is the shared concept-merge
experiment's first data point. What the sandbox cannot answer — whether a real
researcher finds a bridge result worth contacting — stays with the human
judgment round on real projects.

## Discussion gate

No step in this plan is implemented until the implementing agent has presented,
and the owner has approved, a short design brief: the files and models it will
touch, every migration, every prompt and what happens when the model is
unavailable, every default value and setting name, and what is deliberately not
being done. A deviation discovered mid-implementation stops the work and reopens
the brief.
