# EXP-2026-11-014 — Results

Runs r1 (00:42), r1b (01:11), r1s (02:15) and r2 (02:21), 2026-11-13, on the
host in `env/hardware.md`, with nothing else using the decision server (no
foreign requests in any timed pass, by the `/health` counter). Every number
is read from `data/metrics.json` (written by `code/analyse.py` from
`data/bench_<run>.json`); the full table is `tables/summary.md`.

## 1. Headline

**On the real rerank states the server is compute-bound at about 5.2
decisions per second, and it crashed at 32 requests in flight.** Throughput
rises only from 4.6 decisions/s (1 in flight) to 5.25 (16–24 in flight) while
p95 latency grows from 0.70 s to 14.2 s: beyond about 4 in flight, concurrency
only queues. At 32 in flight the engine ran out of GPU memory, 80 of 113
requests failed, and its service manager restarted it (`logs/crash_r1.txt`).
Short states held all the way to 64 in flight (about 15 decisions/s, no
errors), so the limit is state length times concurrency, not concurrency
alone. **Asking a state's questions together or one at a time changes the
answers**: the most likely answer differs on 20.6% of 291 questions (mean
probability difference 0.063, largest 0.32), past the 5% the protocol named
in advance; load does not (1 vs 24 in flight: 99.7% agreement, largest
difference 0.009).

## 2. Results table

Median of the timed passes (three per level; two in r2). Requests per pass:
113 (one per state) for `joint`, `choice` and `synthetic`; 291 (one per
question) for `single`.

| Shape | In flight | Decisions/s | Requests/s | Input tokens/s | p50 s | p95 s | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| joint (production) | 1 | 4.63 | 1.80 | 1,984 | 0.52 | 0.70 | 0 |
| joint | 4 | 5.15 | 2.00 | 2,208 | 1.87 | 2.49 | 0 |
| joint | 16 | 5.25 | 2.04 | 2,252 | 7.40 | 9.43 | 0 |
| joint | 24 | 5.25 | 2.04 | 2,253 | 10.84 | 14.24 | 0 |
| joint | 32 | 3.65 | 1.61 | 1,777 | 14.79 | 16.05 | **70.8%, server crashed** |
| single (one question per request) | 1 | 2.21 | 2.21 | 2,049 | 0.45 | 0.57 | 0 |
| single | 24 | 2.54 | 2.54 | 2,364 | 9.42 | 11.27 | 0 |
| choice (criteria form) | 1 | 4.55 | 1.77 | 1,983 | 0.53 | 0.71 | 0 |
| choice | 24 | 5.13 | 1.99 | 2,236 | 11.12 | 14.53 | 0 |
| synthetic (short state) | 1 | 11.12 | 5.56 | 2,097 | 0.18 | 0.18 | 0 |
| synthetic | 16 | 14.83 | 7.41 | 2,795 | 2.14 | 2.31 | 0 |
| synthetic | 64 | 14.92 | 7.46 | 2,813 | 8.41 | 8.86 | 0 |

Run-to-run (r2 repeating `joint`): 4.63, 5.11, 5.22 and 5.24 decisions/s at
1, 4, 16 and 24 in flight, against r1's 4.63, 5.15, 5.25 and 5.25.

Consistency on identical bodies (`_consistency` in `data/metrics.json`):

| Comparison | Questions | Largest difference | Mean difference | Differs by > 0.05 | Same most-likely answer |
|---|---:|---:|---:|---:|---:|
| all questions in one request vs one per request (1 in flight) | 291 | 0.318 | 0.063 | 45.7% | 79.4% |
| 1 vs 24 requests in flight (joint) | 291 | 0.009 | 0.002 | 0% | 99.7% |

## 3. Figures

None.

## 4. Interpretation

- **Capacity is tokens, not requests.** Every shape levels off at roughly
  2,200–2,800 input tokens per second; a production state with its questions
  is about 1,100 tokens (`input_tokens_per_request`), so the card serves about
  two items per second however they are sent. Reranking N items takes about
  N / 2 seconds of decision time, and more than about 4 requests in flight
  gains nothing.
- **The client must cap concurrency below 32 for real states.** The
  operator's stated ceiling of 64 holds for short prompts but not for
  production-length ones on this 16 GB card. A cap of 4–8 gives full
  throughput with p95 under 5 s.
- **Joint asking is twice as fast but not equivalent.** Answering every
  question of a state in one request yields 4.6–5.3 decisions/s against
  2.2–2.5 one at a time, and is what the production client does. But one
  answer in five changes its most likely value when the other questions are
  present. This experiment cannot say which form is more correct; it says
  the two are not interchangeable, so a switch between them is a change in
  ranking behaviour, not only in speed.
- The `choice` form (questions written as choices with criteria) matches the
  native `joint` form's speed within 3%; whether it gives the same answers
  was not compared (the answer formats differ).

## 5. Threats to validity

- One host, one card, one model build; 113 states from one reader's slates.
- The crash was observed once and not repeated on purpose; the exact
  threshold between 24 and 32 is not known.
- The synthetic state carries the paper questions only (two per request).
- EXP-2026-11-012's numbers come from a different host and models; they are
  context, not a baseline.

## AMENDMENTS

Amendment 1 (shorter repeat) and Amendment 2 (after the crash: real shapes
only up to 24 in flight; short state up to 64) are in PROTOCOL.md, each
written before the runs it describes.
