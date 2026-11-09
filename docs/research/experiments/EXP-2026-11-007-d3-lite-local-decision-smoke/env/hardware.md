# Hardware and environment

| Field | Value |
|---|---|
| CPU | AMD Ryzen AI MAX+ 395 |
| RAM | 121 GB |
| GPU | AMD Radeon 8060S (integrated); the Decisions server reports device `cuda`, bfloat16, 6.7 GB (ISSUES.md 2) |
| Python | 3.13 in the backend container (extract); host `python3` stdlib (decide, analyse) |
| Lockfile | `uv.lock` (container); none needed on the host |
| Container | Mycelium `backend` compose service for `extract.py`; the model server runs on the host, outside this repository |
| Total wall clock | ~66 s main pass (sequential) + 15 determinism calls |

## Where the time went

All in model calls: server-side p50 367 ms, p95 551 ms per pair (three or four
questions per call).

## Anything about the hardware that affects the claim

Latency is for this integrated GPU and one call at a time; a discrete GPU or
concurrent requests would change it.
