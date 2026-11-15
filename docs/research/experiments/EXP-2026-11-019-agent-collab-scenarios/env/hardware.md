# Hardware and environment

| Field | Value |
|---|---|
| CPU | Intel Xeon Silver 4114 @ 2.20 GHz, 20 threads (the harness and the instance embedder, fastembed on CPU) |
| RAM | 62 GB |
| GPU | Quadro RTX 5000 on the host, not used by the harness; the model is served elsewhere (below) |
| Python | 3.13 (backend container) |
| Lockfile | `web/backend/uv.lock` |
| Container | one-off `backend` containers, image `ghcr.io/astral-sh/uv:python3.13-bookworm` (`sha256:47965cdc9d53a515f68f78241161c901e70051ce428f12e791bd7fe19f6a631a`), research folder mounted writable, run as the host user |
| Database | `mycelium_sandbox_exp019` on the stack's Postgres (pgvector/pg17), a copy of `mycelium_sandbox` |
| Model | the instance's relay model `default-model` (`LLM_MODEL`), reached through the compose network. Round one recorded it as Qwen 3.8 27B; it now self-reports as Google-trained. Its identity is **uncertain**; the record says `default-model` and nothing more |
| Concurrency | one Mylo turn at a time from this experiment (`--conc 1`, `AGENT_PARALLEL_CALLS=0`), so at most one model request in flight; the matcher's rerank calls run inside the turn, in sequence. Two other agents shared the model servers (night cap 8 in flight in all) |
| Nightly | `mylo-daily.timer` fires at 12:00 UTC (07:00 EST); every model run here was scheduled to end by 11:15 UTC — see "Overlap" below |
| Total wall clock | filled after the run |

## Where the time went

Filled after the run.

## Overlap with the nightly

Filled after the run.

## Anything about the hardware that affects the claim

Turn latency depends on the shared servers' load (the coordinator reported
40–70 s per turn tonight); that set the number of repetitions (PROTOCOL.md
"Scale"). Nothing graded depends on latency.
