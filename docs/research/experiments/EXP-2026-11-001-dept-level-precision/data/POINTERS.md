# Pointers — artifacts stored outside this folder

| Artifact | Path | Hash | Notes |
|---|---|---|---|
| Labelled firings | `data/labels.csv` (this folder) | sha256:b3ae7edc24f90d3b057ede3d314aa1ca556fa163d9ad0d2db8c9bfa67267ee64 | Every v1 firing, one row per reason, with the label and a note. |
| Corpus snapshot | Postgres database `mycelium_ann` on the dev host | not-hashed: a live database copy, not a file | pg_dump of the dev database taken 2026-11-05; the opportunity corpus was collected 2026-08/09. 3,901 grant, fellowship and conference records. |
