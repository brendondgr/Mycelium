# Retrieval

The grounded corpus every other tool is built on: what papers, grants,
conferences and fellowships exist, what they say, when they are due, and what is
near a given vector or query. Retrieval knows nothing about people. Ranking for
a person, lab or department is the recommendation layer's job.

| | |
|---|---|
| Depends on | — (the platform only) |
| Core | yes — the platform cannot run without it |
| Django app label | `content` (kept: the corpus tables and their migration history were created under it, and the platform's `collab` and `knowledge` migrations depend on that history) |
| Exports | `read`, `service`, `events`, plus the modules still imported directly (listed in `tool.py`) |
| Config | `[tools.retrieval]` in `mycelium.toml`; `make config ARGS="explain tools.retrieval"` |
| Nightly stage | `prune_opportunities` (phase `prune`) |
| API | none of its own |

## What is in here

| Area | Path |
|---|---|
| Paper sources (OpenAlex, PubMed, Semantic Scholar), scan window, cross-source dedup | `sources/`, `ingest.py`, `window.py` |
| The open-source grants/conferences collector (vendored, pure HTTP) | `collect/` |
| Illinois Fellowship Finder scrape + ingest; the eligibility rule engine | `fellowships/`, `eligibility/` |
| Host-side Playwright scrape, dormant Grants.gov/NIH/NSF clients | `host/` |
| `ContentItem`, `ContentDeadline`, `DeadlineKind` | `models.py`, `migrations/` (the whole `content` migration history) |
| Embedder (CPU/CUDA) and its wrapper | `embedding.py`, `embeddings.py` |
| pgvector index, BM25, the `Retrievable`/`VectorIndex` protocols | `index.py`, `lexical.py`, `protocols.py` |
| Corpus search and the cached query embedding | `search.py`, `query_embedding.py` |
| Deadline projection, liveness, duplicate merge | `deadlines_projection.py`, `liveness.py`, `dedupe.py` |
| External DOI / arXiv / URL resolver | `resolver.py` |
| Commands | `collect_opportunities`, `refresh_dblp_registry`, `scan_literature`, `embedding_device`, `apply_extraction_checkpoint`, `dedupe_content_papers`, `rebuild_content_deadlines`, `prune_opportunities`, `reset_opportunities` |

`models.py` holds the corpus only: `ContentItem`, `ContentDeadline` and the
`DeadlineKind` vocabulary. The rest of the old `content` app's models moved to
the recommendation and delivery tools by state-only migrations
(`0038_hand_off_recommendation_models`, `0039_hand_off_delivery_models`), table
names unchanged.

## Doors

- `read.py` — items, deadlines, the vector index, embeddings, liveness, search.
- `service.py` — scan and collect ingestion, prune, deadline rebuilds, duplicate
  merging, resolving an external link into an item.
- `events.py` — `retrieval.items_merging`: published inside a duplicate merge
  so that whoever keeps rows pointing at a `ContentItem` repoints its own.

## Running locally

```bash
uv run --directory web/backend pytest -c pyproject.toml ../../tools/retrieval
uv run tools/retrieval/host/scrape_fellowships.py scrape   # host-side fellowship scrape
```

A ranking change here (`index.py`, `lexical.py`) needs the evaluation-harness
re-run described in `docs/evaluation.md`.
