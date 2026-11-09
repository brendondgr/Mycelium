| Worth AUC (on- vs off-theme) | Qwen3-4B (llama.cpp) | d3-lite (decide) |
| --- | ---: | ---: |
| All (n=45 pairs) | 0.4889 | 0.6899 |
| paper (n=15) | 0.4667 | 0.8267 |
| grant (n=15) | 0.5 | 0.5378 |
| conference (n=15) | 0.5 | 0.7644 |

Difference -0.201, 95% paired bootstrap [-0.2798, -0.1286] (2000 resamples, seed 0).

| Throughput (synthetic state) | Calls/s | p50 ms |
| ---: | ---: | ---: |
| 1 in flight | 7.189 | 139.2 |
| 4 in flight | 22.792 | 128.3 |
| 8 in flight | 13.427 | 672.9 |
