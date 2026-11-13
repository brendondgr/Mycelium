# EXP-2026-11-013 — Results

Generated 2026-11-12/13. Numbers that need no people are read from
`data/metrics.json` (arm a `main`, arm b, injected errors),
`data/metrics_rep2.json` / `data/metrics_rep3.json` (validation repetitions of
arm a) and `data/inject_<run>_summary.json`. **The human-judged half (C-033,
C-034 and C-035's precision) is not measured yet: the rating sheets are
ready in `data/sheets/` and waiting for raters.**

## 1. Headline

Without people: Mylo (arm a) answered all 50 questions, at a mean of 27.1k
tokens and 40.5 s per answer (median 36.7 s, worst 150.6 s), against 9.6k
tokens and 18.8 s for the single retrieve-then-answer call (arm b). The
answer verifier triggered its repair on 1 answer in 50 in each repetition. On
660 rule-built corrupted copies of 49 clean answers it caught every invented
citation number (108/108) and nearly every invented amount or figure
(104/113), caught dates, authors and venues **only when written as a
`Label: value` line** (53/58, 43/51, 30/49) and **never in running prose**
(0/49 each), and caught **none** of 60 unsupported paraphrases — as predicted
before the run. It raised no false alarm on the 49 originals. The same
injection on the two validation repetitions (1,988 copies of 147 answers in
all) gives the same pattern: 328/328 citation numbers, 0/180 paraphrases,
0/147 per class for dates, authors and venues in prose, no false alarm.

## 2. Results table

Arms (50 questions each; `main` run):

| Category | Arm a mean s | Arm a mean tokens | Arm b mean s | Arm b mean tokens |
|---|---:|---:|---:|---:|
| tagged paper | 20.2 | 11,900 | 18.6 | 10,966 |
| tagged grant / fellowship | 16.2 | 11,379 | 12.0 | 8,312 |
| feed vs project | 43.2 | 27,540 | 28.7 | 9,335 |
| project status | 47.3 | 35,778 | 21.1 | 10,204 |
| who in the lab fits | 39.1 | 21,628 | 16.0 | 8,760 |
| compound | 69.6 | 48,859 | 16.7 | 9,849 |
| **all** | **40.5** | **27,088** | **18.8** | **9,582** |

Arm (a) across repetitions (validation; only `main` is rated):

| Run | Answers | Mean tokens | Mean s | Max s | Model calls (mean) | Out of steps | Thrash stop | Repairs | Stripped |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| main | 50 | 27,088 | 40.5 | 150.6 | 6.46 | 1 | 4 | 1 | 1 |
| rep2 | 50 | 27,025 | 34.7 | 124.4 | 6.12 | 0 | 1 | 1 | 0 |
| rep3 | 50 | 26,494 | 37.2 | 104.2 | 6.16 | 0 | 2 | 1 | 1 |

In rep2 one answer (`to03`) was a clarifying question back to the asker
(thread left waiting), not an answer.

Injected errors (one per copy, Wilson 95% intervals):

| Class | Copies | Caught | Recall | 95% CI | in place | added in prose | added as a fact line |
|---|---:|---:|---:|---|---|---|---|
| citation number not in the thread | 108 | 108 | 1.00 | 0.97–1.00 | 103/103 | 5/5 | — |
| citation moved to an unread reference | 0 | — | — | — | — | — | — |
| date / year | 168 | 54 | 0.32 | 0.26–0.40 | 1/61 | 0/49 | 53/58 |
| author surname | 109 | 43 | 0.39 | 0.31–0.49 | 0/9 | 0/49 | 43/51 |
| venue | 102 | 30 | 0.29 | 0.21–0.39 | 0/4 | 0/49 | 30/49 |
| amount / figure | 113 | 104 | 0.92 | 0.86–0.96 | 6/15 | 49/49 | 49/49 |
| unsupported paraphrase | 60 | 0 | 0.00 | 0.00–0.06 | 0/60 | — | — |

Repair (`data/repair_off_<tag>.json`; one repaired answer per run):

| Run | Flagged in the judged draft | Repair outcome | Repair cost | With repair off |
|---|---|---|---|---|
| main | `1.5` in "€1.5–15M" | failed; the figure was stripped | unknown (counter bug) | the same figure stripped |
| rep2 | `2.5` in "about 2.5 months out" | passed; the model dropped the figure | 19,104 tokens, 10.6 s, 2 calls | the sentence's figure stripped |
| rep3 | `1.5` in "€1.5–15M" | failed; the figure was stripped | 20,078 tokens, 16.2 s, 2 calls | the same figure stripped |

On the implementing agent's reading (not a rater's), two of the three flags
are false: the evidence says "€1,500,000–€15,000,000", and the verifier's
literal match does not accept "€1.5–15M" for it, so a correct amount was
removed after a repair the model could not satisfy. The third flags a figure
the model computed itself ("about 2.5 months" to a deadline 84 days away),
which the evidence does not state. The raters' removed-item sheet will judge
the `main` item.

Human-judged (C-033, C-034, C-035 precision and recall against raters): **not
yet measured** — `code/score.py` is written and committed; it runs when the
filled sheets are copied to `data/ratings/`.

## 3. Figures

None.

## 4. Interpretation

- **The verifier is a citation-and-number checker.** It is reliable for what
  it parses: a citation the thread never surfaced, and a figure (decimal or
  percentage) the evidence lacks. A wrong author, venue or year is caught only
  when the model writes it as a `- Authors:` / `Venue:` / `Year:` line; the
  same wrong detail in a sentence passes. Integers in prose (a year, "$75,000")
  are not figures to it. An unsupported claim with no number in it is
  invisible. So C-035's recall bar (≥ 0.5 of what raters find) depends on what
  kind of unsupported detail the model actually produces — which is exactly
  what the raters' lists will show.
- **The repair rarely runs** (1 in 50 in each of three runs), so its cost per
  answer is small on average; when it runs it adds 19–20k tokens (about 70%
  of a mean answer's 27k) and 11–16 s. Two of its three
  triggers were a reformatted amount ("€1.5–15M" for "€1,500,000–€15,000,000"),
  so its precision may be limited less by judgement than by number
  formatting.
- **Arm (b) is cheaper and faster but structurally blind** to the lab's own
  state: project-status and who-fits questions are answered from the corpus
  alone. Whether people judge it worse is C-034, pending.
- The `unread` check cannot be exercised by single-turn questions (every
  surfaced reference is in view); testing it needs multi-turn threads.

## 5. Threats to validity

- Questions were written by the implementing agent; tagged items were picked
  from the demo lab's highest relevance scores.
- One fictional lab, one model, one corpus snapshot. The demo lab's projects
  are thinly described, which favours short answers.
- Arm (a) ran while the nightly run used the same model server, so its
  seconds are under load (ISSUES.md); tokens are unaffected.
- Injected errors are made by rule; their recall is per error type built, not
  per error the model makes.
- Arm (b) never reaches its token ceiling (20-result search cap).

## AMENDMENTS

Amendment 1 (PROTOCOL.md): question ids made unique, arm (b) told which
records were tagged and rerun, removed-item sheet de-duplicated, validation
repetitions — all before any rating.
