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

### GPU acceleration (CUDA)

Embedding runs on a CUDA GPU whenever one is genuinely available — see
`apps/scraper/embedding.py`. The device is chosen by `EMBEDDING_DEVICE`
(`auto` | `cuda` | `cpu`, default `auto`), but `auto` can only find a card when
the **GPU flavour** of the extra is installed: plain `fastembed` depends on the
CPU-only `onnxruntime`, which never exposes `CUDAExecutionProvider`.

```bash
uv sync --project web/backend --extra embeddings-gpu   # instead of --extra embeddings
```

Root-level runners (`pivot.py`, `manual_*.py`) use dependency groups instead:

```bash
uv sync --no-group embeddings-cpu --group embeddings-gpu
```

Containers: `docker compose -f compose.yaml -f compose.gpu.yaml up -d` (needs the
nvidia-container-toolkit on the host).

Confirm what is actually running — `session providers` is the honest answer,
since a CPU fallback is silent by design:

```bash
uv run --project web/backend python web/backend/manage.py embedding_device --benchmark
```

```
resolved device:     cuda
session providers:   CUDAExecutionProvider, CPUExecutionProvider
benchmark:           256 texts in 0.21s (1219.0 texts/s, 384-dim)
```

The GPU and CPU paths run the same ONNX graph and the same normalization, so
vectors are interchangeable — switching device never invalidates stored
embeddings. A missing driver, a busy card, or a failed CUDA session degrades to
the CPU with a warning rather than crashing a scan.
