# EXP-2026-11-025 — Results

**Status: complete.** One run (n=1), 14 seekers, on EXP-2026-11-024's copy
(`mycelium_sandbox_fsusc24`), relay `default-model` (self-report "trained by
Google", 19:13Z and 19:15Z). Nothing in this run was rated.

## 1. Headline

With one `problem` slot per listed topic (`77166b9e`), **12 of 14** faculty get
at least one suggestion from their typed question, against **11 of 14** with
the previous prompt (`2cc179d9`) run again on the same copy minutes earlier. H1
and H2 held. Of the two still shown nobody, one has nobody in their field in
the department; the other had all 6 shortlisted people dropped by the rerank.

## 2. Results table

From `logs/search_{prev,multi}_anon.json` and EXP-2026-11-024's
`logs/search_after_anon.json`, by `code/analyse.py` (`tables/summary.md`).

<!-- BEGIN GENERATED TABLE -->
| Seeker | 024 after: shown | Prev: problem slots / in-field shortlist / dropped / shown | Multi: problem slots / in-field shortlist / dropped / shown |
|---|---|---|---|
| F01 | 3 | 6 / 3 / 0 / 3 | 6 / 3 / 0 / 3 |
| F02 | 3 | 6 / 3 / 0 / 3 | 6 / 3 / 0 / 3 |
| F03 | 1 | 4 / 8 / 7 / 1 | 3 / 8 / 7 / 1 |
| F04 | 1 | 4 / 1 / 0 / 1 | 4 / 1 / 0 / 1 |
| F05 | 3 | 4 / 6 / 2 / 3 | 5 / 8 / 4 / 3 |
| F06 | 1 | 5 / 2 / 1 / 1 | 5 / 2 / 1 / 1 |
| F07 | 0 | 1 / 1 / 1 / 0 | 4 / 2 / 0 / 2 |
| F08 | 3 | 6 / 8 / 3 / 3 | 6 / 8 / 3 / 3 |
| F09 | 0 | 6 / 1 / 1 / 0 | 6 / 1 / 1 / 0 |
| F10 | 3 | 6 / 7 / 4 / 3 | 6 / 7 / 4 / 3 |
| F11 | 0 | 2 / 0 / 0 / 0 | 6 / 6 / 6 / 0 |
| F12 | 1 | 1 / 2 / 1 / 1 | 2 / 3 / 0 / 3 |
| F13 | 1 | 3 / 1 / 0 / 1 | 6 / 1 / 0 / 1 |
| F14 | 1 | 3 / 2 / 1 / 1 | 3 / 2 / 1 / 1 |
<!-- END GENERATED TABLE -->

Pooled (`data/metrics.json`, n=1 run, 14 seekers):

| Count | 024 `after` | `prev` (`2cc179d9`) | `multi` (`77166b9e`) |
|---|---|---|---|
| **Seekers with at least one suggestion** | **11** | **11** | **12** |
| `problem` slots (of 84) | – | 57 | 68 |
| Seekers with a single `problem` slot | – | 2 | 0 |
| In-field shortlisted | – | 45 | 55 |
| Dropped by the rerank | 23 | 21 | 27 |
| Seekers whose whole shortlist was dropped | 3 | 2 | 2 |
| Seekers with an empty shortlist | 0 | 1 | 0 |
| Shown (all in-field) | 21 | 21 | 25 |
| Distinct people shown | 13 | 13 | 15 |
| Searches with zero slots / `no_topic` / fallback / unexplained | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |

`prev` reproduced EXP-2026-11-024's `after` arm seeker for seeker (the same
shown count for all 14), though F11's shortlist differed (method bridge 2 then,
none now).

**Exploratory, against EXP-2026-11-023's ratings** (anonymous ids; rated there,
not here): of `multi`'s 25 shown pairs, 19 were rated in 023, all "would
contact"; 6 are unrated. Of the 6 people the rerank dropped for F11, 3 were
rated in 023, all "would contact" (and dropped by the rerank there too); 3 are
unrated.

## 3. Figures

None.

## 4. Interpretation

- **The prompt change helps where the old one bit.** "At most one problem" was
  mostly ignored by this model (57 of 84 slots were already problems), but for
  the two seekers it held to it, F07 and F12, the in-field lane had one problem
  to search with. With their topics as problems, F07 went from nobody to 2
  people and F12 from 1 to 3. Nobody lost a suggestion.
- **What remains is not retrieval.** F09: one person shortlisted, dropped;
  EXP-2026-11-023's rater said nobody else in the department works in that
  field, so an empty answer is right. F11: 6 shortlisted, all 6 dropped by the
  rerank; the 3 of them that 023 rated were all "would contact". On this one
  seeker the rerank removes people a knowledgeable rater would contact, as it
  did in 023 (all 7 dropped then).
- **Why the rerank was not changed.** Showing what the rerank dropped, or
  saying that someone matched but was judged unsuitable, would tell a seeker
  that someone open to collaboration matched, which the product never says.
  Loosening the rerank needs a base rate (Q-101): in 023 every pair, dropped or
  shown, was rated plausible, so one seeker's three ratings cannot show the
  rerank is wrong in general.

## 5. Threats to validity

- **One run, temperature 0.2.** A gain of one seeker (11 → 12) is within what a
  re-draw could move; `prev` did reproduce 024 exactly, which is some evidence
  the counts are stable on this copy.
- **Same copy, same questions** as EXP-2026-11-024; the change was designed
  after seeing that experiment's three empty seekers, so this is a check of a
  targeted fix, not a held-out test.
- **The model's name is a self-report** ("trained by Google").
- **Questions about one's own research only** (Q-100).

## 6. What surprised us

That the old prompt's "At most one" was ignored for 12 of 14 seekers, and that
more problem slots gave F11 a shortlist only for the rerank to drop all of it.

## 7. Follow-ups

Q-102 narrowed in `../../OPEN_QUESTIONS.md`: the retrieval half is fixed; what
remains is whether the rerank is too strict for a seeker like F11, which waits
on a base rate (Q-101).

## 8. Reproduction

```bash
D=docs/research/experiments/EXP-2026-11-025-collab-self-query-problem-slots/code/drive.sh
FROZEN=<2cc179d9> $D identity
FROZEN=<2cc179d9> $D search --arm prev
FROZEN=<77166b9e> $D search --arm multi
FROZEN=<77166b9e> $D identity
python3 docs/research/experiments/EXP-2026-11-025-collab-self-query-problem-slots/code/analyse.py
```

Needs EXP-2026-11-024's prepared copy `mycelium_sandbox_fsusc24` (its
PROTOCOL.md, Procedure). Private outputs are in `<private>/exp025/`.

## AMENDMENTS

A completed experiment is immutable. Corrections are appended here, dated, never
edited into the sections above.
