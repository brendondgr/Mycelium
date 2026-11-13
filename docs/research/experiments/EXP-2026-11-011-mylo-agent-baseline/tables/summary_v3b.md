| Arm | Set / category | Runs | Pass rate | Tasks passing all reps | Mean tokens | Mean s |
|---|---|---:|---:|---:|---:|---:|
| gate | original/memory | 3 | 1.0 | 1/1 | 9579 | 14.25 |
| gate | original/permission_probe | 24 | 0.875 | 7/8 | 20868 | 21.94 |
| gate | scope/memory_probe | 15 | 0.6 | 3/5 | 7105 | 3.64 |
| gate | scope/scope_control | 6 | 1.0 | 2/2 | 11007 | 6.95 |
| gate | scope/scope_probe | 21 | 1.0 | 7/7 | 8556 | 10.42 |

| Arm | Access probe runs | Leaked to the answer | Rate | 95% CI | Leaked at any point | Lifecycle runs | Lifecycle leaks | Controls |
|---|---:|---:|---:|---|---:|---:|---:|---|
| gate | 48 | 3 | 0.0625 | [0.0131, 0.172] | 3 | 3 | 0 | 6/6 |
