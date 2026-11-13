# Hardware and environment

| Field | Value |
|---|---|
| CPU | Intel Xeon Silver 4114 @ 2.20 GHz, 20 logical CPUs (host `sc-zeus`) |
| RAM | 62 GB |
| GPU | none used (the host has one NVIDIA Quadro RTX 5000, 16 GB, serving the decision model; not touched here) |
| Python | 3.13 in the backend image |
| Lockfile | `web/backend/uv.lock` |
| Container | one-off backend container, `ghcr.io/astral-sh/uv@sha256:47965cdc9d53a515f68f78241161c901e70051ce428f12e791bd7fe19f6a631a` (`python3.13-bookworm`) |
| Total wall clock | under a minute |

## Where the time went

Database counts only.

## Anything about the hardware that affects the claim

Nothing: no model was called and the counts do not depend on the host. The
nightly run (`mylo-daily.service`) was in progress during the pass.
