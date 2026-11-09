# Hardware and environment

| Field | Value |
|---|---|
| CPU | AMD Ryzen AI MAX+ 395 |
| RAM | 121 GB (unified with the GPU) |
| GPU | AMD Radeon 8060S (gfx1151), integrated; one |
| Python | Arm A 3.12.13 in GAIFA decide's venv (torch `2.15.0a0+rocm10.2.0a20260926`); arm B and the dump 3.13 in the host venv `~/.cache/mycelium-backend-venv` |
| Lockfile | `web/backend/uv.lock` (arm B, dump); GAIFA `services/decide/requirements.txt` (arm A) |
| Container | none — run on the host |
| Total wall clock | arm A ~11 min (each configuration run twice: untimed, then timed), arm B ~6 min |

## Where the time went

Arm A: prompt passes over the real states (~66–74 s per timed configuration).
Arm B: prompt evaluation in llama.cpp; one output token per question.

## Anything about the hardware that affects the claim

On an integrated GPU, compute is the limit for both models at production state
lengths. A discrete card would change the absolute numbers; whether it would
change the ordering was not tested. d3-lite ran without the
`flash-linear-attention` / `causal_conv1d` kernels (transformers fell back to
reference PyTorch), as GAIFA's decide does.
