# Hardware and environment

| Field | Value |
|---|---|
| CPU | AMD Ryzen AI MAX+ 395 |
| RAM | 121 GB |
| GPU | AMD Radeon 8060S (integrated); decide reports device `cuda`, bfloat16 |
| Python | 3.13, host venv `~/.cache/mycelium-backend-venv` |
| Lockfile | `web/backend/uv.lock` |
| Container | none — run on the host |
| Total wall clock | ~18 s of measured calls |

## Where the time went

All in the model call; the server serializes them behind GAIFA's GPU lease.

## Anything about the hardware that affects the claim

An integrated GPU shared with the rest of GAIFA. A discrete card or a batching
server (vLLM) would change both numbers and the shape of the curve.
