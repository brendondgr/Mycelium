# Hardware and environment

| Field | Value |
|---|---|
| CPU | Intel Xeon Silver 4114 @ 2.20 GHz, 20 logical CPUs (host `sc-zeus`) |
| RAM | 62 GB |
| GPU | none on this side; the paraphrase copies were written by Qwen 3.8 27B on vLLM, one NVIDIA A100 80GB (remote, reached through the instance's `llm-tunnel` relay as `default-model`; quantisation not exposed by the relay — unknown) |
| Python | 3.13 in the backend image |
| Lockfile | `web/backend/uv.lock` |
| Container | one-off backend container, `ghcr.io/astral-sh/uv@sha256:47965cdc9d53a515f68f78241161c901e70051ce428f12e791bd7fe19f6a631a` |
| Total wall clock | census and rebuild ~1 min; injection ~5 min |

## Where the time went

Rebuilding seven packets (database), then 29 paraphrase calls.

## Anything about the hardware that affects the claim

Nothing: the checks are deterministic. The nightly run was in progress on the
same model server while the paraphrases were written.
