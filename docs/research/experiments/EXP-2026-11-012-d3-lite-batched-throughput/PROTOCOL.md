# EXP-2026-11-012 — Protocol

Written before the run, on 2026-11-09.

## Question

How many pairs per second does d3-lite answer when it is allowed to work on
several pairs at once, and is that faster than the stock Qwen3-4B on llama.cpp
(`EXP-2026-11-009`, 22.8 calls/s at four in flight)?

## Why this experiment exists

`EXP-2026-11-008` measured d3-lite at 1, 4 and 8 requests in flight, but through
GAIFA's decide server, which takes one engine lock and one GPU-queue lease per
request. Concurrency there can only queue, so that sweep measured the server,
not the model. `EXP-2026-11-009` then put llama.cpp's 8 parallel slots next to
it and called llama.cpp 3.2× faster. That was not a fair comparison. This run
lets d3-lite work on several pairs at once, the way llama.cpp did.

## Hypothesis

Stated before the run. d3-lite already runs up to `batch_size` questions per
forward pass, padded to one length (`d3_runtime.D3.run`), and at 0.85B
parameters a short pass is dominated by fixed cost. So putting the questions of
K pairs into one pass should raise throughput nearly in proportion to K at
small K.

The prior is above 20 pairs/s at K = 8 on the synthetic state, which would beat
Qwen3-4B on llama.cpp. Batched answers should match one-pair-at-a-time answers
to within 1e-3, because the runtime masks the padding.

## Setup

- **Model:** `vllm-sr/d3-lite` revision
  `03560c26f5199c3c04129a2ccb38960c913635e0`, the copy GAIFA's decide mod
  serves (`GAIFA/data/models/decide/d3-lite`). It is loaded directly with that
  folder's own `d3_runtime.D3.from_pretrained` in GAIFA decide's venv (the
  ROCm torch it already runs on), on the Radeon 8060S, `verify="fast"`, with
  `cudnn` off as GAIFA's adapter does.
- **Not GAIFA's server.** No HTTP, no engine lock, no GPU-queue lease. That is
  the point of the run. It does mean these numbers are what a server that
  batches across requests could reach, not what decide serves today.
- **Questions:** the exact `/v1/decide` bodies Mycelium's
  `PortDecisionClient` sends. They are dumped from Mycelium's own code
  (`decision_check.SAMPLE_STATE` with its two questions; the production
  `typesafe_rerank.questions_for` for real states) and converted with GAIFA's
  own `to_d3`. This gives the same model input the server would build.
- **Batching:** K pairs' prepared token sequences are concatenated and passed
  to `D3.probabilities` in one call. `batch_size` is 32, so all rows of K ≤ 8
  pairs fit in one pass.
- **Warm-up:** each configuration runs once untimed over its whole input before
  the timed pass, so Triton's per-shape autotuning is not counted.

## Data

- **Synthetic:** `decision_check.SAMPLE_STATE`, 48 calls per configuration.
  This is identical to `EXP-2026-11-008` and `EXP-2026-11-009`, so the numbers
  are directly comparable.
- **Real:** the 165 states of `EXP-2026-11-007`, with 3–4 questions each. They
  are the same scratch file `EXP-2026-11-009` used, which is not committed
  because it carries profile text.

No judgements are involved; this is a throughput and parity run.

## Metrics

- **Throughput (primary):** pairs answered ÷ wall seconds of the timed pass,
  device-synchronized (answers moved to the CPU). Synthetic, per K ∈ {1, 4, 8}.
  It is comparable with EXP-008's and EXP-009's calls/s, where a call is one
  state with both questions.
- **Real-state throughput:** the same metric on the 165 real states, per K, set
  against EXP-007's 367 ms/pair through the server and EXP-009's 554 ms/pair
  through llama.cpp, both sequential.
- **Sequential in-process:** `system_one` one pair at a time. It separates the
  server's overhead from the model's own time.
- **Parity:** the largest absolute difference, over every answer probability on
  the real states, between batched (K = 8) and sequential.

## Baselines

- d3-lite through GAIFA decide (EXP-008: 7.13 / 7.99 / 8.56 calls/s at 1/4/8).
- Qwen3-4B Q4_K_M on llama.cpp, 8 slots (EXP-009: 7.19 / 22.79 / 13.43 calls/s).

## Procedure

```bash
S=<scratchpad>                  # holds EXP-2026-11-007's states.json
E=docs/research/experiments/EXP-2026-11-012-d3-lite-batched-throughput
uv run --no-sync --project web/backend python $E/code/dump_bodies.py \
    --states $S/states.json --out $S/bodies.json
/home/bdgr/Agents/GAIFA/services/decide/.venv/bin/python -I $E/code/bench.py \
    --bodies $S/bodies.json --out $E/data/bench.json
python3 $E/code/analyse.py
```

## What would falsify this

- Synthetic throughput at K = 8 at or below 1.5× K = 1 refutes "batching
  scales". d3-lite would then be compute-bound like the server sweep suggested.
- K = 8 synthetic throughput at or below 22.8 pairs/s refutes "faster than
  llama.cpp Qwen3-4B".
- A parity difference above 1e-3 means batching changes answers. The throughput
  would then not count until that is explained.

## Amendment (2026-11-09, after arm A ran)

Arm A showed d3-lite flat on real states. `EXP-2026-11-009` had measured
llama.cpp concurrency only on the synthetic state, so the real-state
comparison had no concurrent llama.cpp number. **Arm B** was added:

- Qwen3-4B Q4_K_M on the same `llama-server` b11912 setup (`-np 8`).
- The 165 real states with the production questions, through
  `PortDecisionClient`.
- 1, 4 and 8 in flight, each level preceded by an untimed pass over the first
  8 pairs.
- Command: `code/qwen_real.py` (see RESULTS §8).

It was designed after seeing arm A, and no falsifier was set for it.
