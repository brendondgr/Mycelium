# Promoted Figures

A figure moves into `docs/research/figures/` only when it is destined for the
paper. Promotion copies the figure **and** its generator (into `sources/`), so
the manuscript can always be rebuilt from the record.

`make figures` reads this table. Add a row, run it, commit the result.

| Figure | Source experiment | Paper section | Caption |
|---|---|---|---|
| `fig-arm-comparison` | `EXP-2026-08-001` | §5 Retrieval substrate | Effectiveness per retrieval arm across three LongEval-Sci snapshots. BM25 alone leads on nDCG@10 in every snapshot. |
| `fig-pool-recall-gap` | `EXP-2026-08-002` | §5 Retrieval substrate | Recall cost of confining the lexical channel to the dense-retrieved pool, at two pool widths. |

`fig-baseline-gap` is deliberately **not** promoted: it is a correctness check on
our own implementation against the organizers' published runs, which belongs in
the experiment record and in a reproducibility appendix rather than in the paper
body.

## Rules

- Promotion is a copy, never a move. The experiment folder keeps its own copy —
  the experiment record must stay complete on its own.
- The generator lands in `sources/<EXP-ID>-make_figures.py` so the source
  experiment is recoverable from the filename alone.
- `make figures` regenerates everything from scratch; CI fails if the result
  differs from what is committed. If it fails, the figures are stale.
