# EXP-2026-09-009 — Issues

1. **Dirty tree at scaffold.** `make new-experiment` ran while EXP-2026-09-008's
   rebuilt world and CN-04's docs were uncommitted; the manifest's commit is
   corrected to the run's commit when results are recorded.
2. **Resized before the run to fit an hour (amended 2026-09-18, pre-run).**
   The owner asked that no experiment run longer than an hour while the model
   server is under heavy load. As registered (120 seekers, every search
   reranked by the model, own words for every fourth) the run would take about
   three hours. Changed before any panel run: 60 seekers; the model reranks
   the first 10 seekers' searches and the rest run with the rerank off (the
   API must answer identically in shape either way, and the rerank's quality
   is EXP-2026-09-008's question); own words for every sixth seeker; 20 calls
   read by the model; a 45-minute wall-clock budget covering the whole run,
   which stops the seeker loop early and reports `stopped_at_deadline`. The
   hypotheses and their bars are unchanged.
