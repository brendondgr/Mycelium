"""One embedder for both sides of retrieval.

Relevance retrieval only works if the *query* (a user's interest profile) and the
*documents* (scanned papers) are embedded by the **same** model into the same
space. The literature scan already embeds papers with fastembed
``BAAI/bge-small-en-v1.5`` (see :mod:`apps.scraper.embedding`); this module is the
thin shared accessor the daily pipeline uses to embed a profile's canonical text
and any ad-hoc query with that identical model.

Like the scan, embedding is optional: when the ``embeddings`` extra is absent the
accessors return ``None`` and callers degrade to "no retrieval" rather than
crashing. The fastembed model is loaded once and reused across calls.
"""

from __future__ import annotations

from apps.scraper.embedding import Embedder, get_default_embedder

_embedder: Embedder | None = None
_resolved = False


def get_embedder() -> Embedder | None:
    """The shared batch embedder, or ``None`` when the extra is missing.

    Cached after the first call so the fastembed model is loaded at most once
    per process.
    """
    global _embedder, _resolved
    if not _resolved:
        _embedder = get_default_embedder()
        _resolved = True
    return _embedder


def reset_embedder() -> None:
    """Drop the cached embedder (tests install their own via :func:`set_embedder`)."""
    global _embedder, _resolved
    _embedder = None
    _resolved = False


def set_embedder(embedder: Embedder | None) -> None:
    """Install a specific embedder (tests inject a fake; ``None`` disables)."""
    global _embedder, _resolved
    _embedder = embedder
    _resolved = True


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Embed a batch of texts, or return ``None`` when no embedder is available."""
    embedder = get_embedder()
    if embedder is None:
        return None
    if not texts:
        return []
    return embedder(texts)


def embed_text(text: str) -> list[float] | None:
    """Embed one text, or return ``None`` when no embedder is available."""
    vectors = embed_texts([text])
    if not vectors:
        return None
    return vectors[0]
