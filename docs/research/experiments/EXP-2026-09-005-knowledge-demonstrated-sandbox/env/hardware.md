# Hardware and environment

| Field | Value |
|---|---|
| CPU | 20 cores (host), shared by the backend container |
| RAM | 62 GB |
| GPU | Quadro RTX 5000 16 GB on the host, unused by this run — the embedder ran on CPU inside the container |
| Python | 3.13 (backend container) |
| Lockfile | `web/backend/uv.lock` |
| Container | the stack's `backend` service, built from `web/backend` at the commits in `manifest.yaml` |
| Model | `default-model` via the `llm-tunnel` relay on port 9090, upstream `gemma4-26B-mtp`, served off this host |
| Total wall clock | about 42 minutes: corpus 3.7 min, arm A 5 min of reading, arm B 4.4 min, the six-point sweep 13 min, plus seeding and scoring |

## Where the time went

Writing the corpus (1,099 model calls, 12 at a time) and reading it (about
1,100 calls per arm, 12 at a time, 2.4–2.5 s each) dominate; the declared
projection over 336 subjects took 18.5 s. Each re-link in the sweep (no model
calls, all embedding and database work) took about two minutes for 240 people.

## Anything about the hardware that affects the claim

Only wall clock. The metrics are counts against planted truth and do not
depend on speed.
