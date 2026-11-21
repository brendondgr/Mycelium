# Hardware and environment

| Field | Value |
|---|---|
| CPU | Intel Xeon Silver 4114 @ 2.20 GHz, 20 logical CPUs (host `sc-zeus`): harness, database, query embeddings (ONNX, CPU) and the agent loop |
| RAM | 62 GB |
| GPU | none used locally; the model is served remotely behind the instance's `llm-tunnel` relay as `default-model`. Its GPU is not recorded here (unknown; the operator rates the server for 128 requests in flight) |
| Model | operator-stated Inkling 2 Mini, 26B total / 3B active, mixture of experts, NVFP4; relay `upstream_model: "Inkling 2 Mini"`; self-report "I am Inkling, developed by Thinking Machines Lab." (2026-11-21 17:2x UTC). Every part records the relay listing and self-report at its start and end (`data/raw/*/logs/model_*`, `data/raw/run/logs/preflight.jsonl`) |
| Python | 3.13 in the backend image |
| Lockfile | `web/backend/uv.lock` |
| Container | one-off backend containers (`docker compose run --rm --no-deps -T`), run as the host user; `tools/` and `web/backend/` mounted read-only from `git archive` snapshots of `44100c04`, `640d7fe0`, `a99e1a01`; `docs/research` mounted from a staged copy |
| Total wall clock | per part, in `data/raw/run/status.txt` |

## Anything about the hardware that affects the claim

The earlier models (Gemma 4 31B, Qwen 3.8 27B) ran W4A16 on one A100 80GB
(paper §4). Inkling runs NVFP4 on a different server, so latencies compare two
deployments, not two architectures alone.
