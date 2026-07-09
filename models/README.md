# models/

Persistent, on-disk cache for locally-downloaded ML models — kept here (a
bind-mounted directory) rather than in a container's ephemeral `/tmp`, so a model
is downloaded **once** and survives container restarts and recreates.

## `fastembed/`

The FastEmbed / ONNX embedding model used to embed interest and content text
(default `qdrant/bge-small-en-v1.5-onnx-q`, ~65–90 MB). The backend and worker
containers point FastEmbed here via `FASTEMBED_CACHE_PATH=/app/models/fastembed`
(set in `compose.yaml`), which maps to this directory through the `.:/app` bind
mount.

The model files are **git-ignored** (large binaries) — only this README and the
`.gitkeep` are tracked. On first use FastEmbed downloads the model into
`fastembed/`; after that it loads from disk with no network and no re-download.

### First-run / warming

The model downloads lazily on the first embedding call. To avoid a cold-start
race when many requests arrive at once (e.g. a load test), warm it once first:

```bash
docker compose exec -T backend uv run --project web/backend python -c \
  "from apps.scraper.embedding import get_default_embedder; get_default_embedder()(['warm up'])"
```

If the cache is ever deleted, it simply re-downloads on next use.
