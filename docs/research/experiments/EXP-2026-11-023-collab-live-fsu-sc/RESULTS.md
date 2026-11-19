# EXP-2026-11-023 — Results

**Status: complete. The maintainer's ratings are in (Amendment 1, 2026-11-19):
49 of 50 suggested pairs rated "would contact", 1 "maybe", 0 "no".** Sections
1–8 were written before the ratings and are left as they were. Everything below is a count from one run (n=1), on a copy of the live
database, with the in-process changes listed in PROTOCOL.md.

## 1. Headline

Searched as the product reads a typed question (arm `product`), **7 of 14**
faculty got no suggestion at all, because the slot reader returned no slots for
their question; the other 7 got 1–3 people each (10 in total). With slots built
mechanically from each person's research areas (arm `manual`, Deviation 1), 12
of 14 got 1–4 people (32 in total); one got nobody because no one else in the
department publishes in their field, and one had all 7 shortlisted people
dropped by the model. The rating sheet has 52 rows (34 shown by the product
with the model, 18 that only the no-model order would have shown) for 13 of 14
seekers.

## 2. Results table

From `logs/search_anon.json` and `logs/works_anon.json` by `code/analyse.py`
(`tables/summary.md`). Works: imported (read with an abstract). Gaps: slots the
seeker does not already cover; only those reach the bridge lanes.

<!-- BEGIN GENERATED TABLE -->
| Seeker | Works (read) | Product arm: slots / gaps / shown | Manual arm: slots / gaps / shortlisted / shown | Rating rows (shown) | Excluded: lab-mate / co-author |
|---|---|---|---|---|---|
| F01 | 50 (34) | 0 / 0 / 0 | 18 / 2 / 6 / 3 | 5 (3) | 0 / 1 |
| F02 | 50 (33) | 0 / 0 / 0 | 16 / 0 / 8 / 3 | 3 (3) | 0 / 1 |
| F03 | 50 (30) | 6 / 0 / 2 | 16 / 0 / 8 / 2 | 3 (2) | 4 / 1 |
| F04 | 43 (29) | 0 / 0 / 0 | 16 / 0 / 5 / 3 | 4 (3) | 1 / 1 |
| F05 | 50 (37) | 3 / 0 / 1 | 18 / 0 / 8 / 2 | 4 (2) | 1 / 0 |
| F06 | 50 (44) | 0 / 0 / 0 | 18 / 0 / 3 / 2 | 3 (2) | 0 / 0 |
| F07 | 50 (40) | 0 / 0 / 0 | 14 / 0 / 4 / 3 | 3 (3) | 0 / 0 |
| F08 | 31 (20) | 6 / 0 / 1 | 18 / 0 / 8 / 3 | 4 (4) | 0 / 0 |
| F09 | 25 (21) | 0 / 0 / 0 | 14 / 0 / 0 / 0 | 0 (0) | 0 / 0 |
| F10 | 26 (13) | 6 / 0 / 3 | 20 / 0 / 8 / 3 | 5 (4) | 3 / 0 |
| F11 | 50 (27) | 0 / 0 / 0 | 14 / 4 / 7 / 0 | 4 (0) | 1 / 0 |
| F12 | 50 (33) | 6 / 0 / 1 | 16 / 0 / 8 / 3 | 5 (3) | 0 / 0 |
| F13 | 26 (22) | 6 / 0 / 1 | 16 / 0 / 1 / 1 | 1 (1) | 2 / 0 |
| F14 | 50 (41) | 6 / 1 / 1 | 16 / 2 / 11 / 4 | 8 (4) | 0 / 2 |
<!-- END GENERATED TABLE -->

Pooled (`data/metrics.json`, n=1 run):

| Count | Product arm | Manual arm |
|---|---|---|
| Seekers with no slots read | 7 / 14 | 0 / 14 |
| Seekers with any uncovered slot (bridges can run) | 1 / 14 | 3 / 14 |
| Seekers shown nobody | 7 / 14 | 2 / 14 |
| People shortlisted (all lanes) | 33 | 85 |
| Dropped by the model's rerank | 23 | 39 |
| Shown: in-field / method bridge / problem bridge / resource | 9 / 1 / 0 / 0 | 31 / 1 / 0 / 0 |
| Shown who are students | 0 | 1 |
| Distinct people shown | 7 | 14 |
| Searches the rerank could not explain | 0 | 0 |

Population: 25 people open in the copy (14 faculty and 10 students opted in by
the harness, plus one account that was already open). Papers: 601 faculty works
imported (all 14 faculty), 424 read into facets, 177 thin (mostly no abstract);
4 of 10 students imported (17 works). Across all 14 seekers the gate excluded
12 lab-mate pairs and 6 co-author pairs.

## 3. Figures

None.

## 4. Interpretation

Nothing about usefulness can be said before the ratings. What the counts already
show about the product as it stands:

- **The typed-question path fails half the time on this model.** The slot reader
  is a funding-call reader; given "who should I collaborate with on …" it
  returned an empty list for 7 of 14 people, consistently on a second read. In
  the app, those people would see an empty result with no explanation. This is
  a defect independent of the rating.
- **Asking about one's own research reaches only the in-field lane.** Nearly
  every slot built from a person's own areas is one they already cover, and
  covered slots feed only the in-field lane; only 3 of 14 seekers had any
  uncovered slot, and the bridges showed 1 person in total (the same person in
  both arms, matched on a declared interest, not a paper). The suggestions here are therefore "people in your own
  field you do not already publish with", not the cross-field matches the
  design emphasises. A query about something the person does *not* do would
  exercise the bridges; none was asked.
- **The rerank did real work.** It dropped 39 of 85 shortlisted people in the
  manual arm, all 7 for one seeker; on reading the private log, those 7 matched
  the slot at cosine ≥ 0.70 on sentences about unrelated topics. Whether its
  drops were right is part of what the ratings measure (the 18 model-dropped
  rows on the sheet).
- **Structural expectations held:** no student without imported papers and not
  the already-open account (declared profile only) appeared in any shortlist;
  lab-mates and co-authors never did.

## 5. Threats to validity

- **One rater, not blind, judging on others' behalf.** The maintainer knows
  everyone and the department's existing collaborations; "would F0x contact
  this person?" is the rater's guess about F0x, not F0x's answer.
- **Author records.** Two faculty records are conflated with other authors of
  the same name and were imported as they are (ISSUES.md); some suggestions to
  and from those two may rest on papers that are not theirs. 6 of 10 students
  have no papers in the copy, so students are barely represented as candidates.
- **The 50 most-cited works** are what the product imports; for long careers
  that is old work, which the in-field lane's recency weight discounts but does
  not remove.
- **The manual arm is not a product path.** Its slots skip the slot reader and
  give every area both facets; it shows what the matcher does with reasonable
  slots, not what a user typing a question gets.
- **Opt-in is simulated.** Everyone was opted in; in live use the open set
  would be smaller and self-selected.
- **Appearance cap raised.** In live use the cap could hide some people from
  later seekers.
- **One run, temperature 0.2, shared server.** The slot reader, the paper
  facets and the rerank are model outputs and would differ somewhat on a rerun.

## 6. What surprised us

That the product path returned nothing for half the department: the reader that
works for funding calls (EXP-2026-09-006) refuses a plain question about one's
own research on this model. And that a department of 25 open people yields only
in-field suggestions when people ask about their own work.

## 7. Follow-ups

Not copied into `../../OPEN_QUESTIONS.md` by this agent (another agent owns that
file tonight); the coordinator should copy them:

- The slot reader returns no slots for a typed question in 7 of 14 real cases:
  give typed text its own prompt (a need, not a call) or fall back to the text
  itself as a problem slot when the reader returns nothing.
- Self-queries reach only the in-field lane: decide whether "collaborate with me
  on my research" should search gaps the person names, or say plainly that the
  result is in-field only.
- Rate the sheet (the maintainer), then amend this file with the would-contact
  rates per arm and lane, and for model-dropped rows.
- Re-run once the two conflated author records are confirmed or replaced, and
  with the students' papers where a record can be confirmed.

## 8. Reproduction

```bash
# copy (once), then, with PRIVATE_DIR (people.json) and FROZEN (git archive of 181ca3c4):
docs/research/experiments/EXP-2026-11-023-collab-live-fsu-sc/code/drive.sh check
docs/research/experiments/EXP-2026-11-023-collab-live-fsu-sc/code/drive.sh prepare
docs/research/experiments/EXP-2026-11-023-collab-live-fsu-sc/code/drive.sh search --arm product
docs/research/experiments/EXP-2026-11-023-collab-live-fsu-sc/code/drive.sh search --arm manual
docs/research/experiments/EXP-2026-11-023-collab-live-fsu-sc/code/drive.sh export
python3 docs/research/experiments/EXP-2026-11-023-collab-live-fsu-sc/code/analyse.py
```

The private inputs (`people.json`: anonymous id → person, stand-in emails,
OpenAlex ids) and outputs (`raw/`, `ratings_input.json`) are with the
maintainer, outside the repository.

## AMENDMENTS

A completed experiment is immutable. Corrections are appended here, dated, never
edited into the sections above.

### Amendment 1 — the maintainer's ratings (2026-11-19, post hoc)

**What was rated.** The maintainer, who knows every person, rated each row of
the private rating sheet on 2026-11-19 (01:48–01:53 UTC): "would this professor
plausibly reach out to this person about this?" (would contact / maybe / no),
plus a "not their work" box, an optional note per row, an optional "who is
missing" note per professor and one overall note. The ratings were read from the
rating page's store, joined to the sheet by anonymous id, and scored by
`code/score_ratings.py`; `data/ratings_anon.json` keeps only ids, flags and the
rating (no names, no note text). The analysis is post hoc: no rating measure or
threshold was registered for this experiment beyond EXP-2026-09-012's
yes/maybe/no question.

**Unit.** A seeker–candidate pair. The sheet had 52 rows; two people appeared
twice for the same seeker (once per lane), and the page stored one rating per
pair, so the unit is 50 pairs (ISSUES.md). All 50 were rated.

<!-- BEGIN GENERATED TABLE: tables/ratings.md -->
| Pairs | n | Would contact | Maybe | No | Would contact, rate (Wilson 95%) |
|---|---:|---:|---:|---:|---|
| all pairs | 50 | 49 | 1 | 0 | 0.98 (0.895–0.9965) |
| shown with the model (either arm) | 34 | 33 | 1 | 0 | 0.9706 (0.8508–0.9948) |
| dropped by the model only | 16 | 16 | 0 | 0 | 1.0 (0.8064–1.0) |
| shown, product arm | 10 | 10 | 0 | 0 | 1.0 (0.7225–1.0) |
| shown, manual arm | 32 | 31 | 1 | 0 | 0.9688 (0.8426–0.9945) |
| includes a bridge-lane row | 4 | 4 | 0 | 0 | 1.0 (0.5101–1.0) |
| candidate is a student | 1 | 1 | 0 | 0 | 1.0 (0.2065–1.0) |
<!-- END GENERATED TABLE -->

"Not their work" was ticked for no pair, including those touching the two
conflated author records. 12 of the 13 seekers with suggestions had every pair
rated "would contact"; the one "maybe" is a pair the product showed.

**The rater's notes (paraphrased, no names).**

- On one "would contact" pair: the match fits the candidate's *earlier* work,
  not what they do now. This is the "50 most-cited works" threat in section 5
  showing up in a rating.
- On another: the two people's research is more closely related than most
  pairs on the sheet.
- For the one professor with no suggestions: no other faculty member works in
  that field, so nobody was the right answer; some students would match, but
  none of them had imported papers.
- Overall: most if not all suggestions fit "would contact"; many of the people
  suggested are related to one another; the matching of interests is good. The
  rater expects the same matching to help fill a missing piece of expertise
  for a grant team. That use was not tested here.
- The rater reported that the page "glitched". The only defect found in the
  page is the shared rating for a person on two rows (ISSUES.md).

**Interpretation.**

- **The suggestions are ones the rater judges real.** On this department,
  every suggestion the product showed was rated "would contact" except one
  "maybe" (33/34, Wilson 0.85–0.99). The typed-question path's 10 suggestions
  were all "would contact". That path still found nobody for 7 of 14
  (section 1), so its coverage problem stands.
- **The test cannot tell the matcher from the department.** The 16 pairs that
  only the no-model order would have shown (the model's rerank dropped them)
  were also all "would contact". So the rerank removed nobody the rater would
  not contact, and its drops cost suggestions rather than removed bad ones. In
  a 14-person department whose faculty all work in computational science, most
  pairs may be plausible. No pair outside the matcher's output (for example, a
  random colleague) was rated, so there is no base rate. The 98% says the
  suggestions are plausible, not that the matcher picks them out better than
  chance would.
- **This is in-field matching only** (section 4): the suggestions are people in
  one's own field one does not already publish with. The cross-field bridges
  were barely exercised (4 pairs).
- **One rater, not blind, rating on others' behalf** (section 5). The rater saw
  which rows the model hid.

**What the paper can say.** On the 14 faculty of one real department, with
their papers imported, the people the matcher suggests are ones the rater
judges the professor would contact (49 of 50 pairs, the rest "maybe"). The
paper must also say: one rater, no comparison with random colleagues, in-field
suggestions only, and the typed-question path found nobody for half of them.
No names or other identifying details.

**Follow-ups** (copied to `../../OPEN_QUESTIONS.md` as Q-099 to Q-101): the
typed-question slot reader (section 7), self-queries reaching only the in-field
lane (section 7), and a random-colleague control rated blind so the would-contact
rate has a base rate.
