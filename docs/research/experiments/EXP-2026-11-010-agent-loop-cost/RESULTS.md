# EXP-2026-11-010 — Results

Attempt 2, 2026-11-12/13 (attempt 1 on 2026-11-09 measured nothing; the
endpoint was down). Model: Qwen 3.8 27B on vLLM, one A100 80GB, through the
instance relay (`env/hardware.md`). Every number is read from
`data/metrics.json` (written by `code/analyse.py` from `data/a1_<run>.json`
and `data/a2_<run>.jsonl`); the generated table is `tables/summary.md`.

## 1. Headline

**C-030 holds.** A five-call scripted turn took 3.4–5.0 s and 16k tokens;
fifteen calls peaked at 7.9k prompt tokens, a quarter of the 32k window. On
twelve real questions in the demo lab, every turn that made up to five
function calls finished within 10.6 s and 25.4k tokens (46 such turns across
three runs), and no real turn's single model call exceeded 19.1k prompt
tokens, so nothing needed compaction. On an idle model server the median turn takes
**2.4 s** for a one-lookup question, **9.7 s** for a few lookups and **22.0 s**
for a compound question; the worst compound turn took **83.8 s** (27 model
calls, 347k tokens in total). The informal five-minute observation that
motivated A2 was not reproduced: no turn came near the 15-minute cap.

## 2. Results table

A2, per question group, three repetitions of four questions each (12 turns
per cell):

| Run | Group | Median s | Worst s | Mean s | First activity, median s | Model calls (median / max) | Function calls (median / max) | Median tokens | Worst tokens |
|---|---|---:|---:|---:|---:|---|---|---:|---:|
| idle | one lookup | 2.35 | 4.61 | 2.54 | 0.78 | 2 / 3 | 1 / 2 | 5,788 | 7,620 |
| idle | a few lookups | 9.67 | 17.89 | 10.16 | 0.78 | 6 / 10 | 6.5 / 12 | 21,917 | 55,458 |
| idle | compound | 22.01 | 83.84 | 30.72 | 0.70 | 10.5 / 27 | 20 / 61 | 56,571 | 346,692 |
| idle, second run | one lookup | 2.22 | 4.77 | 2.42 | 0.78 | 2 / 4 | 1 / 3 | 5,812 | 10,318 |
| idle, second run | a few lookups | 7.96 | 18.78 | 9.47 | 0.78 | 6 / 7 | 6 / 9 | 21,107 | 39,042 |
| idle, second run | compound | 20.31 | 44.87 | 23.74 | 0.85 | 9.5 / 17 | 15.5 / 58 | 50,270 | 190,448 |
| under the nightly | one lookup | 2.38 | 7.54 | 2.61 | 0.95 | 2 / 3 | 1 / 2 | 5,779 | 7,612 |
| under the nightly | a few lookups | 13.21 | 38.70 | 16.98 | 1.01 | 6 / 9 | 7 / 17 | 22,883 | 49,657 |
| under the nightly | compound | 29.22 | 70.51 | 34.57 | 1.04 | 9.5 / 23 | 17 / 32 | 55,105 | 211,566 |

Stops: idle — one compound turn ran out of its 25 steps, one few-lookup turn
hit the thrash stop, the verifier's repair ran twice; idle, second run — one
thrash stop, one repair; under the nightly — one thrash stop, one repair. No turn errored or timed out.

C-030's bar, measured directly:

| Run | Turns with ≤ 5 function calls | Slowest | Most tokens | Over 60 s | Over 30k tokens | Largest single-call prompt (any turn) |
|---|---:|---:|---:|---:|---:|---:|
| idle | 16 | 9.59 s | 22,660 | 0 | 0 | 18,943 |
| idle, second run | 16 | 7.17 s | 25,441 | 0 | 0 | 19,055 |
| under the nightly | 14 | 10.64 s | 19,757 | 0 | 0 | 12,895 |

A1 (scripted results; three repetitions; the model made exactly the calls
asked in every repetition):

| Run | Calls | Mean s per turn | Worst s | Mean tokens per turn | Peak prompt tokens |
|---|---:|---:|---:|---:|---:|
| idle (`r2idle`) | 1 | 1.61 | 2.95 | 3,733 | 2,058 |
| idle | 5 | 4.98 | 6.36 | 16,281 | 3,754 |
| idle | 15 | 9.02 | 9.68 | 76,637 | 7,946 |
| under the nightly (`r1`) | 1 | 2.65 | 6.13 | 3,716 | 2,032 |
| under the nightly | 5 | 3.35 | 3.55 | 16,326 | 3,797 |
| under the nightly | 15 | 11.90 | 17.96 | 76,503 | 7,888 |

## 3. Figures

None.

## 4. Interpretation

- The decision rule (a five-step turn over 60 s) did not fire, so no default
  needs to change. The slowest turns are compound questions that fan out
  into many function calls; their time is mostly the number of model calls
  (idle: median model call 0.87 s, 90th percentile 3.8 s, longest 15.7 s over
  236 calls; computed from the `calls` field of `data/a2_a2idle.jsonl`).
- **Tokens, not seconds, are the cost to watch.** A compound turn's total
  grows with the number of model calls because each call re-sends the
  conversation: the worst idle turn sent 347k tokens over 27 calls although
  no single call exceeded 19k. If cost matters on a metered model, the lever
  is `tools.agent.max_steps` (25 now) or a lower `result_cap_tokens` (4,000),
  not the context window.
- The nightly run's load slowed few-lookup and compound turns by roughly a
  third at the median (13.2 vs 9.7 s, 29.2 vs 22.0 s) and left one-lookup
  turns unchanged.
- First activity (the first streamed text or function call) arrives in under
  1 s at the median in every group; a person sees something happening almost
  at once even when the answer takes 20–80 s.

## 5. Threats to validity

- One model, one host, one network path; latency includes the SSH relay.
- Twelve questions in one demo lab; compound questions were written to fan
  out.
- "Idle" means nothing scheduled on this side; the relay does not expose the
  A100's queue (ISSUES.md).
- The run is synchronous `run_turn` — the Celery task's function — so the
  queue hop the web chat adds is not included.

## 6. What surprised us

The model batches function calls: a turn with six model calls made sixteen
function calls. Counting "steps" by model calls understates how much a turn
reads.

## 7. Follow-ups

None required by the gate. If compound turns are common in real use, measure
whether a lower `max_steps` changes answer quality (EXP-2026-11-013's sheets
can show it).

## AMENDMENTS

Amendment 1 (PROTOCOL.md, before the run): container runtime and the A2 arm.
