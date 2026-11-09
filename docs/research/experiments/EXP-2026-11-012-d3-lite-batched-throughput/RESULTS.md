# EXP-2026-11-012 — Results

**Arm A:** d3-lite (`vllm-sr/d3-lite@03560c2`) loaded in-process with its own
runtime, outside GAIFA's decide server, K pairs per forward pass. **Arm B**
(added after arm A, see PROTOCOL.md Amendment): Qwen3-4B Q4_K_M on llama.cpp
b11912, 8 slots, real states at 1/4/8 in flight. Every number is read from
`data/metrics.json`, written by `code/analyse.py`.

## 1. Headline

The comparison in `EXP-2026-11-009` was unfair, and correcting it reverses the
throughput claim. On the 165 real states **neither model gains from
parallelism**:

| Model | Pairs/s, real states |
| --- | --- |
| d3-lite | 2.22–2.50 |
| Qwen3-4B on llama.cpp | 1.50–1.80 |

At its best setting d3-lite is 1.39× faster than Qwen. llama.cpp's 3.2× lead
existed only on the ~400-character synthetic state. The hypothesis is refuted
twice:

- Batching d3-lite gave 1.32× on the synthetic state (below the 1.5× bar) and
  nothing on real states.
- At 8 per pass on the synthetic state d3-lite reached 10.98 pairs/s, short of
  llama.cpp's 22.8.

## 2. Results table

<!-- BEGIN GENERATED TABLE -->
Pairs per second (one pair = one state with all of its questions).

| State | Parallelism | d3-lite, decide server | d3-lite, in-process | Qwen3-4B, llama.cpp |
| --- | ---: | ---: | ---: | ---: |
| synthetic (48) | 1 | 7.132 | 8.288 | 7.189 |
| synthetic (48) | 4 | 7.993 | 11.806 | 22.792 |
| synthetic (48) | 8 | 8.56 | 10.976 | 13.427 |
| real (165) | 1 | — | 2.319 | 1.799 |
| real (165) | 4 | — | 2.219 | 1.495 |
| real (165) | 8 | — | 2.258 | 1.594 |

Parallelism: requests in flight (decide server, llama.cpp) or pairs per forward pass (d3-lite in-process). In-process one-pair-at-a-time (`system_one`): synthetic 7.429, real 2.498.

| Batched vs sequential answers | max abs diff |
| --- | ---: |
| synthetic, 4 per pass | 0.000751 |
| synthetic, 8 per pass | 0.000979 |
| real, 4 per pass | 0.034668 |
| real, 8 per pass | 0.033518 |
<!-- END GENERATED TABLE -->

## 3. Figures

None.

## 4. Interpretation

- **Real states are compute-bound for both models.** A production state is
  about 2,300 characters with 3–4 questions, so each pair is several thousand
  prompt tokens and no output. Once the GPU is busy with one pass, a second
  request or a wider batch only shares it. That holds for llama.cpp's 8 slots
  (1.80 → 1.50 → 1.59 pairs/s, with p50 latency 583 → 2,710 → 4,960 ms) and
  for d3-lite's batched pass (2.32 → 2.22 → 2.26).
- **The decide server was not the bottleneck.** In-process, one pair at a
  time, d3-lite did 7.43 pairs/s on the synthetic state, against 7.13 through
  the server. The server's lock and lease cost about 4%. `EXP-2026-11-008`'s
  conclusion that concurrency only queues was right, but for a reason it did
  not show: it is the model's compute, not the lease.
- **Short states flattered llama.cpp.** On ~400 characters a pass is mostly
  fixed overhead, which llama.cpp's slots overlap well and d3-lite's runtime
  does not. That regime is not what the nightly rerank sends.
- **For the switch:** on this host a local backend sustains about 2.3 pairs/s
  (d3-lite) or 1.6–1.8 (Qwen3-4B). Run it at 1–2 in flight;
  `rerank_concurrency = 12` buys nothing for either. At 400 pairs per target
  before fingerprint reuse, that is about 3 minutes per target on d3-lite.

## 5. Threats to validity

- **Batched answers are not identical to sequential ones on real states.** The
  largest difference was 0.035. The protocol's bar was 1e-3, so the batched
  real-state numbers are recorded but not counted as equivalent outputs. The
  likely cause is bf16 numerics with left padding across rows of very
  different lengths; it was not investigated. It does not change the headline,
  because batching did not raise throughput anyway, and sequential is what the
  server runs.
- **d3-lite may be running reference kernels.** Transformers warned that
  `causal_conv1d` and `flash-linear-attention` are not installed, so
  `causal_conv1d_fn` and `chunk_gated_delta_rule` fall back to their slower
  PyTorch implementations. GAIFA's decide runs in the same venv, so the server
  numbers share this. An optimized install could change both d3-lite columns
  (Q-063).
- **Arm B was added after arm A's results were seen.** Its design copies
  `EXP-2026-11-009` and arm A, and the amendment says so.
- **Not quite the same unit of parallelism.** llama.cpp's parallelism is
  requests in flight; d3-lite's is pairs per pass. Both are what each runtime
  offers a caller, and both answer "does more work at once help?".
- **One GPU, shared.** GAIFA's other mods share this integrated GPU. Nothing
  was observed running, but it was not controlled. llama.cpp's prompt cache
  can reuse the shared researcher prefix within a pass. That is a real feature
  of the server, not a leak.

## 6. What surprised us

- The llama.cpp advantage vanished completely on real input. Concurrency made
  Qwen slower on real states (1.80 → 1.50 pairs/s).
- The decide server's overhead was almost nothing.

## 7. Follow-ups

- Q-063: Does installing `flash-linear-attention` / `causal_conv1d` (ROCm
  builds) raise d3-lite's real-state throughput, and does batching help once
  the kernels are fast?
- Q-061 (partly answered): llama.cpp at production states is now measured
  (1.5–1.8 pairs/s, no gain from concurrency). vLLM is still unmeasured.

## 8. Reproduction

```bash
S=<scratchpad holding EXP-2026-11-007's states.json>
E=docs/research/experiments/EXP-2026-11-012-d3-lite-batched-throughput
uv run --no-sync --project web/backend python $E/code/dump_bodies.py --states $S/states.json --out $S/bodies.json
BENCH_SCRATCH=$S /home/bdgr/Agents/GAIFA/services/decide/.venv/bin/python -I $E/code/bench.py --bodies $S/bodies.json --out $E/data/bench.json
llama-server -m Qwen3-4B-Q4_K_M.gguf --alias qwen3-4b-q4_k_m -ngl 99 -c 32768 -np 8 --host 127.0.0.1 --port 5180 &
uv run --no-sync --project web/backend python $E/code/qwen_real.py --states $S/states.json --url http://127.0.0.1:5180 --out $E/data/qwen_real.json
python3 $E/code/analyse.py
```

## AMENDMENTS

A completed experiment is immutable. Corrections are appended here, dated, never
edited into the sections above.
