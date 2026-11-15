# Hardware and environment

| Field | Value |
|---|---|
| CPU | Intel Xeon Silver 4114 @ 2.20 GHz, 20 logical CPUs (host `sc-zeus`) — runs the harness, the database, query embeddings (ONNX, CPU) and the agent loop |
| RAM | 62 GB |
| GPU (model) | remote, behind the instance's `llm-tunnel` relay: `default-model` (the instance model Mylo uses, for 5a's repairs) and `default-model-2` (the second model, 5c's reader). See "Which model" below. |
| GPU (local) | one NVIDIA Quadro RTX 5000, 16 GB, serving the decision model; not used by this experiment |
| Python | 3.13 in the backend image |
| Lockfile | `web/backend/uv.lock` |
| Container | one-off backend containers (`docker compose run --rm --no-deps -T backend …`), run as the host user, research folder mounted writable, `AGENT_PARALLEL_CALLS=0` |
| Model settings | instance defaults (temperature, reasoning style and caps as configured in `mycelium.toml`; nothing changed for the run) |
| Total wall clock | filled in RESULTS.md from `data/runs.jsonl` timestamps |

## Which model

Round one (`EXP-2026-11-013`) recorded the instance model as Qwen 3.8 27B on
one A100 80GB. On 2026-11-15 the relay had been reconfigured: `default-model`
now describes itself as trained by Google (Gemma-like reasoning output). The
relay does not expose the upstream model's name, size, quantisation or server
version, so **the instance model for this experiment is unknown beyond that
self-report**, and it may not be the model round one measured. Self-reports
are not reliable identification; they are recorded because nothing better is
available. The forced drafts were written by round one's model; the repairs here are by
tonight's instance model.

**Second model (5c reader):** relay model `default-model-2`, passed to the
reader's container only (`EVAL2_LLM_*`; the key is the instance's own
`LLM_API_KEY`, read from `.env` in the shell and never written down). It
describes itself as Qwen, trained by Alibaba, and serves a different usage
format from `default-model`, so it is taken to be a different model family
from the instance model. Its size and version are not exposed: unknown.

## What else used the model server

Two other agents ran round-two phases (EXP-2026-11-016, -017, -019) on the
same relay during this run; the night's total was capped at 8 requests in
flight, of which this experiment used at most 3 (3 turns, each one model
call at a time). The nightly run (`mylo-daily.timer`, 12:00 UTC) did **not**
overlap: every model run of this experiment finished before 11:15 UTC.

## Anything about the hardware that affects the claim

Latency depends on the shared server's load and is reported only as context.
Repair seconds depend on the shared server's load and are context only;
5b makes no model call.
