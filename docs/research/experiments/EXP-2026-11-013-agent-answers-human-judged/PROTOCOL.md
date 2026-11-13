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
