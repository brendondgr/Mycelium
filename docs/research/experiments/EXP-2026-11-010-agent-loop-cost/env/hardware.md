# Hardware and environment

| Field | Value |
|---|---|
| CPU | Intel Xeon Silver 4114 @ 2.20 GHz, 20 logical CPUs (host `sc-zeus`) — runs the harness, the database, query embeddings (ONNX, CPU) and the agent loop |
| RAM | 62 GB |
| GPU (model) | one NVIDIA A100 80GB on a remote host, serving **Qwen 3.8 27B** ("Heretic" build, as the relay reports `upstream_model`) on vLLM; reached through the instance's `llm-tunnel` SSH relay as model `default-model`. Quantisation and vLLM version are not exposed through the relay: unknown. Supports up to 128 concurrent requests (operator). |
| GPU (local) | one NVIDIA Quadro RTX 5000, 16 GB, serving the decision model; not used by this experiment |
| Python | 3.13 in the backend image |
| Lockfile | `web/backend/uv.lock` |
| Container | one-off backend containers, `ghcr.io/astral-sh/uv@sha256:47965cdc9d53a515f68f78241161c901e70051ce428f12e791bd7fe19f6a631a` (`python3.13-bookworm`), research folder mounted writable |
| Model settings | instance defaults: temperature 0.2, no output cap for the agent (`LLM_MAX_TOKENS` 8096 for other components), reasoning style `thinking` |

## What else used the model server

The nightly run (`mylo-daily.service`) was started by hand at 22:58 EST on
2026-11-12 and was running — calling the same model server and the decision
server — until it finished; see ISSUES.md for which runs overlapped it. This
session also ran its own experiments side by side (at most 8 agent turns in
flight across them). The relay does not expose the A100's queue, so other
tenants of that GPU, if any, are not visible from here.

## Anything about the hardware that affects the claim

Latency is the model server's and the network's; a turn's time is dominated
by model calls. Token counts are unaffected by load.
