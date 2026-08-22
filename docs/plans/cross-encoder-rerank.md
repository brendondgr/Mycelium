# Plan — cross-encoder rerank over the deployed dense pool

**Status:** in progress. Delete this file when the work ships and write the
outcome into `docs/changelog.md` + `docs/repo-map.md` (planner skill rule).

## Objective

Add a cross-encoder rerank stage to the deployed matching pipeline, over
**production's existing dense-restricted pool, unchanged**. Run it on a CUDA GPU
automatically when one is present and on the CPU otherwise, using the same model
either way.

**Model: `Xenova/ms-marco-MiniLM-L-6-v2`** (0.08 GB, ~22M params). Not chosen for
size — it is the **only reranker any human has judged on this corpus**.
`EXP-2026-08-014`, `-015`, `-016` and `-017` all used it; shipping any other model
ships a stage nobody has looked at. The five alternatives in fastembed 0.8.0
(`ms-marco-MiniLM-L-12-v2`, `bge-reranker-base`, three `jina-reranker` variants)
stay unshipped and remain the material for `Q-021`/`Q-023`.

## Evidence, and its limits

Three blinded preference reads by the product's own user, over two research areas
and four content types:

| Experiment | Result |
|---|---|
| `EXP-2026-08-015` | `fusion_dense_pool+xenc` 1st in papers, grants, conferences — **last in fellowships** |
| `EXP-2026-08-016` | same arm 1st in papers, grants, conferences on an unrelated area |
| `EXP-2026-08-017` | with the confound removed (both pools reranked): **5 wins, 3 ties, 0 losses** |

**This is a preference from one reader, not a relevance measurement.** C-013
remains refuted on LongEval-Sci; nothing here overturns it, and the two are
compatible because the reader judged *narrow dense-filtered pools*, which is the
regime where the reranker has never been shown to hurt. `Q-033` is the outstanding
question and this plan does not answer it — it ships a stage behind a flag, with
the flag's evidential basis written into the code comments.

## Assumptions and open questions

1. **The multi-interest query is the one thing the experiments did not test.**
   Every read used **one** query string. Production reranks a pool built from
   *several* declared interests, and cross-encoder scores are **not comparable
   across different queries**, so there is no single obvious query to hand it.
   Decided below (Phase 3, Decision A); it degrades exactly to the judged
   configuration when a target has one interest, and Phase 6 puts the choice in
   front of the reader rather than assuming it.
2. **Fellowships default OFF.** `EXP-2026-08-015` found this same reranker
   *worst* on healthcare fellowships, surfacing Tropical Medicine and Molecular
   Imaging for an AI-agents query — the corpus where the query's domain word is
   boilerplate. `Q-031`. This is a default, not a hard exclusion.
3. **No new tier gate.** Reranking is internal ranking quality, not a user-facing
   capability, so nothing is read through `billing.entitlements`. Stated
   explicitly because the planner skill requires every new capability to name its
   gate; this one has none by design, and if that is wrong it is wrong here.
4. **No new routes**, so the trailing-slash rule does not apply.
5. GPU is unavailable on this development host. Every CUDA branch is therefore
   exercised through injected fakes, exactly as `apps/scraper/tests/
   test_embedding_device.py` already does — no test may import onnxruntime.

## Phases

### Phase 0 — baseline, so "no change" is provable

Capture the current eval-harness numbers before touching anything. The gate for
the whole change is that **with the flag off, every committed run reproduces
byte-identically**.

- `uv run --project eval python eval/report.py` (or re-score committed runs) and
  save the output under `/tmp` for comparison.
- Record current `make validate-research` state (17 experiments) and the test
  suite baseline.

**Validation:** baseline captured; `uv run --project web/backend pytest` passes
apart from the two known pre-existing failures (`test_site_and_resume_merge`,
`test_high_signal.py::test_command_delivers_when_enabled`).

### Phase 1 — `apps/content/reranking.py`: device handling

Mirror `apps/scraper/embedding.py` rather than invent a second device story.
`fastembed.rerank.cross_encoder.TextCrossEncoder.__init__` takes the identical
`cuda` / `device_ids` / `threads` / `lazy_load` arguments as `TextEmbedding`, so
the port is mechanical.

- `cuda_available()` — reuse `apps.scraper.embedding.cuda_available` (one seam,
  not two).
- `resolve_device()` — reads `RERANK_DEVICE`, **defaulting to `EMBEDDING_DEVICE`**
  so a host configured once is configured for both. `auto` → CUDA when present,
  `cuda` → warn and fall back if absent, `cpu` → pin.
- `_build_model()` — CUDA attempt wrapped in `try/except`, falling back to CPU on
  any session failure. A driver mismatch must degrade a nightly run, never crash
  it — the rule already established for the embedder.
- Process-wide lazy cache keyed by `(model, device, device_id)`, with
  `reset_rerank_cache()` for tests.
- `default_batch_size(device)` from `RERANK_BATCH_SIZE_CPU` / `_GPU`.
- `describe_device(load=False)` for diagnostics.

**Validation:** `uv run --project web/backend pytest apps/content/tests/test_rerank_device.py`
— device resolution, unknown-value fallback, CUDA-requested-but-absent warning,
CUDA-session-failure fallback, batch size per device, cache reuse. All through an
injected fake; no onnxruntime import.

### Phase 2 — the rerank stage, ORM-free and testable without a model

A pure function in the same module, with the scorer injected:

```python
def rerank(query: str, items: Sequence[Retrievable], *, score, depth: int) -> list[str]
```

- Scores only the top `depth`; everything below keeps its incoming order and sits
  underneath. A reranker that cannot see rank 200 must not be able to move it.
- **Deterministic tie-break by document id** — `EXP-2026-08-003` ISSUES records
  the trap: a tie order that depends on set iteration is not a ranking, it is a
  hash.
- Text per item is `apps.content.lexical._item_text`, the same text BM25 indexes,
  so the reranker and the lexical channel see one document.
- Empty input, empty query, and a `None` scorer each return the input order
  unchanged — the "every missing capability degrades to a status, not a crash"
  convention.

**Validation:** `pytest apps/content/tests/test_reranking.py` with a stub scorer —
ordering, depth boundary, tie determinism, no-op paths. No model, no database.

### Phase 3 — wire it into the shared fusion path

One insertion point, not two, so personal / lab / project parity holds by
construction: the tail of `fuse_interests_pool` **and** `fuse_clusters_pool` in
`apps/content/pipeline.py`, gated by content type.

**Decision A — the multi-interest query.** Rerank **per interest** over that
interest's own contributions, then merge the reranked orderings by **RRF**
(`fusion.DEFAULT_RRF_K`, the constant the codebase already fuses with), with the
pre-rerank combined score as the tiebreak.

- Cross-encoder logits are not comparable across queries, so a single merged
  score is not available; ranks are.
- The codebase already fuses by rank, so this adds no new idea.
- **With one interest it reduces exactly to the configuration that was judged** —
  one query, one list, one rerank — which is the property that makes it the
  defensible default.
- Cost is bounded by `n_interests × depth` pairs. `RERANK_DEPTH` (default 50,
  matching every experiment) and a `RERANK_MAX_PAIRS` ceiling keep a 22-interest
  profile from running away.

Also: reorder `fuse_clusters_pool`'s `slate_groups` with the **same** scores, so
the per-theme slate and the global list cannot disagree about which paper is
better.

Record the rerank rank and score in the `signals` dict via `_fusion_row`, so the
audit trail shows what moved and why.

**Consequences to state plainly** — reranking `pairs` changes three things
downstream, all intended:
1. **Top-25 slate membership** (`entering = pairs[:top_n()]`) — i.e. what the
   product calls *new*.
2. **Which items get an LLM write-up** (`generate_suggestions(llm_limit=…)`) — the
   reranker decides where the model's budget goes.
3. Display order.

**Validation:** `pytest apps/content` against the Compose Postgres
(`DATABASE_URL=…@localhost:11450`, since pgvector tests skip on SQLite), plus a
new test asserting **the flag off is byte-identical to today** on a fixture pool.

### Phase 4 — settings, diagnostics, docs

- `config/settings.py`: `RERANK_ENABLED`, `RERANK_MODEL`, `RERANK_DEVICE`
  (defaults to `EMBEDDING_DEVICE`), `RERANK_DEVICE_ID`, `RERANK_DEPTH`,
  `RERANK_MAX_PAIRS`, `RERANK_BATCH_SIZE_CPU`, `RERANK_BATCH_SIZE_GPU`,
  `RERANK_CONTENT_TYPES` (default `paper,grant,conference` — fellowships off, see
  Assumption 2). Each with a comment carrying the evidence and its limits.
- `.env.example` entries.
- `apps/content/management/commands/rerank_device.py`, mirroring
  `embedding_device` — prints requested/resolved device, available providers, and
  with `--load` the live session's providers. This is how the GPU gets confirmed
  on the real server.
- `pyproject.toml`: nothing new. `fastembed` is already an optional extra and
  `fastembed-gpu` already exists for CUDA.
- Docs: `docs/repo-map.md` row, `docs/changelog.md` entry, and a line in
  `docs/evaluation.md`'s claims boundary recording that the shipped stage rests on
  a **preference**, not a measurement.

**Validation:** `uv run --project web/backend python manage.py rerank_device`
prints `cpu` here and would print `cuda` on the server; `make validate-research`
still passes.

### Phase 5 — the flag-off invariant, and the re-run rule

`docs/skills/global.md` requires a fresh evaluation run for any change to
`pipeline.py`'s ranking path, recorded in an experiment folder.

- **Flag off ⇒ byte-identical.** Re-run the harness arms and diff against the
  committed run files. Any difference is a bug in the wiring, not a result.
- **Flag on ⇒ record it.** A new experiment folder capturing the reranked arm on
  the production store and the wall-clock cost per target on CPU, pointing at
  `EXP-2026-08-015/016/017` for the preference basis.

**Validation:** committed run files reproduce exactly with the flag off;
`make research-ci` passes.

### Phase 6 — put Decision A in front of the reader

Decision A is the only part of this change with **no** human read behind it,
because every experiment used a single query. A fifth booklet, same format and a
fresh blinding: per-interest + RRF against a single concatenated-interest query,
on a real multi-interest profile.

Not a blocker for shipping behind a flag — it is the thing to run before the flag
goes on by default for a real user.

## Interfaces that change

| Surface | Change |
|---|---|
| `apps/content/reranking.py` | **new** — device resolution, model cache, `rerank()` |
| `apps/content/pipeline.py` | `fuse_interests_pool` / `fuse_clusters_pool` gain an optional rerank tail |
| `apps/content/management/commands/rerank_device.py` | **new** — diagnostics |
| `config/settings.py`, `.env.example` | eight new settings, all defaulted |
| `RelevanceScore.signals` | gains `rerank_rank` / `rerank_score` when the stage runs |
| REST API | **no route or schema change**; ordering changes, shape does not |

## Explicitly out of scope

- Any other reranker model (`Q-021`, `Q-023`).
- The union pool and the SPLADE channel — `Q-034` records the decision not to
  build them: three blinded reads, nothing won, against ~23 min of one-time
  encoding plus a second index maintained forever.
- Changing the pool, the fusion, the 0.15 interest floor, `PAPER_MATCH_THRESHOLD`,
  or the freshness gate.
- The cosine-gate fix from C-019 — a separate change with its own evidence
  (`Q-025`).
- Turning the flag on by default for real users, which waits on Phase 6.
