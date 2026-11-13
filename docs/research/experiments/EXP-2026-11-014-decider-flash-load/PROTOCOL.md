# EXP-2026-11-014 — Protocol

Written 2026-11-12, before any timed request. Descriptive; no claim in
CLAIMS.md depends on it.

## Question

How much load can the local decision server (`pplx-decider-flash-v1.2-fp8`
behind the protocol-v3 adapter at `127.0.0.1:7500`) take on this host —
throughput, latency and errors as concurrency rises to 64 — and are its
answers stable under batching and under load?

## Hypothesis

From the operator (2026-11-12): throughput stops rising after about 16
requests in flight, and the server may crash above 64. Expected: requests per
second plateaus between 8 and 16 in flight while p95 latency keeps growing
roughly linearly beyond it; no errors up to 64. Answers agree between one
question per request and all questions in one request to within 0.05 in
probability on most pairs (EXP-2026-11-012 saw up to 0.035 on d3-lite).

## Setup

- Server: the operator's vLLM pooling engine (`vLLM-Decision/scripts/engine.py
  serve … --runner pooling --dtype half`, port 8001) behind the protocol-v3
  adapter on port 7500, one NVIDIA Quadro RTX 5000 (16 GB) on this host.
- Client: `code/bench.py`, Python standard library, on the same host, one
  thread per request in flight.
- Run alone: not while the nightly run (`mylo-daily.service`), which also calls
  this server, is active, and not while other experiments of this session use
  the host. `/health` request and error counters are read before and after
  every timed pass; a request-count delta larger than the pass's own requests
  means someone else was using the server, and is reported.

## Data

- The 113 real production rerank states for one reader (EXP-2026-11-007's
  `extract.py`, rebuilt today: 48 paper, 33 grant, 32 conference pairs across
  3 themes; median state ~3,700 characters). They hold profile text, so they
  stay in scratch; only their SHA-256 is recorded.
- The production questions (`typesafe_rerank.questions_for`, version
  `2026-09-17.1`), dumped to `data/questions.json`: two or three per pair.

## Shapes

- `joint` — one request per pair with all its questions, native types
  (yes/no → `noul` with true/false criteria; the ordered scale → `score`).
- `single` — one question per request.
- `choice` — all questions as `choice` with criteria (the documented form).
- `synthetic` — one fixed ~400-character state with the paper questions, 113
  times (comparison with EXP-2026-11-012's synthetic arm).

## Metrics

Per shape and concurrency level (1, 2, 4, 8, 12, 16, 24, 32, 48, 64): requests
per second, decisions (questions answered) per second, input tokens per
second (from `usage`), latency p50/p95/p99/mean, error rate. Three timed
passes per level over the whole request list after 20 untimed warm-up
requests; reported as the median pass and the spread. The whole sweep is run
more than once (`--tag r1`, `r2`, …) if time allows, to show run-to-run
variation.

Consistency, on identical bodies: `joint` vs `single` (per question, absolute
difference in the answer's probability for its first option, and whether the
most likely answer agrees), and concurrency 1 vs 64 within `joint`.

## Safety rule

Never more than 64 in flight. A level stops, and no higher level runs, if more
than 5% of its requests fail or `/health` stops answering.

## Procedure

```bash
S=<scratch>
docker compose run --rm --no-deps -T backend uv run --no-sync --project web/backend \
  python docs/research/experiments/EXP-2026-11-007-d3-lite-local-decision-smoke/code/extract.py \
  --user <reader> --per-theme 8 > $S/states.json
docker compose run … python docs/research/experiments/EXP-2026-11-014-decider-flash-load/code/dump_questions.py
python3 docs/research/experiments/EXP-2026-11-014-decider-flash-load/code/bench.py --states $S/states.json --tag r1
python3 docs/research/experiments/EXP-2026-11-014-decider-flash-load/code/analyse.py
```

## What would falsify this

Throughput still rising past 32 in flight, or any error at or below 64, would
contradict the operator's expectation; joint-vs-single disagreement on the
most likely answer for more than 5% of questions would mean batching
questions changes decisions and the production client should not batch.
