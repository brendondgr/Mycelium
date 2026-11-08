"""Raw cosine between two short texts — the one place the matchers embed anything.

Three of the matchers ask the same narrow question: *does this sentence say
roughly the thing that sentence says?* The claimed contribution against a paper's
headline claim. A blocker against what a paper offers to reuse. Required expertise
against what a member lists.

They use **raw cosine**, deliberately, and never RRF (plan 3.2). RRF is a rank
fusion: it answers "which of these candidates should come first", which is the
retrieval question and is the wrong one here. Nothing is being ranked. The
question is whether two specific sentences are close, and the honest answer is a
similarity, with a threshold that a calibration run sets and can move.

Embeddings are batched and cached per process. A daily run asks about the same
project state hundreds of times — once per candidate item — and the state does not
change while the run is going.
"""

from __future__ import annotations

import threading

#: Per-process cache of ``text -> vector``. Bounded, because a daily run sees
#: tens of thousands of distinct item claims and an unbounded dict of 384-float
#: lists is a slow memory leak rather than a cache.
_CACHE: dict[str, list[float]] = {}
_CACHE_LOCK = threading.Lock()
MAX_CACHE = 20_000


def reset_cache() -> None:
    """Forget every cached vector. For tests, and for a long-lived worker."""
    with _CACHE_LOCK:
        _CACHE.clear()


def _normalise(text: str) -> str:
    return " ".join((text or "").split())[:2000]


def embed_many(texts: list[str], *, embedder=None) -> dict[str, list[float]]:
    """``{text: vector}`` for every non-empty text, embedding only the misses.

    Returns ``{}`` when no embedder is available — the optional extra is not
    installed, or the model cannot load. Every caller treats that as "no signal",
    which degrades the matcher to silence rather than to a wrong answer.
    """
    wanted = {_normalise(text) for text in texts if _normalise(text)}
    if not wanted:
        return {}

    with _CACHE_LOCK:
        hits = {text: _CACHE[text] for text in wanted if text in _CACHE}
    misses = sorted(wanted - set(hits))
    if not misses:
        return hits

    if embedder is None:
        from tools.retrieval.embedding import get_default_embedder

        embedder = get_default_embedder()
    if embedder is None:
        return hits

    try:
        vectors = embedder(misses)
    except Exception:  # noqa: BLE001 — no signal beats a wrong one
        import logging

        logging.getLogger(__name__).warning(
            "could not embed matcher texts", exc_info=True
        )
        return hits

    fresh = dict(zip(misses, vectors, strict=False))
    with _CACHE_LOCK:
        if len(_CACHE) + len(fresh) > MAX_CACHE:
            _CACHE.clear()
        _CACHE.update(fresh)
    return {**hits, **fresh}


def cosine(left: list[float] | None, right: list[float] | None) -> float:
    """Cosine similarity of two vectors, or ``0.0`` when either is missing.

    The embedder returns L2-normalised vectors, so this is a dot product. The
    normalisation is re-applied anyway: a caller passing a vector from somewhere
    else (a stored ``ContentItem.embedding``, say) would otherwise get a number
    that is not a cosine and does not compare against any threshold.
    """
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def similarity(left: str, right: str, *, vectors: dict | None = None) -> float:
    """Cosine between two texts, using a prepared ``vectors`` map when given."""
    left, right = _normalise(left), _normalise(right)
    if not left or not right:
        return 0.0
    if vectors is None:
        vectors = embed_many([left, right])
    return cosine(vectors.get(left), vectors.get(right))
