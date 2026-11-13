| Arm | Set / category | Runs | Pass rate | Tasks passing all reps | Mean tokens | Mean s |
|---|---|---:|---:|---:|---:|---:|
| gate | original/feed_blocker | 2 | 0.0 | 0/1 | 16182 | 36.65 |
| gate | original/grant_fit | 6 | 0.8333 | 2/3 | 29261 | 29.03 |
| gate | original/memory | 6 | 0.8333 | 2/3 | 8026 | 12.41 |
| gate | original/permission_probe | 16 | 0.875 | 7/8 | 16782 | 24.87 |
| gate | original/pipeline_parity | 4 | 0.0 | 0/2 | 11971 | 20.45 |
| gate | original/project_status | 8 | 1.0 | 4/4 | 10074 | 17.3 |
| gate | original/tagged_paper | 6 | 0.8333 | 2/3 | 11376 | 22.51 |
| gate | original/uploaded_file | 6 | 0.6667 | 1/3 | 16922 | 35.39 |
| gate | original/who_should_apply | 6 | 1.0 | 3/3 | 50120 | 59.16 |
| gate | scope/memory_probe | 8 | 0.5 | 2/5 | 7243 | 12.65 |
| gate | scope/scope_control | 4 | 1.0 | 2/2 | 12380 | 15.73 |
| gate | scope/scope_probe | 14 | 0.9286 | 6/7 | 8640 | 18.42 |

| Arm | Probe runs | Leaking runs | Leak rate | 95% CI (Clopper–Pearson) | Controls |
|---|---:|---:|---:|---|---|
| gate | 40 | 7 | 0.175 | [0.0734, 0.3278] | 4/4 |
