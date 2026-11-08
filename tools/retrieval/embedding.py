"""Article embedding for the RAG store.

The scan pipeline embeds each new paper's ``title + abstract`` and writes the
vector onto ``content.ContentItem.embedding``. The model is fastembed
``BAAI/bge-small-en-v1.5`` (384-dim), matching the ResearchScraper reranker.

Embedding is **pluggable and optional**:

- ``fastembed`` (+ ``numpy``) ships in the optional ``embeddings`` extra
  (``uv sync --extra embeddings``); both are imported lazily, so the app stays
  importable — and the rest of the scan still runs — when the extra is absent.
- :func:`get_default_embedder` returns ``None`` when the extra is missing; the
  pipeline then stores rows with ``embedding=NULL`` and reports the reason,
  honoring the project's deferred-embedding-dimension decision rather than
  crashing a worker.
- Tests inject their own embedder, so the suite never imports fastembed.

An ``Embedder`` maps a batch of texts to a batch of vectors (one ``list[float]``
each), so a single model load covers a whole scan.

**Device selection.** Embedding runs on a CUDA GPU whenever one is really
available and falls back to the CPU otherwise:

- ``settings.EMBEDDING_DEVICE`` is ``auto`` (default), ``cuda`` or ``cpu``.
  ``auto`` picks CUDA only when ONNX Runtime actually exposes
  ``CUDAExecutionProvider``; ``cuda`` asks for it explicitly and warns when it is
  missing; ``cpu`` pins the CPU even on a GPU host.
- The provider is only available when the GPU flavour of the extra is installed
  (``uv sync --extra embeddings-gpu`` → ``fastembed-gpu`` + ``onnxruntime-gpu``).
  The plain ``embeddings`` extra ships the CPU-only runtime, so a request for
  CUDA there degrades to CPU with a warning rather than crashing a worker.
- One ONNX session is cached per ``(model, device, device_id)``, so constructing
  ``FastEmbedEmbedder`` repeatedly (the paste-a-link resolver does) reuses a
  single loaded model instead of re-uploading weights to the card.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from django.conf import settings

logger = logging.getLogger(__name__)

#: Maps a batch of texts to a batch of unit-length vectors.
Embedder = Callable[[list[str]], list[list[float]]]

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"

CPU = "cpu"
CUDA = "cuda"
AUTO = "auto"

#: Batch sizes handed to ``TextEmbedding.embed``. A GPU is throughput-bound and
#: wants a large batch; a CPU is latency-bound and wants a modest one.
DEFAULT_BATCH_SIZE = {CPU: 64, CUDA: 256}

_CUDA_PROVIDER = "CUDAExecutionProvider"

# Cached ONNX sessions, keyed by (model_name, device, device_id).
_models: dict[tuple[str, str, int | None], object] = {}
_models_lock = threading.Lock()
_logged_devices: set[tuple[str, str, int | None]] = set()


def _setting(name: str, default):
    return getattr(settings, name, default)


def cuda_available() -> bool:
    """True when the installed ONNX Runtime exposes ``CUDAExecutionProvider``.

    The CPU wheel never does, so this doubles as the "is the GPU flavour of the
    extra installed" probe. Any import problem means "no CUDA", never a crash.
    """
    try:
        import onnxruntime as ort  # lazy: part of the embeddings extra
    except ImportError:
        return False
    try:
        return _CUDA_PROVIDER in ort.get_available_providers()
    except Exception:  # noqa: BLE001 - a broken runtime is simply "no CUDA".
        return False


def resolve_device(device: str | None = None) -> tuple[str, int | None]:
    """Resolve the requested device to the one that will actually be used.

    Returns ``(device, device_id)`` where device is ``"cuda"`` or ``"cpu"``.
    ``auto`` (the default) uses CUDA when available. An explicit ``cuda`` request
    that cannot be honored warns and falls back to CPU — embedding degrading to
    slow is always better than a worker crashing.
    """
    requested = (device or _setting("EMBEDDING_DEVICE", AUTO) or AUTO).strip().lower()
    if requested not in {AUTO, CUDA, CPU}:
        logger.warning(
            "unknown EMBEDDING_DEVICE %r; falling back to %r", requested, AUTO
        )
        requested = AUTO
    if requested == CPU:
        return CPU, None
    if not cuda_available():
        if requested == CUDA:
            logger.warning(
                "EMBEDDING_DEVICE=cuda but %s is unavailable — embedding on the CPU. "
                "Install the GPU runtime with: uv sync --extra embeddings-gpu",
                _CUDA_PROVIDER,
            )
        return CPU, None
    raw_id = _setting("EMBEDDING_DEVICE_ID", None)
    device_id = int(raw_id) if raw_id not in (None, "") else None
    return CUDA, device_id


def default_batch_size(device: str) -> int:
    """The configured batch size for ``device`` (GPU batches are much larger)."""
    key = "EMBEDDING_BATCH_SIZE_GPU" if device == CUDA else "EMBEDDING_BATCH_SIZE_CPU"
    return int(_setting(key, DEFAULT_BATCH_SIZE[device]))


def reset_embedding_cache() -> None:
    """Drop cached ONNX sessions (tests, and after changing device settings)."""
    with _models_lock:
        _models.clear()
        _logged_devices.clear()


def build_article_text(record) -> str:
    """The document text embedded for a paper: title then abstract.

    Falls back to whichever of the two is present so every paper stays
    embeddable; returns ``""`` only when both are empty.
    """
    title = record.clean_title
    abstract = record.clean_abstract
    if title and abstract:
        return f"{title}\n\n{abstract}"
    return title or abstract


def _build_model(model_name: str, device: str, device_id: int | None):
    """Build a ``TextEmbedding`` on ``device``, falling back to the CPU.

    fastembed raises when a requested provider is missing, and an ONNX CUDA
    session can also fail at build time (driver/toolkit mismatch, out of memory,
    a card already fully claimed by the LLM). Either way the pipeline keeps
    running on the CPU.
    """
    from fastembed import TextEmbedding  # lazy: only when actually embedding

    if device == CUDA:
        try:
            return TextEmbedding(
                model_name,
                cuda=True,
                device_ids=[device_id] if device_id is not None else None,
            )
        except Exception as exc:  # noqa: BLE001 - degrade to CPU, don't crash a scan.
            logger.warning(
                "CUDA embedding session failed (%s); embedding on the CPU instead", exc
            )
    return TextEmbedding(model_name, cuda=False)


def _session_providers(model) -> list[str]:
    """The execution providers the live ONNX session reports, best effort."""
    try:
        return list(model.model.model.get_providers())
    except Exception:  # noqa: BLE001 - diagnostics only.
        return []


class FastEmbedEmbedder:
    """Lazy fastembed wrapper. The model loads on first call, not on import.

    Runs on CUDA when one is available (see the module docstring); the loaded
    model is shared process-wide per ``(model, device, device_id)``.
    """

    def __init__(
        self,
        model_name: str | None = None,
        *,
        device: str | None = None,
        device_id: int | None = None,
        batch_size: int | None = None,
    ) -> None:
        self.model_name = model_name or _setting(
            "SCRAPER_EMBEDDING_MODEL", DEFAULT_MODEL
        )
        resolved, resolved_id = resolve_device(device)
        self.device = resolved
        self.device_id = resolved_id if device_id is None else device_id
        self.batch_size = batch_size or default_batch_size(resolved)
        self._model = None

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        key = (self.model_name, self.device, self.device_id)
        with _models_lock:
            model = _models.get(key)
            if model is None:
                model = _build_model(self.model_name, self.device, self.device_id)
                _models[key] = model
            if key not in _logged_devices:
                _logged_devices.add(key)
                logger.info(
                    "embedding model %s loaded on %s (providers: %s, batch_size=%s)",
                    self.model_name,
                    self.device,
                    ", ".join(_session_providers(model)) or "unknown",
                    self.batch_size,
                )
        self._model = model
        return model

    def __call__(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        import numpy as np  # lazy: part of the embeddings extra

        model = self._ensure_model()
        raw = np.asarray(
            list(model.embed(texts, batch_size=self.batch_size)), dtype=np.float32
        )
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (raw / norms).tolist()


def get_default_embedder(model_name: str | None = None) -> Embedder | None:
    """The fastembed embedder, or ``None`` when the optional extra is missing."""
    try:
        import fastembed  # noqa: F401  (probe only)
        import numpy  # noqa: F401
    except ImportError:
        return None
    return FastEmbedEmbedder(model_name)


def describe_device(*, load: bool = False) -> dict:
    """A diagnostic snapshot of where embedding will run (and did run).

    ``load=True`` actually builds the session so ``session_providers`` reports
    what ONNX Runtime settled on — the only honest proof the GPU is in use.
    Backs the ``embedding_device`` management command.
    """
    device, device_id = resolve_device()
    try:
        import onnxruntime as ort

        available = list(ort.get_available_providers())
        runtime = getattr(ort, "__version__", "")
    except ImportError:
        available = []
        runtime = ""
    info = {
        "installed": get_default_embedder() is not None,
        "model": _setting("SCRAPER_EMBEDDING_MODEL", DEFAULT_MODEL),
        "requested": str(_setting("EMBEDDING_DEVICE", AUTO)),
        "device": device,
        "device_id": device_id,
        "batch_size": default_batch_size(device),
        "onnxruntime_version": runtime,
        "available_providers": available,
        "session_providers": [],
    }
    if load and info["installed"]:
        embedder = FastEmbedEmbedder()
        info["session_providers"] = _session_providers(embedder._ensure_model())
    return info
