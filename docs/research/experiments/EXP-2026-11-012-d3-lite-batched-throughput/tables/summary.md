Pairs per second (one pair = one state with all of its questions).

| State | Parallelism | d3-lite, decide server | d3-lite, in-process | Qwen3-4B, llama.cpp |
| --- | ---: | ---: | ---: | ---: |
| synthetic (48) | 1 | 7.132 | 8.288 | 7.189 |
| synthetic (48) | 4 | 7.993 | 11.806 | 22.792 |
| synthetic (48) | 8 | 8.56 | 10.976 | 13.427 |
| real (165) | 1 | — | 2.319 | 1.799 |
| real (165) | 4 | — | 2.219 | 1.495 |
| real (165) | 8 | — | 2.258 | 1.594 |

Parallelism: requests in flight (decide server, llama.cpp) or pairs per forward pass (d3-lite in-process). In-process one-pair-at-a-time (`system_one`): synthetic 7.429, real 2.498.

| Batched vs sequential answers | max abs diff |
| --- | ---: |
| synthetic, 4 per pass | 0.000751 |
| synthetic, 8 per pass | 0.000979 |
| real, 4 per pass | 0.034668 |
| real, 8 per pass | 0.033518 |
