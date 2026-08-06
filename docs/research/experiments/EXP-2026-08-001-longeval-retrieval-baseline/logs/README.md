# Logs

No run logs were retained. The harness writes progress to stdout and the
provenance that matters — git SHA, dirty flag, config hash, corpus size, qrels
variant, wall-clock, embedding model — into the run file itself
(`eval/results/*.json`) and an `ir-metadata.yml` sidecar in `eval/runs/`.

The sidecars are gitignored and were regenerated after the fact, so they are not
a record of these runs. `data/POINTERS.md` says so explicitly rather than leaving
the gap silent.

Future runs: trim and commit stdout here if it carries anything the run file does
not.
