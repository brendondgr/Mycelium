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
"""

from __future__ import annotations

from collections.abc import Callable

from django.conf import settings

#: Maps a batch of texts to a batch of unit-length vectors.
Embedder = Callable[[list[str]], list[list[float]]]

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


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


class FastEmbedEmbedder:
    """Lazy fastembed wrapper. The model loads on first call, not on import."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or getattr(
            settings, "SCRAPER_EMBEDDING_MODEL", DEFAULT_MODEL
        )
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            from fastembed import TextEmbedding  # lazy: only when actually embedding

            self._model = TextEmbedding(self.model_name)
        return self._model

    def __call__(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        import numpy as np  # lazy: part of the embeddings extra

        model = self._ensure_model()
        raw = np.asarray(list(model.embed(texts)), dtype=np.float32)
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
