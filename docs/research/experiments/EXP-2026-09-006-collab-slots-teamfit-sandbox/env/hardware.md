# Hardware and environment

| Field | Value |
|---|---|
| CPU | 20 cores (host), shared by the backend container |
| RAM | 62 GB |
| GPU | Quadro RTX 5000 16 GB on the host, unused — the embedder ran on CPU inside the container |
| Python | 3.13 (backend container) |
| Lockfile | `web/backend/uv.lock` |
| Container | the stack's `backend` service |
| Model | `default-model` via the `llm-tunnel` relay on port 9090, upstream `gemma4-26B-mtp`, served off this host |
| Total wall clock | about 35 minutes over three arms and the sweep |

## Where the time went

Writing the 150 calls took about two minutes; reading them, 12–14 s per arm
(151 model calls, 12 at a time). The team-fit phase dominates: about 33 s for
48 labs and 160 s for 240 people, each against 150 calls — 43,200 score rows
per arm, all embedding and database work, no model calls.

## Anything about the hardware that affects the claim

Only the wall clock (H5). The agreement numbers are counts against planted
truth.
