# EXP-2026-09-012 — Protocol

Written 2026-09-18, before any live collaborator search has run (search is
off: `COLLAB_SEARCH_ENABLED=false`). Registered now so the live measures are
fixed before there is any data to fit them to (plan CN-08 step 8).

The sandbox runs (EXP-2026-09-005 to -011) are this experiment's first
evidence: they show the machinery does what it says against planted truth.
They cannot say whether a real researcher finds a result worth contacting;
this protocol is for that.

## Measures and bars

Each measure is computed by `collab_evaluation` / `apps.collab.evaluation`
or by the named query, over a window stated in the result.

1. **Slot quality (CN-03).** Precision proxy: 1 − (distinct slots marked "not
   a requirement") / (slots shown on calls that received any slot feedback).
   Recall proxy: "missed one" notes per call with feedback. Plus a
   hand-labelled sample of 50 real calls (two readers, disagreements
   resolved) scored as in EXP-2026-09-006. **Bar:** hand-labelled precision
   ≥ 0.80 before outward search is switched on.
2. **Coverage accuracy (CN-03).** Share of gap slots corrected "we do cover
   this". Tunes `COLLAB_COVERAGE_COSINE` (Q-044). No bar; reported with the
   threshold in force.
3. **Concept linking (CN-01).** Merge precision on 200 sampled merged pairs
   (hand-judged "same idea") and split rate on 200 sampled concept pairs above
   0.85 cosine that were *not* merged. Shared with ambient-profile Plan 10 —
   one folder, both series cite it. EXP-2026-09-005's threshold sweep is the
   first data point (Q-042).
4. **In-field lane — likely collaborations.** Hide co-authorships formed after
   a cutoff (from `AuthorWork` co-author ids among Mycelium users); run the
   in-field lane as of the cutoff *without* the co-author exclusion for the
   hidden pairs; report recall@3 of hidden pairs. Its weakness (design §12) is
   stated with the result: it rewards collaborations that would have happened
   anyway.
5. **Bridge and resource lanes — valuable unlikely ones.** Opt-in human
   judgment by seekers on their own projects and calls: per result, "would you
   contact this person?" (yes / maybe / no). Expectation (design §15):
   spontaneous materialisation is 0.06–0.5%, so the measure is intent to
   contact, not collaboration. Reported per lane with the n of judgments.
6. **Concentration.** Appearances per person per week: Gini, share of
   person-weeks at the cap, and opt-out rate within 14 days of a week at half
   the cap or more.
7. **Harm checks** (all must be zero, daily, from the collab task's log):
   untraceable evidence, outside audience ∩ scope, a candidate told, a
   private concept made global, shown while off, not from the shortlist.

## Scope widening (plan CN-07 step 1)

Search widens from institution to country, then anywhere, only when
`evaluation.readiness()` reports ready over 28 days: ≥ 100 rated results,
not-relevant rate ≤ 0.5, ≤ 5% of person-weeks at the cap, and every harm
check zero. Widening is a deliberate change to `COLLAB_MAX_SCOPE`, recorded
in `docs/research/DECISIONS.md` with the readiness report attached.

## What would falsify the series' claim

Any harm check non-zero in live use; hand-labelled slot precision below 0.80;
a bridge lane whose "would contact" rate is not above the in-field lane's.
