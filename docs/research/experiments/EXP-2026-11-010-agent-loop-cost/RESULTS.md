# EXP-2026-11-010 — Results

**Round two, A5 (2026-11-15, Amendment 5).** C-030's bar still holds on the
current commit: every turn with up to five function calls finished within
**26.1 s idle and 41.2 s with 8 in flight**, under 20.1k tokens (66 such turns,
0 over 60 s or 30k). But **turns are much slower than round one** — idle
medians 14.4 / 28.1 / 63.2 s (single / few / compound) against 2.4 / 9.7 /
22.0 s — **and the instance model is no longer the one round one measured**
(the relay's `default-model` now self-reports Google-trained), so the loop
fixes and the model change cannot be separated. O8 (compound turns slow under
load) is **kept**: the 8-in-flight compound median is 79.0 s (round one 72.5–
77.8 s), though the worst turn fell from 169–234 s to 109.2 s.

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
calls, 347k tokens in total). **With several people asking at once, turns
slow down sharply:** with 8 turns in flight (separate processes, as in
production) the medians are 5.9 s, 32.4 s and 77.8 s and the worst compound
turn took 234 s, the scale of the informal five-minute observation that
motivated A2; five-call turns still stayed under 34 s.

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

A3, several turns at once (Amendment 2 and its addendum). The process-based
runs match production, where each turn runs in its own Celery worker process;
the thread-based runs (several turns as threads in one harness process) are
kept, and their extra slowdown is the harness's:

| Run | Turns in flight | Turns | One lookup, median / worst s | A few, median / worst s | Compound, median / worst s | Median model call s | Seconds per question overall |
|---|---:|---:|---|---|---|---:|---:|
| idle (`a2idle`, `a2idle2`) | 1 | 36 + 36 | 2.35 / 4.61 and 2.22 / 4.77 | 9.67 / 17.89 and 7.96 / 18.78 | 22.01 / 83.84 and 20.31 / 44.87 | 0.87 and 0.77 | 14.10 and 11.47 |
| 4 processes (`a3p4`) | 4 | 48 | 4.06 / 7.70 | 16.59 / 30.31 | 44.15 / 103.81 | 1.69 | 6.31 |
| 8 processes (`a3p8`) | 8 | 96 | 5.94 / 25.33 | 32.42 / 82.19 | 77.78 / 234.00 | 3.15 | 5.91 |
| 4 processes, repeat (`a3p4b`) | 4 | 48 | 4.05 / 7.05 | 16.11 / 27.51 | 50.38 / 169.68 | 2.02 | 7.95 |
| 8 processes, repeat (`a3p8b`) | 8 | 96 | 6.85 / 21.96 | 30.33 / 66.95 | 72.54 / 169.34 | 3.37 | 5.39 |
| 4 threads (`a3c4`) | 4 | 36 | 9.40 / 12.79 | 27.16 / 38.01 | 64.51 / 79.68 | 1.57 | 9.13 |
| 8 threads (`a3c8`) | 8 | 36 | 16.07 / 22.25 | 47.68 / 92.51 | 73.63 / 104.87 | 1.89 | 8.06 |

With 4 and 8 processes, every turn with up to five function calls still
finished within 28.4 s and 33.9 s (25 and 44 turns; none over 30k tokens);
in the repeats, within 27.1 s and 28.6 s.
No turn errored or hit the 15-minute cap.

A4, `max_steps` capped at 10 (Amendment 3; idle, one at a time, run `a4s10`):

| Group | Median s | Worst s | Median tokens | Worst tokens | Most model calls | Turns that hit the cap |
|---|---:|---:|---:|---:|---:|---:|
| one lookup | 1.84 | 4.26 | 5,812 | 7,621 | 3 | 0 of 12 |
| a few lookups | 8.88 | 18.93 | 22,256 | 37,671 | 7 | 0 of 12 |
| compound | 20.14 | 33.51 | 57,406 | 100,950 | 11 | **6 of 12** |

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
  1 s at the median in every group when one turn runs at a time, and in 1.4–2.8 s
  with 4–8 concurrent turns; a person sees something happening early even
  when the answer takes 20–80 s.
- **Concurrency is where a turn gets slow.** With several people asking at
  once the model server slows each call (median call 0.8 s alone, 1.7 s with
  4 turns in flight, 3.2–3.4 s with 8), and a compound turn's many calls multiply
  that: its median rises from about 21 s to 44 s and 78 s, and the worst
  compound turn with 8 in flight took 234 s. That is the scale of the informal
  five-minute observation that motivated A2, which was made while the server
  had other work. Total throughput only roughly doubles (11.5–14.1 s per
  question one at a time; 6.3–8.0 s and 5.4–5.9 s with 4 and 8 in flight). If several
  people will use Mylo at once, a faster model on the agent route, or a lower
  `max_steps` for compound questions, is the lever; the five-call bar of
  C-030 still holds (≤ 34 s).
- **What `max_steps` 10 buys and costs (A4).** It leaves typical turns as they
  are (compound median 20.1 s against 20.3–22.0 s at 25) and cuts the tail
  (worst compound 33.5 s and 101k tokens, against 44.9–83.8 s and
  190k–347k), but half the compound questions then end on the cap and answer
  with what they have. Whether those answers are worse needs the raters'
  kind of judgement; the cap is a cost control, not a free speed-up.

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

## A5 — round two, 2026-11-15 (Amendment 5)

Run on the current commit (the round-one loop fixes included) at 09:53–10:24
UTC, after every other round-two run had stopped (EXP-2026-11-016 to -020 had
finished their model work by 09:50 UTC; the backend test suite was running on
this host's CPU in one-off containers until about 10:06). `a5idle`: the twelve
questions, three repetitions, one at a time (`--stop-at 10:45`, not reached).
`a5p8`: eight containers started together, each asking all twelve once with
`--rotate 0…7`. The process arm's rows were marked `conc: 8` by
`code/stamp_process_arm.py` so the analysis measures its batch from
timestamps, as round one's `a3p8` rows were. 132 demo threads
(`EXP-2026-11-010`) and their 3,910 events were deleted from the live database
afterwards.

| Run | In flight | Group | Median s | Worst s | Median tokens | Model calls (median/max) |
|---|---:|---|---:|---:|---:|---|
| a2idle / a2idle2 (round one) | 1 | single | 2.35 / 2.22 | 4.61 / 4.77 | 5.8k | 2/3–4 |
| **a5idle** | 1 | single | **14.40** | 16.85 | 10.5k | 4/5 |
| a2idle / a2idle2 | 1 | few | 9.67 / 7.96 | 17.89 / 18.78 | 21.9k / 21.1k | 6/7–10 |
| **a5idle** | 1 | few | **28.08** | 58.12 | 18.4k | 5/9 |
| a2idle / a2idle2 | 1 | compound | 22.01 / 20.31 | 83.84 / 44.87 | 56.6k / 50.3k | 9.5–10.5/17–27 |
| **a5idle** | 1 | compound | **63.18** | 75.09 | 27.4k | 6/7 |
| a3p8 / a3p8b (round one) | 8 | compound | 77.78 / 72.54 | 234.0 / 169.34 | 52.7k / 65.3k | 9.5/23–26 |
| **a5p8** | 8 | compound | **78.95** | 109.22 | 27.5k | 6/7 |

Model-call latency (median / p90): round one idle 0.77–0.87 / 3.5–3.8 s;
**a5idle 3.88 / 12.3 s**; a5p8 5.12 / 19.7 s. Twelve questions end to end:
idle 427 s per repetition (round one 138–169 s); with 8 in flight 607 s for
96 questions, 6.3 s each (round one 5.4–5.9 s). No turn hit `max_steps` or
timed out; thrash stops 1 (idle) and 3 (8 in flight), all in the few group.

**Reading.** The loop fixes did what they were for — compound turns use about
6 model calls instead of 9.5 and half the tokens, and the worst case under
load is half round one's. But every model call is now 4–5× slower, which
outweighs the saving; that is a property of the server answering as
`default-model` tonight, not of the loop, and it cannot be separated here.
C-030 is re-read as still holding (its bar is about turns of up to five
calls); O8 stays open. The full per-group numbers are in `tables/summary.md`
and `data/metrics.json`.

## AMENDMENTS

Amendment 1 (PROTOCOL.md, before the run): container runtime and the A2 arm.
Amendment 2 and its addendum (before their runs): the A3 concurrency arm, in
threads and then in separate processes. Amendment 3 (before its run): A4,
`max_steps` 10.
