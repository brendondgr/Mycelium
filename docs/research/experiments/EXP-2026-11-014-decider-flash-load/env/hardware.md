# Hardware and environment

| Field | Value |
|---|---|
| CPU | Intel Xeon Silver 4114 @ 2.20 GHz, 20 logical CPUs (host `sc-zeus`) — runs the benchmark client and the protocol adapter |
| RAM | 62 GB |
| GPU | one NVIDIA Quadro RTX 5000, 16 GB (driver 595.71.05), serving the decision model; 90% of its memory reserved by vLLM |
| Model | `kimrinking/pplx-decider-flash-v1.2-fp8` (Perplexity Decider Flash v1.2, static FP8, Qwen3.5-4B based), served name `pplx-decider-flash-v1.2-fp8`, `--dtype half`, `MAX_MODEL_LEN` 32768, `MAX_NUM_SEQS` 64 |
| Server | the operator's `vLLM-Decision` setup: vLLM 0.32.0 (torch 2.13.0+cu130) pooling engine on port 8001, protocol-v3 adapter on port 7500; adapter temperature 1.554 (from `/health`) |
| Client | `code/bench.py`, Python 3 standard library on the host, one thread per request in flight |
| Container | none — run on the host |
| Total wall clock | see RESULTS.md (per run) |

## What else used the server

Nothing scheduled: the nightly run (the decision server's only other client)
finished at 00:31 EST, before the first timed request. The adapter's
`/health` request counter is read before and after every timed pass, and any
requests beyond the pass's own are reported in `data/metrics.json`
(`foreign_requests`). This session's other experiments use the remote model
server, not this GPU; none ran during a timed pass.

## Anything about the hardware that affects the claim

A Turing-generation card has no FP8 tensor cores; how vLLM executes this FP8
checkpoint on it (which kernels) was not checked. Absolute throughput says
little about newer GPUs. EXP-2026-11-012's numbers come from a different host (AMD Ryzen AI MAX+
395, integrated Radeon 8060S) and different models; they are context, not a
like-for-like baseline.
