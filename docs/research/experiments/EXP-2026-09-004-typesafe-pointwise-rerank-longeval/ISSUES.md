# EXP-2026-09-004 — Issues

1. **Dirty tree.** The arms (`eval/harness/typesafe_rerank.py`), their configs,
   tests and this folder were uncommitted when the manifest was scaffolded; they
   are committed together with the run.
2. **Different host from the record.** Every earlier LongEval number came from a
   32-core, 130 GB machine with no GPU. This host has 20 cores, 62 GB and a
   16 GB GPU. The BM25 baseline is therefore re-run here so the paired analysis
   compares arms from one corpus build; the committed baseline rows are quoted
   for context, never paired against.
3. **Corpus cache built from scratch.** `data/eval-cache/` did not exist on this
   host; the 2026 registration downloads all three 2026 snapshots (~2.8 GB
   compressed) even though only `snapshot-1/train` is used.
4. **Qrels are click-derived** (`dctr`), not human assessment. Every table says
   so. The 492-query human-assessed snapshot runs only if the primary holds.
5. **Provider determinism is undocumented.** Measured in-run (`code/determinism.py`);
   `EXP-2026-09-003` saw a 0.03 spread on the same question type.
