# GPU-Accelerated Embedding

## Objective

Make Mycelium's local embedding pass (fastembed / ONNX Runtime, `BAAI/bge-small-en-v1.5`)
run on a CUDA GPU whenever one is present, fall back to CPU cleanly when it is not, and
be observable enough that an operator can confirm which device actually ran.

## Findings (why it runs on CPU today)

- Every vector in the product comes from one place: `apps/scraper/embedding.py`
  (`FastEmbedEmbedder`). `apps/content/embeddings.py`, `query_embedding.py`,
  `apps/scraper/ingest.py` and `apps/scraper/resolver.py` all funnel through it.
- fastembed 0.8's `TextEmbedding(..., cuda=Device.AUTO)` *already* selects
  `CUDAExecutionProvider` when ONNX Runtime exposes it. The blocker is the installed
  wheel: the `embeddings` extra pulls plain `fastembed`, which depends on the CPU-only
  `onnxruntime` (`get_available_providers()` → `['AzureExecutionProvider',
  'CPUExecutionProvider']`). CUDA is therefore never even a candidate.
- Two secondary costs: the model is re-loaded per `FastEmbedEmbedder` instance
  (`resolver.py` builds a new one on every paste-a-link resolve), and `model.embed()`
  runs at fastembed's default batch size, which is not what you want on a GPU.

## Assumptions

- The GPU server has an NVIDIA card with a CUDA 12.x driver stack.
- Dockerized services only see the GPU if the host grants it (nvidia-container-toolkit);
  the host-side `mylo-daily` run and the root `uv run` scripts see it directly.
- This dev machine has **no** CUDA device, so GPU execution is verified by the operator
  on the server with the new diagnostic command; locally we verify the CPU path plus the
  device-resolution logic.

## Decisions

- **D1 — Package split, not a flag.** GPU support ships as a separate optional extra
  `embeddings-gpu` (`fastembed-gpu` + `onnxruntime-gpu`), declared as *conflicting* with
  `embeddings` in `[tool.uv]`. `fastembed-gpu` imports as `fastembed`, so no call site
  changes; installing both distributions in one environment is the documented failure
  mode and uv will now refuse it.
- **D2 — Auto by default, explicitly overridable.** `EMBEDDING_DEVICE=auto|cuda|cpu`
  (default `auto`) plus `EMBEDDING_DEVICE_ID`. `auto` uses CUDA only when the provider is
  really available; `cuda` demands it and says so loudly if it is missing; `cpu` forces
  CPU even on a GPU box (useful when the card is busy serving the LLM).
- **D3 — Never crash the pipeline over a device.** A failed CUDA session build falls back
  to CPU with a warning, matching the module's existing "degrade, don't crash" contract.
- **D4 — One loaded model per process.** The underlying `TextEmbedding` is cached by
  `(model, device, device_id)`, so repeated `FastEmbedEmbedder()` construction (resolver)
  reuses a single GPU session instead of re-uploading weights.
- **D5 — Device-aware batch size.** `EMBEDDING_BATCH_SIZE_CPU` / `EMBEDDING_BATCH_SIZE_GPU`
  (defaults 64 / 256) are passed to `model.embed(batch_size=...)`.

## Phases

1. **Device layer** — `apps/scraper/embedding.py`: `resolve_device()`, device-aware
   `FastEmbedEmbedder`, shared session cache, CPU fallback, one INFO log line naming the
   provider actually in use, `describe_device()` for diagnostics. Settings in
   `config/settings.py`.
2. **Diagnostics** — `manage.py embedding_device [--benchmark N]`: prints the requested
   device, ONNX Runtime's available providers, the providers the live session reports,
   and (optionally) a throughput measurement. This is the acceptance check on the server.
3. **Dependencies** — `embeddings-gpu` extra in `web/backend/pyproject.toml` and the root
   runner `pyproject.toml`, with the uv conflict declaration.
4. **Wiring & docs** — `.env.example` knobs, `compose.yaml` pass-through + a GPU note,
   `models/README.md` / `docs/repo-map.md` / `docs/changelog.md`.
5. **Tests** — `apps/scraper/tests/test_embedding_device.py`: auto with/without CUDA,
   forced cpu/cuda, unavailable-CUDA fallback, batch-size selection, session caching.
   No test imports fastembed or onnxruntime.

## Interfaces that change

- New settings: `EMBEDDING_DEVICE`, `EMBEDDING_DEVICE_ID`, `EMBEDDING_BATCH_SIZE_CPU`,
  `EMBEDDING_BATCH_SIZE_GPU`.
- New public functions in `apps.scraper.embedding`: `resolve_device()`,
  `describe_device()`, `reset_embedding_cache()`.
- New management command `embedding_device`.
- `FastEmbedEmbedder(model_name=None, *, device=None, device_id=None, batch_size=None)` —
  existing zero-arg construction is unchanged.

## Validation

- `uv run --project web/backend ruff check` + `ruff format --check` on touched files.
- `uv run --project web/backend pytest apps/scraper apps/content` (CPU path).
- Local: `manage.py embedding_device --benchmark 64` reports `cpu` and a real vector.
- Server (operator): `uv sync --extra embeddings-gpu` then the same command must report
  `device=cuda`, `session_providers=['CUDAExecutionProvider', ...]`, with a materially
  higher texts/sec than the CPU run.

## Exclusions

- No change to the model, vector dimension, or any scoring semantics — GPU and CPU must
  produce the same vectors (same ONNX graph, same normalization).
- No GPU support for the LLM stack (that is a separate vLLM concern).
- No change to the daily orchestrator's stage list.
