"""Cross-encoder reranking of the fused candidate list.

Retrieval and fusion (:mod:`.retrieval`, :mod:`.lexical`, :mod:`.fusion`) decide
*which* candidates a target sees. This module reorders the top of that list with
a cross-encoder — a model that reads the query and the document **together**
rather than comparing two independently-computed vectors, and can therefore judge
fit in a way cosine cannot.

**The pool is not changed.** This stage runs over whatever
:func:`tools.recommendation.pipeline._build_pool` already produced. Everything about how
candidates are retrieved stays exactly as deployed.

Why this model
--------------

``Xenova/ms-marco-MiniLM-L-6-v2`` (0.08 GB, ~22M parameters). fastembed offers
five others — a 12-layer sibling, ``BAAI/bge-reranker-base``, and three
``jina-reranker`` variants — and this one is not chosen for being the smallest.
It is the **only reranker any human has judged on this corpus**: every blinded
read in ``docs/research/experiments/EXP-2026-08-014`` … ``-017`` used it. Shipping
a different model would ship a stage nobody has looked at.

What the evidence is, and is not
--------------------------------

Three blinded preference reads by the product's own user, across two research
areas and four content types, put this reranker over the deployed dense pool
first in papers, grants and conferences — and, with the pool held constant so
only the reranker varied, at five wins, three ties and no losses
(``EXP-2026-08-017``).

That is **a preference from one reader, not a relevance measurement**. On
LongEval-Sci the same model is significantly *harmful* on short queries and claim
C-013 stands refuted; the two findings are compatible because the reader judged a
narrow, dense-filtered pool, which is the regime where the harm has never been
reproduced. ``Q-033`` is the outstanding question. Hence the stage ships behind
``RERANK_ENABLED`` and defaults **off** for fellowships (``Q-031``): on that
corpus the query's domain word is boilerplate, and this reranker was measured
promoting medically-themed programmes with no topical connection at all.

Device selection
----------------

Mirrors :mod:`tools.retrieval.embedding` deliberately rather than inventing a second
device story — ``TextCrossEncoder`` takes the identical ``cuda`` / ``device_ids``
arguments as ``TextEmbedding``, so the same rules apply:

- ``settings.RERANK_DEVICE`` is ``auto`` (default), ``cuda`` or ``cpu``, and
  **falls back to ``EMBEDDING_DEVICE``** when unset, so a host configured once is
  configured for both models.
- ``auto`` picks CUDA only when ONNX Runtime actually exposes
  ``CUDAExecutionProvider`` (i.e. the ``embeddings-gpu`` extra is installed);
  ``cuda`` asks explicitly and warns when it is missing; ``cpu`` pins the CPU.
- A CUDA session that fails to build (driver mismatch, out of memory, a card
  already claimed by the LLM) degrades to the CPU with a warning. A nightly run
  getting slower is always better than a worker crashing.
- One session is cached per ``(model, device, device_id)``.

Like the embedder, every import of fastembed is lazy and every failure degrades
to "no reranking" rather than an exception, so the app stays importable without
the optional extra and the pipeline keeps its "a missing capability is a status,
not a crash" convention.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence

from django.conf import settings

from tools.retrieval.embedding import AUTO, CPU, CUDA, cuda_available
from tools.retrieval.protocols import Retrievable

logger = logging.getLogger(__name__)

#: Scores a batch of documents against one query, higher is more relevant. The
#: seam tests inject so the suite never loads a model.
Scorer = Callable[[str, Sequence[str]], list[float]]

DEFAULT_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"

#: How deep into the fused list the reranker is allowed to look. 50 is the depth
#: every experiment used. Candidates below it keep their fusion order and sit
#: underneath the reranked head — a reranker that cannot see rank 200 must not be
#: able to move it.
DEFAULT_DEPTH = 50

#: Ceiling on query-document pairs scored per target per run. A profile with 22
#: declared interests would otherwise cost 22 x depth pairs; this bounds the
#: nightly run's worst case rather than trusting every profile to be small.
DEFAULT_MAX_PAIRS = 400

#: Batch sizes handed to ``TextCrossEncoder.rerank``. A GPU is throughput-bound
#: and wants a large batch; a CPU is latency-bound and wants a modest one.
DEFAULT_BATCH_SIZE = {CPU: 32, CUDA: 128}

#: Content types the stage runs for. Fellowships are absent by default: see the
#: module docstring and ``Q-031``.
DEFAULT_CONTENT_TYPES = ("paper", "grant", "conference")

# Cached ONNX sessions, keyed by (model_name, device, device_id).
_models: dict[tuple[str, str, int | None], object] = {}
_models_lock = threading.Lock()
_logged_devices: set[tuple[str, str, int | None]] = set()


def _setting(name: str, default):
    return getattr(settings, name, default)


def enabled_for(content_type: str | None) -> bool:
    """Is the rerank stage on for ``content_type``?

    Off entirely unless ``RERANK_ENABLED``; then per-type via
    ``RERANK_CONTENT_TYPES``. A ``None`` content type (the harness scores a
    collection with no type) never reranks.
    """
    if not _setting("RERANK_ENABLED", False):
        return False
    if not content_type:
        return False
    allowed = _setting("RERANK_CONTENT_TYPES", DEFAULT_CONTENT_TYPES)
    if isinstance(allowed, str):
        allowed = [part.strip() for part in allowed.split(",") if part.strip()]
    return content_type in set(allowed)


def resolve_device(device: str | None = None) -> tuple[str, int | None]:
    """Resolve the requested device to the one that will actually be used.

    Returns ``(device, device_id)``. ``RERANK_DEVICE`` falls back to
    ``EMBEDDING_DEVICE`` when unset so one host setting covers both models; an
    explicit ``cuda`` that cannot be honored warns and uses the CPU.
    """
    requested = device
    if requested is None:
        requested = _setting("RERANK_DEVICE", None) or _setting(
            "EMBEDDING_DEVICE", AUTO
        )
    requested = (requested or AUTO).strip().lower()
    if requested not in {AUTO, CUDA, CPU}:
        logger.warning("unknown RERANK_DEVICE %r; falling back to %r", requested, AUTO)
        requested = AUTO
    if requested == CPU:
        return CPU, None
    if not cuda_available():
        if requested == CUDA:
            logger.warning(
                "RERANK_DEVICE=cuda but CUDAExecutionProvider is unavailable — "
                "reranking on the CPU. Install the GPU runtime with: "
                "uv sync --extra embeddings-gpu",
            )
        return CPU, None
    raw_id = _setting("RERANK_DEVICE_ID", None)
    if raw_id in (None, ""):
        raw_id = _setting("EMBEDDING_DEVICE_ID", None)
    device_id = int(raw_id) if raw_id not in (None, "") else None
    return CUDA, device_id


def default_batch_size(device: str) -> int:
    """The configured batch size for ``device`` (GPU batches are much larger)."""
    key = "RERANK_BATCH_SIZE_GPU" if device == CUDA else "RERANK_BATCH_SIZE_CPU"
    return int(_setting(key, DEFAULT_BATCH_SIZE[device]))


def rerank_depth() -> int:
    return int(_setting("RERANK_DEPTH", DEFAULT_DEPTH))


def max_pairs() -> int:
    return int(_setting("RERANK_MAX_PAIRS", DEFAULT_MAX_PAIRS))


def reset_rerank_cache() -> None:
    """Drop cached ONNX sessions (tests, and after changing device settings)."""
    with _models_lock:
        _models.clear()
        _logged_devices.clear()


def _build_model(model_name: str, device: str, device_id: int | None):
    """Build a ``TextCrossEncoder`` on ``device``, falling back to the CPU.

    fastembed raises when a requested provider is missing, and an ONNX CUDA
    session can also fail at build time. Either way the pipeline keeps running.
    """
    from fastembed.rerank.cross_encoder import TextCrossEncoder  # lazy

    if device == CUDA:
        try:
            return TextCrossEncoder(
                model_name,
                cuda=True,
                device_ids=[device_id] if device_id is not None else None,
            )
        except Exception as exc:  # noqa: BLE001 - degrade to CPU, don't crash a run.
            logger.warning(
                "CUDA rerank session failed (%s); reranking on the CPU instead", exc
            )
    return TextCrossEncoder(model_name, cuda=False)


def _session_providers(model) -> list[str]:
    """The execution providers the live ONNX session reports, best effort."""
    try:
        return list(model.model.model.get_providers())
    except Exception:  # noqa: BLE001 - diagnostics only.
        return []


def get_scorer(model_name: str | None = None) -> Scorer | None:
    """A :data:`Scorer` backed by the configured cross-encoder, or ``None``.

    ``None`` means "no reranking available" — the optional extra is missing, or
    the model could not be loaded. Callers treat that as a no-op, never an error.
    The session is cached per ``(model, device, device_id)``.
    """
    name = model_name or _setting("RERANK_MODEL", DEFAULT_MODEL)
    device, device_id = resolve_device()
    key = (name, device, device_id)

    with _models_lock:
        model = _models.get(key)
        if model is None:
            try:
                model = _build_model(name, device, device_id)
            except ImportError:
                logger.info(
                    "fastembed not installed; rerank stage disabled "
                    "(install with: uv sync --extra embeddings)"
                )
                return None
            except Exception as exc:  # noqa: BLE001 - no reranker is a status.
                logger.warning("could not load reranker %s: %s", name, exc)
                return None
            _models[key] = model
            if key not in _logged_devices:
                _logged_devices.add(key)
                logger.info(
                    "reranker %s loaded on %s (providers: %s, batch_size=%s)",
                    name,
                    device,
                    ", ".join(_session_providers(model)) or "unknown",
                    default_batch_size(device),
                )

    batch_size = default_batch_size(device)

    def score(query: str, documents: Sequence[str]) -> list[float]:
        raw = model.rerank(query, list(documents), batch_size=batch_size)
        return [float(value) for value in raw]

    return score


def rerank(
    query: str,
    items: Sequence[Retrievable],
    *,
    score: Scorer | None,
    depth: int | None = None,
) -> list[str]:
    """Reorder ``items`` by cross-encoder relevance to ``query``, best first.

    Returns document ids. Only the first ``depth`` items are scored; the rest
    keep their incoming order and follow underneath, so this can reorder the head
    of a list but never promote something the fusion buried.

    Ties break on document id. That is not fussiness: ``EXP-2026-08-003`` recorded
    a ranking whose tie order came from set iteration, which is a hash and not a
    ranking. An empty query, empty input, or a missing scorer returns the incoming
    order unchanged — a missing capability is a status, not a crash.
    """
    ids = [str(item.id) for item in items]
    if score is None or not ids or not (query or "").strip():
        return ids

    from tools.retrieval.lexical import _item_text

    cut = depth if depth is not None else rerank_depth()
    head, tail = list(items[:cut]), ids[cut:]
    if not head:
        return ids

    head_ids = [str(item.id) for item in head]
    try:
        scores = score(query, [_item_text(item) for item in head])
    except Exception as exc:  # noqa: BLE001 - a failed rerank is the fused order.
        logger.warning("rerank failed (%s); keeping the fused order", exc)
        return ids
    if len(scores) != len(head_ids):
        logger.warning(
            "reranker returned %d scores for %d documents; keeping the fused order",
            len(scores),
            len(head_ids),
        )
        return ids

    order = sorted(
        range(len(head_ids)), key=lambda i: (-scores[i], head_ids[i])
    )
    return [head_ids[i] for i in order] + tail


def rerank_order(
    ordered_ids: Sequence[str],
    *,
    items_by_id: dict[str, Retrievable],
    per_interest_scores: dict[str, dict[str, float]],
    queries: dict[str, str],
    score: Scorer | None,
    depth: int | None = None,
    budget: int | None = None,
    rrf_k: int = 60,
) -> list[str]:
    """Reorder ``ordered_ids`` by reranking **per interest** and merging by RRF.

    This is the one design decision no experiment covers, so the reasoning is
    here rather than in a commit message. Every blinded read
    (``EXP-2026-08-014`` … ``-017``) reranked **one** list against **one** query.
    Production builds its pool from several declared interests, and cross-encoder
    logits are **not comparable across different queries** — the same document
    scored against "knowledge graphs" and against "clinical data extraction"
    produces two numbers that cannot be put in one order.

    So each interest's own candidates are reranked against that interest's own
    query, and the resulting *orderings* are merged by Reciprocal Rank Fusion —
    ranks are comparable where scores are not, and RRF is already how this
    codebase fuses (:data:`tools.recommendation.fusion.DEFAULT_RRF_K`).

    The property that makes this the defensible default: **with a single declared
    interest it reduces exactly to the configuration that was judged** — one
    query, one list, one rerank, no merge.

    ``budget`` caps total query-document pairs across all interests, so a
    22-interest profile cannot turn a nightly run into an afternoon. Candidates
    outside every interest's reranked slice keep their incoming relative order
    and follow underneath.
    """
    ids = list(ordered_ids)
    if score is None or not ids or not per_interest_scores:
        return ids

    cut = depth if depth is not None else rerank_depth()
    allowance = budget if budget is not None else max_pairs()
    surviving = set(ids)
    labels = [
        label
        for label in per_interest_scores
        if label in queries and any(i in surviving for i in per_interest_scores[label])
    ]
    if not labels:
        return ids

    # Spread the pair budget evenly rather than letting the first interest eat it.
    per_label = max(1, min(cut, allowance // len(labels)))

    rrf: dict[str, float] = {}
    for label in labels:
        scores = per_interest_scores[label]
        candidates = sorted(
            (i for i in scores if i in surviving),
            key=lambda i: (-scores[i], i),
        )[:per_label]
        items = [items_by_id[i] for i in candidates if i in items_by_id]
        if not items:
            continue
        for rank, doc_id in enumerate(
            rerank(queries[label], items, score=score, depth=per_label), start=1
        ):
            rrf[doc_id] = rrf.get(doc_id, 0.0) + 1.0 / (rrf_k + rank)

    if not rrf:
        return ids

    position = {doc_id: index for index, doc_id in enumerate(ids)}
    reranked = sorted(rrf, key=lambda i: (-rrf[i], position[i]))
    remainder = [i for i in ids if i not in rrf]
    return reranked + remainder


def describe_device(*, load: bool = False) -> dict:
    """Diagnostics for the ``rerank_device`` management command.

    ``load=True`` actually builds the session so ``session_providers`` reports
    what the model is really running on — the only way to confirm a GPU on a
    server rather than infer it.
    """
    try:
        import onnxruntime as ort

        available = list(ort.get_available_providers())
    except Exception:  # noqa: BLE001 - report the absence rather than raise.
        available = []

    device, device_id = resolve_device()
    info = {
        "enabled": bool(_setting("RERANK_ENABLED", False)),
        "content_types": list(_setting("RERANK_CONTENT_TYPES", DEFAULT_CONTENT_TYPES)),
        "model": _setting("RERANK_MODEL", DEFAULT_MODEL),
        "requested": str(
            _setting("RERANK_DEVICE", None) or _setting("EMBEDDING_DEVICE", AUTO)
        ),
        "resolved": device,
        "device_id": device_id,
        "cuda_available": cuda_available(),
        "available_providers": available,
        "batch_size": default_batch_size(device),
        "depth": rerank_depth(),
        "max_pairs": max_pairs(),
        "session_providers": [],
    }
    if load:
        name = info["model"]
        with _models_lock:
            model = _models.get((name, device, device_id))
        if model is None:
            get_scorer(name)
            with _models_lock:
                model = _models.get((name, device, device_id))
        if model is not None:
            info["session_providers"] = _session_providers(model)
    return info
