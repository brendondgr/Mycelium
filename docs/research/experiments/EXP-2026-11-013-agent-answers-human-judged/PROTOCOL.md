# EXP-2026-11-013 — Protocol

Written 2026-11-12, before any answer was generated. Tests C-033, C-034, C-035.

## Question

When Mylo answers a PI's question about the lab's field and opportunities, do
people judge the answer correct and its citations supported; is it better than
a single retrieve-then-answer call at the same token budget; and does the
code-level answer verifier (`tools/agent/verify.py`) remove the right things?

## Hypothesis

Stated in CLAIMS.md before generation, thresholds fixed by the maintainer as a
conservative first bar:

- C-033: majority-correct on ≥ 70% of questions; ≥ 85% of citations judged
  supporting.
- C-034: Mylo correct more often than the single-call arm, paired bootstrap 95%
  interval for the difference excluding zero.
- C-035: verifier removal precision ≥ 0.9 and recall ≥ 0.5 against raters'
  lists of unsupported details.

Prediction from reading the code, written down so it cannot be renegotiated:
the verifier's `unsupported` check matches fact *lines* (authors, venue, DOI,
deadline, amount) and figures; a changed detail inside running prose and an
unsupported paraphrase will mostly be missed. `unread` citations trigger the
repair but are never stripped on the final pass.

## Setup

- Agent at the commit recorded in `manifest.yaml`, instance model (Qwen 3.8 27B
  on vLLM, one A100 80GB, via `llm-tunnel:9090` as `default-model`), defaults
  (`max_steps` 25, `result_cap_tokens` 4000, no output cap).
- Runs in a one-off backend container (the tunnel has no host port).
- Asker: the public demo world's PI (fictional), lab scope, `surface="web"`,
  audience `person`. Threads are demo threads (`demo_visitor="EXP-2026-11-013"`):
  no learning pass, removed by the demo's 24-hour cleanup. Nothing is written
  to a real account. Everything raters need is copied into `data/` first.
- No production code is changed. Drafts before repair and verifier verdicts
  are read from `AgentEvent`; timings from a wrapping port.

## Data

- `code/questions.json`: 50 questions fixed before generation. Eight each:
  tagged paper, tagged grant or fellowship, feed against a project, project
  status, who in the lab fits a call; ten compound. Tagged items are real
  corpus items chosen from the demo lab's highest relevance scores on
  2026-11-12. No question names a real person.
- Judgements are **human** (raters), against the evidence the answer's
  producer read. "Cannot tell from the evidence" counts as unsupported.

## Arms

- **(a) Mylo as shipped**, verifier and its single repair on.
- **(b) single call**: one `corpus_search` with the question as the query (20
  results); the tagged items' records first, then search results' full records
  (exactly the text `corpus_item` gives the agent), numbered `#1..k`, added
  until the estimate reaches arm (a)'s mean total tokens minus 1,500; one model
  call, same model and port, no tools, instructed to cite `#n` and to state no
  detail the evidence lacks. Project-status and who-fits questions are answered
  from the corpus only — that is what a retrieve-then-answer call can see, and
  the comparison is meant to show it.
- **(a′) repair off**, computed exactly rather than re-sampled: for every arm
  (a) turn where the repair ran, the text the loop would have posted had the
  repair been disabled is `strip_claims(strip(draft, unmatched), unsupported)`
  applied to the stored first draft and its stored verdict — the loop's own
  give-up path. Paired on the identical draft, so no sampling noise.
  (Deviation from the brief, which asked for a rerun with the repair disabled;
  the loop has no switch for it and a rerun would compare different drafts.)

## Metrics

From the rating sheets (majority label per item, ≥ 2 raters):
- correct rate per arm (yes = 1, partly = 0.5 reported separately, no = 0;
  primary: share majority **yes**);
- citation support rate (share of `#n` citations judged supporting);
- per-arm usefulness 1–5 (mean, median);
- verifier removal precision: of the sentences/details the verifier removed
  (or forced into repair), share raters judged unsupported;
- verifier recall: of the unsupported details raters list in arm (a) drafts,
  share the verifier flagged;
- agreement: Cohen's κ (two raters) or Fleiss' κ (three) per field.

Without people:
- injected-error recall per class (≥ 40 corrupted copies per class, one error
  each): (1) `#n` not in the thread; (2) citation moved to a surfaced but unread
  reference; (3) a changed year/date; (4) a changed author surname; (5) a
  changed venue; (6) a changed amount or figure; (7) an unsupported paraphrase
  (model-written with a fixed prompt, expected to be missed). Wilson 95%
  intervals. Also the false-alarm rate on the uncorrupted originals.
- repair: share of repaired turns where the repair kept a sentence the strip
  would have removed; tokens and seconds spent after the first draft.
- steps, tokens, seconds per arm.

## Procedure

```bash
R="docker compose run --rm --no-deps -T backend uv run --no-sync --project web/backend python"
E=docs/research/experiments/EXP-2026-11-013-agent-answers-human-judged
$R $E/code/generate.py --arm a --conc 4 --tag main
$R $E/code/generate.py --arm b --budget-from data/arm_a_main.jsonl --tag main
python3 $E/code/make_sheets.py          # sheets, evidence files, key (key outside sheets/)
$R $E/code/inject.py                    # injected-error set, verifier recall
python3 $E/code/analyse.py              # metrics without people
# after ratings return:
python3 $E/code/score.py
```

## What would falsify this

C-033 fails if fewer than 70% of arm (a) answers are majority-correct or
fewer than 85% of its citations are judged supporting. C-034 fails if the
paired interval includes zero or favours arm (b). C-035 fails if removal
precision < 0.9 or recall < 0.5. Disagreements are reported, never resolved by
picking a rater.

## Limits stated in advance

One fictional lab ranked against the real corpus, one model, questions written
by the implementing agent, raters arranged by the maintainer (not blind to the
system's existence, blind to arm).

## Amendment 1 — 2026-11-12, after generation, before any rating

Nothing below changes an answer raters will see from arm (a); all of it was
done before any sheet left the folder.

1. **Question ids.** The tagged-paper and tagged-opportunity questions both
   received ids `ta01`–`ta08` (an id-generation slip). The opportunity
   questions are renamed `to01`–`to08` in `code/questions.json` and in arm (a)'s
   rows (each row also carries its category, so the mapping is exact). Text
   unchanged.
2. **Arm (b) told which records were tagged.** The first arm (b) run gave the
   model the tagged items as `#1…` but did not say they were the tagged ones,
   so "this paper" was ambiguous to it while the agent is told what was
   tagged. Arm (b) was rerun with one added line ("The asker tagged #1 … with
   this question"). The first run is kept at the session scratch path, unused.
   Arm (b)'s evidence is limited by `corpus_search`'s 20-result cap, so its mean
   total (9.6k tokens) sits well under arm (a)'s mean (27.1k): the budget is a
   ceiling arm (b) does not reach.
3. **Removed-item sheet.** A repair verdict and the strip that follows it name
   the same item; the sheet lists it once, in the sentence of the first draft.
4. **Validation repetition.** Arm (a) is run again (`--tag rep2`, and further
   tags if time allows) for run-to-run stability and the repair's cost (fixed
   per-call counter). Only `main` goes to raters.

## Amendment 2 — 2026-11-13 03:22, before arm (b) `rep2`

Arm (b) repeated unchanged (`--arm b --budget-from data/arm_a_main.jsonl
--tag rep2`) to show the single call's run-to-run variation in tokens and
seconds. Only `main` goes to raters.

## Amendment 3 — 2026-11-13, after the verifier was changed, before re-scoring

The verifier (`tools/agent/verify.py`) was changed in response to this
experiment's findings: (1) a venue, funder, publisher or place line passes only
when every distinctive word is in the evidence (was: three in five); (2) a
number beside an author list is checked; (3) an amount written in short form
("€1.5–15M", "€2.5M") is matched against the evidence's numbers at their
scale, and a decimal with a scale suffix is now read as a figure at all.

`code/rescore.py` re-checks, with the changed verifier and nothing else
changed, the stored injected copies of all three repetitions
(`data/inject_<tag>.jsonl`) and the 150 stored original answers
(`data/arm_a_<tag>.jsonl`), against the same stored evidence. It reports per
class and placement the old and new catch counts, and every original answer
the new verifier flags (a candidate false alarm), listed individually. It
writes `data/rescore_v2.json`. Predictions, fixed now: invented venues as fact
lines are caught far more often (most of the 19 + 2 × repetitions misses were
word-overlap passes); prose catches are unchanged except for amounts; the
amount rows keep their recall; the `main` and `rep3` removals of "€1.5–15M"
are no longer flagged. Any new flag on an original answer is reported as a
false-alarm candidate, not explained away. The rated `main` answers are not
regenerated: raters still judge what the old verifier produced.

Data join (found on the first re-score, before anything was changed to fix
it): `inject_main.jsonl` was written before Amendment 1's rename, so its
`ta0N` copies come from two different answers. `code/rescore.py` matches each
such copy to the original whose text it was made from. The first, unmatched
re-score is kept at the session scratch path; its only difference is that join.

## Amendment 4 — 2026-11-13, after the Amendment 3 re-score, before the next

The Amendment 3 verifier flagged three original answers (`main` co10, `rep2`
co02 and co10), all for "€8.9M" written for the evidence's "€8,925,000" —
correct rounding the new scale reading turned into a false alarm (before
Amendment 3 a decimal with an "M" after it was not read as a figure at all).
That result stands in `data/rescore_v2.json`. One further change: an amount
written with a scale ("8.9M") is backed when an evidence number rounds to it
at the written precision (here within ±0.05M). Percentages and unscaled
decimals keep the literal match. The same re-score is run again into
`data/rescore_v3.json`. This is a change made after seeing the data, on this
data, so `v3`'s false-alarm count is not an independent estimate; a fresh set
of answers is needed for that.

Within Amendment 4, before its re-score was recorded: the first run of it
missed one planted amount (`rep3` co04, "$3.8 million") because the number
reader parsed a DOI's digits as 3,770,855. Links and DOIs are now left out of
the evidence's numbers. `data/rescore_v3.json` is the run after that fix;
the run before it differs only in that one copy.

## Amendment 5 — 2026-11-15, regenerate the 50 answers after the round-one fixes (tag `fix1`)

Written and committed before any `fix1` answer was generated, as step 4 of
Phase 3 of `docs/plans/20261115-mylo-evaluation-round-two.md`.

1. **What.** The same 50 questions (`code/questions.json`, unchanged), both
   arms, one repetition each, on the current commit (which contains `60ae301`,
   the fixes from round one):
   - arm (a): `generate.py --arm a --conc 3 --tag fix1`;
   - arm (b): `generate.py --arm b --budget-from data/arm_a_fix1.jsonl --tag fix1`
     (same budget rule as round one: the mean total tokens of the same tag's
     arm (a)).
   Concurrency is 3 turns (not 4) because three experiments share the model
   server tonight; the environment adds `AGENT_PARALLEL_CALLS=0` so a turn
   never has more than one request in flight (the function calls it
   serialises are database reads; the answer path is unchanged).
2. **Sheets.** `make_sheets.py --tag fix1 --sheets sheets_fix1 --key-suffix _fix1`
   writes the blinded sheets under `data/sheets_fix1/` and the keys to
   `data/key_fix1.csv` and `data/removed_key_fix1.csv`. `make_sheets.py` gained
   these two options in this amendment; their defaults reproduce round one's
   paths, so round one's sheets and keys are untouched. Nobody rates `fix1`
   tonight; the sheets are ready if a rater appears.
3. **Use.** These 100 answers are the input of `EXP-2026-11-020` 5c (a second
   model reads each against the evidence the producer had). Nothing in this
   experiment's round-one numbers is recomputed.
4. **Preflight, not counted.** `data/arm_a_preflight-r2.jsonl` is one arm (a)
   answer to `ta01` (11.5 s), generated 2026-11-15 05:33 UTC as the round-two
   preflight (`generate.py --arm a --only ta01 --tag preflight-r2`). It checked
   that the harness still runs; it is kept and counted nowhere.
5. **Failures.** A question whose generation raises is recorded with its
   error and not retried; the count of failed rows is reported.
