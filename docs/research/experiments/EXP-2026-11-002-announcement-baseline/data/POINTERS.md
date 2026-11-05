# Pointers — artifacts stored outside this folder

| Artifact | Path | Hash | Notes |
|---|---|---|---|
| Measures | `data/metrics.json` (this folder) | sha256:a8ffc70ad655e12fa879e6f06b7f93d3ec49d84045f9ea9c2f2d8471bd74e50c | `announcement_metrics` output for 2026-11-05. |
| Lab-fit labels | `data/labfit_labels.csv` (this folder) | sha256:41301cbe547bcfdca949aa2b1f98b975a1c2420fd1ff334bf1daa14a1f9c76db | One row per department-level call against PULSE Lab, agent-labelled. |
| Derived numbers | `data/derived.json` (this folder) | sha256:5df80e5a4d1880ce94d7a4e3b4bed1b6d85b461a76f217021f4332f2af1c6ce9 | Written by `summarize.py`. |
| Database copy | Postgres database `mycelium_ann` on the dev host | not-hashed: a live database copy, not a file | pg_dump of the dev database taken 2026-11-05, after the Phase 4–7 test-server smoke runs. |
