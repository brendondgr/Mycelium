# Hardware and environment

| Field | Value |
|---|---|
| CPU | AMD RYZEN AI MAX+ 395 (32 threads) |
| RAM | 121 GB |
| GPU | none (no model is called) |
| Python | 3.13 (uv-managed) |
| Lockfile | web/backend/uv.lock |
| Container | none — run on the host; the compose Postgres (port 11450) is used only for Django setup |
| Total wall clock | 1,226.3 s for the own arm (about 20 minutes); the stored arm (45 papers) and the PubMed efetch were not timed separately |

## Where the time went

Network-bound, as in `EXP-2026-11-004`: per-source throttles set the pace, CORE
without a key the slowest.

## Anything about the hardware that affects the claim

Only the network: the same home connection as `EXP-2026-11-004`, same day.
