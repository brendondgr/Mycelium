| Arm | Set / category | Runs | Pass rate | Tasks passing all reps | Mean tokens | Mean s |
|---|---|---:|---:|---:|---:|---:|
| gate | original/memory | 3 | 1.0 | 1/1 | 9579 | 14.25 |
| gate | original/permission_probe | 24 | 0.875 | 7/8 | 20868 | 21.94 |
| gate | scope/memory_probe | 15 | 0.6 | 3/5 | 7105 | 3.64 |
| gate | scope/scope_control | 6 | 1.0 | 2/2 | 11007 | 6.95 |
| gate | scope/scope_probe | 21 | 1.0 | 7/7 | 8556 | 10.42 |
| prompt_only | original/memory | 3 | 1.0 | 1/1 | 10525 | 13.79 |
| prompt_only | original/permission_probe | 24 | 0.5 | 4/8 | 14664 | 19.43 |
| prompt_only | scope/memory_probe | 15 | 0.6 | 3/5 | 8768 | 4.84 |
| prompt_only | scope/scope_control | 6 | 1.0 | 2/2 | 16838 | 12.13 |
| prompt_only | scope/scope_probe | 21 | 0.1429 | 1/7 | 16103 | 13.47 |

| Arm | Access probe runs | Leaked to the answer | Rate | 95% CI | Leaked at any point | Lifecycle runs | Lifecycle leaks | Controls |
|---|---:|---:|---:|---|---:|---:|---:|---|
| gate | 48 | 3 | 0.0625 | [0.0131, 0.172] | 3 | 3 | 0 | 6/6 |
| prompt_only | 48 | 28 | 0.5833 | [0.4321, 0.7239] | 30 | 3 | 0 | 6/6 |

Prompt-only minus gate, access probes, leaked to the answer: 0.5208 (Newcombe 95% [0.3449, 0.6554]); all probes, any point: 0.5294 [0.3599, 0.6595]
