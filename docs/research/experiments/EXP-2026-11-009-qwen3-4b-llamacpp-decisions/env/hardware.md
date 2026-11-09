# Hardware and environment

| Field | Value |
|---|---|
| CPU | AMD Ryzen AI MAX+ 395 |
| RAM | 121 GB (unified; Vulkan reports 128 GB device memory) |
| GPU | AMD Radeon 8060S, RADV STRIX_HALO, Vulkan; `-ngl 99` |
| Python | 3.13, host venv `~/.cache/mycelium-backend-venv` |
| Lockfile | `web/backend/uv.lock` |
| Container | none — `llama-server` b11912 prebuilt Vulkan on the host, `-c 32768 -np 8` |
| Total wall clock | 87.5 s main pass + determinism + ~12 s throughput |

## Where the time went

Prompt evaluation (~1,000 tokens/s on this GPU); one output token per question.
llama-server's prompt cache reuses the shared state across a pair's questions.

## Anything about the hardware that affects the claim

Integrated GPU with unified memory; a discrete card would change throughput but
not the saturation finding.
