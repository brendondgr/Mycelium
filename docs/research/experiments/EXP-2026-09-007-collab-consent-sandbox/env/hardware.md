# Hardware and environment

| Field | Value |
|---|---|
| CPU | 20 cores (host), shared by the backend container |
| RAM | 62 GB |
| GPU | none used |
| Python | 3.13 (backend container) |
| Lockfile | `web/backend/uv.lock` |
| Container | the stack's `backend` service |
| Model | none — no model is called; the embedder (`BAAI/bge-small-en-v1.5`, CPU) only links the planted conversational topics |
| Total wall clock | 29 s: planting 8.5 s, every check 20.2 s |

## Where the time went

Planting the matrix through the real code paths, and the simulated search
week (2,000 searches, each re-checking mutual visibility and the cap).

## Anything about the hardware that affects the claim

None: every number is a count against planted truth.
