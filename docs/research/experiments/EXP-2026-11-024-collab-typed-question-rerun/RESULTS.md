# EXP-2026-11-024 — Results

**Status: complete.** One run (n=1), 14 seekers, on a new copy of the live
database (`mycelium_sandbox_fsusc24`, 2026-11-19), relay `default-model`
(self-report "trained by Google", 18:48Z and 19:06Z). Nothing in this run was
rated.

## 1. Headline

After the fix, **11 of 14** faculty get at least one suggestion from their
typed question, against **7 of 14** with the code before the fix on the same
copy, the same 7 of 14 EXP-2026-11-023 recorded. Every search now runs with
slots (H1 held: 14 of 14 read by the new prompt, no fallback needed, no
`no_topic`). The three still shown nobody did search; the rerank dropped the
1–2 people each had shortlisted.

## 2. Results table

From `logs/search_{before,after}_anon.json`, `logs/works_anon.json` and
EXP-2026-11-023's `logs/search_anon.json`, by `code/analyse.py`
(`tables/summary.md`). Works: imported (read with an abstract). Source: where
the slots came from. Gaps: slots the seeker does not already cover.

<!-- BEGIN GENERATED TABLE -->
| Seeker | Works (read) | 023 product: slots / shown | Before: slots / source / shown | After: slots / source / gaps / shown |
|---|---|---|---|---|
| F01 | 50 (34) | 0 / 0 | 0 / none / 0 | 6 / reader / 0 / 3 |
| F02 | 50 (33) | 0 / 0 | 0 / none / 0 | 6 / reader / 0 / 3 |
| F03 | 50 (30) | 6 / 2 | 6 / reader / 2 | 6 / reader / 0 / 1 |
| F04 | 43 (29) | 0 / 0 | 0 / none / 0 | 6 / reader / 0 / 1 |
| F05 | 50 (37) | 3 / 1 | 6 / reader / 3 | 6 / reader / 0 / 3 |
| F06 | 50 (44) | 0 / 0 | 0 / none / 0 | 6 / reader / 0 / 1 |
| F07 | 50 (40) | 0 / 0 | 0 / none / 0 | 6 / reader / 0 / 0 |
| F08 | 31 (20) | 6 / 1 | 6 / reader / 1 | 6 / reader / 0 / 3 |
| F09 | 25 (21) | 0 / 0 | 0 / none / 0 | 6 / reader / 0 / 0 |
| F10 | 26 (13) | 6 / 3 | 6 / reader / 3 | 6 / reader / 0 / 3 |
| F11 | 50 (27) | 0 / 0 | 0 / none / 0 | 6 / reader / 2 / 0 |
| F12 | 50 (33) | 6 / 1 | 6 / reader / 1 | 6 / reader / 0 / 1 |
| F13 | 26 (22) | 6 / 1 | 6 / reader / 1 | 6 / reader / 0 / 1 |
| F14 | 50 (41) | 6 / 1 | 6 / reader / 1 | 6 / reader / 0 / 1 |
<!-- END GENERATED TABLE -->

Pooled (`data/metrics.json`, n=1 run, 14 seekers):

| Count | 023 product arm | Before (`b45c1211`) | After (`2cc179d9`) |
|---|---|---|---|
| **Seekers with at least one suggestion** | **7 / 14** | **7 / 14** | **11 / 14** |
| Searches run with zero slots | 7 | 7 | 0 |
| Slots from the reader / the fallback / none | 7 / – / 7 | 7 / – / 7 | 14 / 0 / 0 |
| Refused `no_topic` | – | – | 0 |
| Seekers with any uncovered slot | 1 | 1 | 1 |
| Shortlisted (all lanes) | 33 | 33 | 47 |
| Dropped by the rerank | 23 | 20 | 23 |
| Shown: total (in-field / method bridge) | 10 (9 / 1) | 12 (11 / 1) | 21 (21 / 0) |
| Distinct people shown | 7 | 8 | 13 |
| Students shown | 0 | 1 | 2 |
| Unexplained searches / retries | 0 / 0 | 0 / 0 | 0 / 0 |

Of the 4 seekers who gained suggestions (F01, F02, F04, F06), none was shown
anyone before. The paper import matched EXP-2026-11-023 exactly: 601 faculty
works, 424 read, 177 thin; 4 students imported (17 works); 6 co-author pairs.

**Exploratory, against EXP-2026-11-023's ratings** (joined by anonymous id; the
pairs were rated there, not here): of the `after` arm's 21 shown (seeker,
candidate) pairs, 16 were on 023's rating sheet, all 16 rated "would contact";
5 are new pairs, unrated. Of the `before` arm's 12, 10 were rated, all "would
contact".

## 3. Figures

None.

## 4. Interpretation

- **The fix does what it is for.** The empty-slots failure is gone: the prompt
  written for a person's words read slots from all 14 questions, where the
  call prompt read none from 7 (the same 7 on 2026-11-18 and today, so it is a
  steady property of that prompt on this model, not noise). The fallback and
  the `no_topic` message were never reached here; they exist for questions
  without a nameable topic and for an unreachable model, and are covered by
  tests, not by this run.
- **4 more people get suggestions (7 → 11 of 14).** The suggestions remain
  in-field only: 1 of 14 seekers had an uncovered slot, as in 023 (Q-100).
- **The rest of the gap is the rerank, not the reader.** F07, F09 and F11
  searched with 6 slots each, and each had 1–2 people shortlisted, all dropped
  by the model. In 023's manual arm (one problem and one method slot per area,
  14–20 slots) F07 got 3 people, and F11 had all 7 of its shortlist dropped
  then too. F09 got nobody in either; 023's rater said nobody in the department
  works in that field. The new reader gives at most one or a few `problem`
  slots, and only covered `problem` slots feed the in-field lane, so a
  self-query's shortlist is short; one model drop then empties it.
- **Pairs the product now shows are ones already judged plausible.** 16 of 21
  were rated "would contact" in 023. That is a different copy and a different
  day, and 023 has no base rate (Q-101), so this only says the new suggestions
  are not a different kind of suggestion.

## 5. Threats to validity

- **One run, temperature 0.2.** Slot reading, facet reading and the rerank are
  model outputs. The 7 failures before the fix recurred exactly, but the 11 after
  it are one draw.
- **The model's name is a self-report** ("trained by Google", as in 023); the
  maintainer did not state the model for this run (ISSUES.md).
- **A new copy.** The papers and facets were re-read; the counts matched 023
  exactly, but individual facets and vectors may differ, so per-seeker shown
  counts are compared within this run (`before` vs `after`), not with 023.
- **Not a product test of the message.** The `no_topic` refusal and the panel's
  error line were tested by unit tests only.
- **One query per person, about their own research** (023's design); questions
  about something the person does not do were not asked.

## 6. What surprised us

That the new prompt never needed the fallback: a question naming a topic was
read every time once the prompt said a question counts. Also that F09's six
slots were all `problem`, despite the prompt asking for at most one; the
validator does not enforce that, and here it did no harm.

## 7. Follow-ups

Copied to `../../OPEN_QUESTIONS.md`:

- Q-099 answered (this experiment).
- New (Q-102): when a lane's whole shortlist is dropped by the rerank, the
  person sees nobody (3 of 14 here). Show the retrieval order with a note
  that the model doubted it, show a "nobody suitable" sentence instead of an
  empty list, or widen a self-query's in-field slots (each named area as a
  problem slot).

## 8. Reproduction

```bash
# copy the live database to mycelium_sandbox_fsusc24 (PROTOCOL.md), then with
# PRIVATE_DIR (people.json) and each frozen tree (git archive + COMMIT):
D=docs/research/experiments/EXP-2026-11-024-collab-typed-question-rerun/code/drive.sh
FROZEN=<2cc179d9> $D check; FROZEN=<2cc179d9> $D identity
FROZEN=<2cc179d9> $D prepare; FROZEN=<2cc179d9> $D works
FROZEN=<b45c1211> $D search --arm before
FROZEN=<2cc179d9> $D search --arm after
FROZEN=<2cc179d9> $D identity
python3 docs/research/experiments/EXP-2026-11-024-collab-typed-question-rerun/code/analyse.py
```

Private outputs (slot texts, names, raw searches) are in `<private>/exp024/`,
with the maintainer, outside the repository.

## AMENDMENTS

A completed experiment is immutable. Corrections are appended here, dated, never
edited into the sections above.
