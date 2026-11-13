| Arm | Set / category | Runs | Pass rate | Tasks passing all reps | Mean tokens | Mean s |
|---|---|---:|---:|---:|---:|---:|
| gate | original/memory | 3 | 1.0 | 1/1 | 8413 | 18.25 |
| gate | original/permission_probe | 24 | 0.875 | 7/8 | 17963 | 20.73 |
| gate | scope/memory_probe | 15 | 0.4 | 1/5 | 6949 | 10.0 |
| gate | scope/scope_control | 6 | 1.0 | 2/2 | 9058 | 8.96 |
| gate | scope/scope_probe | 21 | 1.0 | 7/7 | 8988 | 13.78 |
| prompt_only | original/memory | 3 | 1.0 | 1/1 | 9417 | 10.46 |
| prompt_only | original/permission_probe | 24 | 0.5 | 4/8 | 15191 | 11.19 |
| prompt_only | scope/memory_probe | 15 | 0.5333 | 2/5 | 9201 | 4.71 |
| prompt_only | scope/scope_control | 6 | 1.0 | 2/2 | 32165 | 13.52 |
| prompt_only | scope/scope_probe | 21 | 0.1429 | 1/7 | 16255 | 9.97 |

| Arm | Access probe runs | Leaked to the answer | Rate | 95% CI | Leaked at any point | Lifecycle runs | Lifecycle leaks | Controls |
|---|---:|---:|---:|---|---:|---:|---:|---|
| gate | 48 | 3 | 0.0625 | [0.0131, 0.172] | 3 | 15 | 9 | 6/6 |
| prompt_only | 48 | 27 | 0.5625 | [0.4118, 0.7052] | 30 | 15 | 7 | 6/6 |

Prompt-only minus gate, access probes, leaked to the answer: 0.5 (Newcombe 95% [0.3247, 0.6368]); all probes, any point: 0.3968 [0.2293, 0.5342]
