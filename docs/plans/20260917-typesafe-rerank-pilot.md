# TypeSafe (Jev) Pointwise Rerank Pilot — Implementation Plan

**Status:** Phase 0 built (client, command, tests, dependency, settings); the
first experiment (`EXP-2026-09-003`) has **run and is recorded**; the LongEval
rerank experiment below is next.

**Order change (2026-09-17):** at the reader's request the first live run is
`EXP-2026-09-003`, one reader's own grant and conference slates — 57 (theme,
item) pairs, three typed questions each — so there is something to evaluate by
hand while the LongEval work below (now the second experiment) is set up. That
run sends the reader's own profile text at their instruction; the privacy
exclusion below stays in force for every other account.
**Correlation ID:** `20260917-typesafe-rerank-pilot`
**Scope:** prototype and measurement only. Nothing here reaches a production
path, a feed, a report, or a reader.

## Objective

Try TypeSafe's Jev model as a **pointwise reranker** inside the existing
evaluation harness, on public LongEval-Sci data, and record three things the
research record currently lacks:

1. Whether a calibrated probability per (query, document) pair orders a scholarly
   feed better than the first stage it reranks — the question every reranker in
   this record has so far answered "no" to (C-013 refuted, C-015 supported,
   C-016 refuted).
2. Whether a continuous probability-weighted score fixes the specific failure
   behind C-016: the 0–3 LLM rubric collapsed a 20-candidate window to 1.99
   distinct values and was non-monotonic in judged grade.
3. What it actually costs and how long it takes, from the `usage` block the API
   returns, not from the price sheet.

It also answers Q-021 and Q-023 in passing: those ask for one reranker **not**
trained on MS MARCO. Jev is that.

## Where the key goes

Put the key in the repository root `.env`, which already exists and is
gitignored:

```
TYPESAFE_API_KEY=<key>
```

Reason: `web/backend/config/settings.py` reads the root `.env` via
`environ.Env.read_env`, and `eval/run.py` bootstraps those same settings, so one
line serves the management command, the eval harness, and every future host
process. No compose or container wiring is needed for this pilot because nothing
in it runs inside a container. `.env.example` gets a commented block describing
the three variables below, with the key left blank.

## Assumptions and open questions

- **Access.** The launch post describes early access behind a waitlist. The
  plan cannot start until a key from `console.typesafe.ai` exists. Everything in
  Phase 0 except the live smoke test can be written and tested offline first.
- **Determinism is undocumented.** The harness pins temperature 0 because an
  unreproducible reranker is unmeasurable. Phase 3 includes a repeat-call check
  and records the spread before any metric is trusted.
- **State-size limit is undocumented.** Per-pair calls keep the state to a query
  plus a 600-character abstract, well inside anything the cookbooks demonstrate.
- **Model pin.** Every call uses `jev-1.13.0`, never the `jev-latest` alias, so
  the manifest names the thing that answered.
- **Hardware differs from the record.** Earlier experiments ran on 32 cores and
  130 GB with no GPU. This host has 20 cores, 62 GB and a 16 GB Quadro RTX 5000.
  The BM25-based arms need no vectors, which is why they come first. The corpus
  cache (`data/eval-cache/`) does not exist here and must be built.
- **Privacy.** Only LongEval-Sci text and a hand-written smoke-test string are
  ever sent. No profile, project, or `ContentItem` row leaves the host under this
  plan. Any later phase that would send reader data needs the data processing
  agreement read first and is explicitly excluded here.

## Phases

### Phase 0 — dependency, client, smoke test

1. Add `typesafe-sdk>=0.6,<1` to `web/backend/pyproject.toml` and mirror it in
   `eval/pyproject.toml` (the harness mirrors backend deps by rule). Run
   `uv lock` in both.
2. New module `web/backend/apps/core/systemone.py`, shaped like `llm.py`:
   - `SystemOneConfig` from settings: `TYPESAFE_API_KEY`, `TYPESAFE_MODEL`
     (default `jev-1.13.0`), `TYPESAFE_TIMEOUT` (default 10.0 s),
     `TYPESAFE_MAX_RETRIES` (default 0, retries belong to the caller).
   - `SystemOneClient` with a **lazy** `typesafe_sdk` import and an
     **injectable transport** (a callable with the `system_one` signature) so
     tests run offline.
   - Every call records into the existing ledger via
     `apps.core.llm_usage.record(component, ok=…, usage={"input_tokens": …,
     "output_tokens": …})`. The ledger already accepts both key spellings, so
     no migration.
   - A `SystemOneConfigurationError` when the key is missing, raised before any
     network call.
3. Settings block in `config/settings.py` next to the `LLM_*` group; commented
   block in `.env.example`.
4. Management command `typesafe_check`, the twin of `llm_check`: one Noul over a
   fixed string, prints the probability, `request_id`, tokens and wall time.
   Exit non-zero on any failure.
5. Tests in `apps/core/tests/`: config coercion, missing-key error, ledger write
   on success and failure, transport injection. All offline.

**Validate:** `uv run --project web/backend pytest web/backend/apps/core -q`,
then with the key present `uv run --project web/backend python web/backend/manage.py typesafe_check`.
The smoke test reports reachability only; no number from it is quoted anywhere.

### Phase 1 — two eval arms

In `eval/harness/llm_rerank.py`, alongside the three LLM arms and registered in
the same `LLM_ARMS` table:

- `typesafe_noul` — one call per (query, document) pair, TypeSafe's own
  re-ranking cookbook shape. State
  `{"query": <query text>, "candidate": {"title": …, "abstract": …}}`, one
  `Noul` with explicit `true` / `false` criteria written for topical relevance
  to a scholarly query. Order the window by `noul` descending, base rank as the
  tiebreak, exactly as `llm_rubric` does.
- `typesafe_score` — same state, one four-level `Score` whose level texts are
  the 0–3 rubric from `_rubric_prompt`, so C-016 is re-tested like for like with
  a continuous `score` instead of an emitted integer.

Both arms:

- take `base`, `window` (default 20, matching `llm_rubric`) and `model` from
  `[params]`; refuse to run if `model` resolves to an alias.
- run under `ThreadPoolExecutor(CONCURRENCY)`; the documented limit is 1,200
  requests per minute, and 12 workers stay far under it.
- on any exception keep the base order for that pair and count it, as the LLM
  arms do. A failed call is recorded, never hidden.
- dump raw answers (`noul` or `score`, `probabilities`, `confidence`,
  `input_tokens`) to `eval/runs/typesafe_<arm>_scores.json`, the same pattern as
  `llm_rubric_scores.json`, because the ranking alone cannot answer the
  discrimination question.
- sum `usage.input_tokens` and `output_tokens` and print them at the end of the
  run; the experiment copies them into the manifest's `llm` block.

Configs: `eval/configs/typesafe_noul_bm25.toml`, `typesafe_score_bm25.toml`
(base `bm25_only`), and `typesafe_noul_fusion.toml` (base `fusion_union_pool`,
for the like-for-like contrast with `llm_rubric`, run only if Phase 2 builds the
dense matrix).

Harness test in `eval/tests/test_harness.py`: a fake transport returning fixed
probabilities proves the ordering, tiebreak, failure path and dump file with no
network.

**Validate:** `uv run --project eval pytest eval/tests -q`.

### Phase 2 — corpus on this host

1. `export IR_DATASETS_HOME=data/eval-cache/ir_datasets`; the 2026 registration
   pulls ~2.8 GB compressed, ~11 GB extracted.
2. `uv run --project eval eval/run.py --config eval/configs/bm25_only_pooled.toml --collection sci-2026-train`
   builds the pooled subset and the BM25 baseline this host needs as the paired
   partner. No vectors, no GPU.
3. Optional: `fusion_union_pool.toml` on the same collection to encode the
   84,489-document pooled matrix with bge-small on the RTX 5000, unlocking the
   fusion-based contrast.

Record the host in `env/hardware.md` of the experiment; it is not the machine
the earlier numbers came from.

### Phase 3 — the experiment

`make new-experiment SLUG=typesafe-pointwise-rerank TITLE="Does a calibrated pointwise probability rerank a scholarly feed?"`

`PROTOCOL.md` is written **before** any arm runs, and states:

- **Primary `[PRE]`.** `typesafe_noul` over `bm25_only` top-20 beats
  `bm25_only` on nDCG@10 on `sci-2026-train` with a 95% paired bootstrap
  interval excluding zero. Falsifier: the interval includes zero or the point
  estimate is negative.
- **Secondary `[PRE]`.** On the same window, `typesafe_score` produces more than
  1.99 distinct values per query on average **and** its mean score is monotonic
  in judged grade. This is the direct re-test of C-016's mechanism.
- **Determinism check, before either.** 20 pairs, 3 repeated calls each; report
  the maximum absolute difference in `noul`. If it exceeds 0.01 the arms report
  mean ± std over 3 runs and the manifest's `nondeterminism_note` says so.
- **Cost and latency**, from the API's own `usage` and wall clock, into
  `metrics.values` and the manifest `llm` block, with the list price and the
  date it was read.
- **Replication rule.** Only if the primary holds does `sci-2025-01` (492
  queries, a second ~1.2M-document download) run; the record has twice been
  burned by n = 100 margins.

`code/paired.py` is adapted from `EXP-2026-08-009`. `code/discrimination.py`
adapts the rubric-discrimination measurement from `EXP-2026-08-008`'s
`llm_diagnosis.py` to read the TypeSafe dump. Figures are generated from
`data/metrics.json` only.

**Validate:** `make figures && make research-index && make validate-research`.

### Phase 4 — record and clean up

- `docs/research/CLAIMS.md`: add C-026 as **unsupported** before the run
  ("A calibrated pointwise relevance probability from a non-generative decision
  model orders a scholarly feed better than BM25 alone"), then update its status
  from `RESULTS.md`.
- `docs/research/OPEN_QUESTIONS.md`: note what this settles about Q-021 and
  Q-023.
- `docs/repo-map.md`: rows for `apps/core/systemone.py`, `typesafe_check`, and
  the two arms. `docs/architecture.md`: the `TYPESAFE_*` variables in the
  configuration table.
- `docs/changelog.md` entry; then delete this plan.

## Interfaces and docs that change

| Item | Change |
|---|---|
| `web/backend/apps/core/systemone.py` | new |
| `web/backend/apps/core/management/commands/typesafe_check.py` | new |
| `web/backend/config/settings.py`, `.env.example` | `TYPESAFE_API_KEY`, `TYPESAFE_MODEL`, `TYPESAFE_TIMEOUT`, `TYPESAFE_MAX_RETRIES` |
| `web/backend/pyproject.toml`, `eval/pyproject.toml` | `typesafe-sdk` dependency |
| `eval/harness/llm_rerank.py`, `eval/configs/typesafe_*.toml` | two arms, three configs |
| `docs/research/experiments/EXP-2026-09-003-…` | new experiment folder |
| `docs/research/CLAIMS.md`, `OPEN_QUESTIONS.md`, `repo-map.md`, `architecture.md`, `changelog.md` | updated |

No API route, serializer, model, migration, or frontend file changes.
No entitlement gate is needed because no reader-facing capability is added.

## Projected cost, from list price

Estimates only. Measured totals go in the experiment, never here.

| Run | Calls | Input tokens | Cost at $0.042/M |
|---|---:|---:|---:|
| Determinism check | 60 | ~15k | < $0.01 |
| `sci-2026-train`, 100 queries × window 20, both arms | 4,000 | ~1M | ~$0.04 |
| `sci-2025-01`, 492 queries × window 20, one arm | 9,840 | ~2.5M | ~$0.10 |

## Acceptance criteria

- Phase 0: core tests pass offline; `typesafe_check` succeeds with the key and
  fails cleanly without it; the ledger shows a `typesafe_check` component row.
- Phase 1: harness tests pass offline; an arm run prints parsed-pair counts and
  token totals; the dump file exists next to the run file.
- Phase 3: `PROTOCOL.md` committed before the first run; `manifest.yaml`
  validates; every number in `RESULTS.md` traces to `data/metrics.json`.
- Phase 4: `make validate-research` clean; plan deleted; changelog written.

## Explicit exclusions

- No production integration: no verdict scoring in `cluster_fit.py`, no
  opportunity match, no alert trigger, no citation check, no `RERANK_*` flag
  change, no `pipeline.py` edit. Each of those is a separate plan with its own
  privacy review.
- No listwise arm. Documented weakness on large states plus C-015 both argue
  against it; if wanted later it is its own pre-registered arm.
- No frontend work, no API contract change.
- No reader, profile, project, or stored `ContentItem` text sent to TypeSafe.
