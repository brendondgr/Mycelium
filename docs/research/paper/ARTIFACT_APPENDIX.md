# Artifact Appendix

Started early on purpose: the appendix is ~2 pages and mostly assembles from
`manifest.yaml` plus `PROTOCOL.md`, so writing it now costs little and reveals
what is missing while there is still time to fix it.

## Badges, and where we stand

Most ACM/USENIX venues award three:

| Badge | Requirement | Status |
|---|---|---|
| **Available** | Artifact deposited in a public archival repository with a DOI | **Not met.** GitHub alone does not satisfy this — an archival DOI from Zenodo, Figshare, or Dryad is required. Not yet minted. |
| **Functional** | Documented, consistent, complete, exercisable | **Partially met** for the retrieval stack: `uv.lock`, Docker Compose for the full stack, a documented README, 1,379 offline-runnable tests, and a one-command evaluation harness. Not met overall — see blockers. |
| **Results Reproduced** | An independent committee re-obtains the main results within tolerance | **Met for `EXP-2026-08-001` and `EXP-2026-08-002`** in principle: the collection is openly downloadable, the arms are deterministic, and the entrypoint plus commit are recorded. Untested by anyone outside the project. |

## What a reproducer needs

| Requirement | Provided | Where |
|---|---|---|
| Source at a fixed commit | Yes | `code.commit` in every manifest |
| Pinned environment | Yes | `eval/uv.lock`, `uv.lock`; Compose for the full stack |
| Data | Yes, for LongEval | `pip install ir-datasets-longeval`; ~2.8 GB download |
| Exact commands | Yes | `code.entrypoint`, and PROTOCOL.md §Procedure |
| Hardware | Recorded | `compute.hardware` — CPU-only, 32 cores, 130 GB RAM, no CUDA |
| Expected runtime | Recorded | `compute.wall_clock_hours`, per-run `wall_clock_s` in `eval/results/*.json` |
| Metric definitions | Yes | Standard `ir_measures` calls; never hand-rolled |
| Tolerance | Deterministic arms → exact match expected | See "Nondeterminism" below |

## Blockers to full reproduction

1. **No archival DOI.** Blocks *Available*. Cheap to fix; must be done before
   submission.
2. **The opportunity corpus is not redistributable.** Pivot-RP is behind
   institutional SSO. Any experiment resting on grants or fellowships is
   unreproducible until W10 rebuilds the corpus from open sources.
3. **`LLM_MODEL` is unpinned and `LLM_TEMPERATURE` defaults to 0.2.** The
   scoring layer has no recorded identity and varies run to run. No experiment in
   this record touches it — and none can, until W1 lands.
4. **No seeds in the production matching path.** Retrieval is deterministic so
   the current numbers are unaffected, but this must be fixed before any
   stochastic experiment.
5. **Full-corpus runs are expensive.** The 2026 snapshot is 869,902 documents
   embedded on CPU; a full-corpus arm takes hours. Pooled runs are the cheap
   path and are labeled as such — they are re-ranking evaluations and their
   recall numbers do not transfer.

## Nondeterminism

The recorded retrieval arms are deterministic: fixed embeddings, exact
similarity (no ANN index in production, so the harness's in-memory index computes
an identical ranking, not an approximation), and deterministic BM25 and RRF. A
reproducer should get identical numbers, not numbers within tolerance. Any
divergence indicates a version drift in `ir-datasets-longeval` or `fastembed`,
both pinned in `eval/uv.lock`.

Nothing in this record calls an LLM. When one does, the manifest's `llm` block
must carry the model version, temperature, prompt hash, token counts, and an
explicit note that provider-side nondeterminism persists at temperature 0 — so
results are reported as mean ± std over `n_runs`.

## Checklist mapping

Venue reproducibility checklists ask for datasets, hyperparameters and the ranges
searched, number of runs and seeds, metric definitions, and compute
infrastructure. Every one is already a manifest field:

| Checklist item | Manifest field |
|---|---|
| Dataset and version | `data.name`, `data.version`, `data.split`, `data.n_examples` |
| Hyperparameters | `config.path` + `config.hash` |
| Runs and seeds | `n_runs`, `seeds` |
| Metric definitions | `metrics.primary`, `PROTOCOL.md` §Metrics |
| Compute | `compute.hardware`, `compute.wall_clock_hours` |
| Code version | `code.commit`, `code.branch`, `code.dirty` |
| Environment | `environment.python`, `environment.lockfile` |

Filled per-venue copies go in [`checklists/`](checklists/).
