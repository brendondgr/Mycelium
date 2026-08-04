"""Harness unit tests. No collection download, no Django database.

Three properties the numbers depend on:

1. `NumpyIndex` reproduces `retrieve_for_vector`'s contract — same ordering, same
   clamping, same empty-vector behaviour. If it did not, every embedding arm
   would be measuring the harness rather than production.
2. The embedding cache is keyed on content, so a corpus that changed underneath
   cannot silently reuse stale vectors.
3. `parallel=` sharding does not change a single vector. The harness embeds with
   `parallel` set for speed; that is only legitimate if it is bit-identical to
   the serial path the scan pipeline uses.

The third is marked `slow` because it loads the real model.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.index import NumpyIndex, cache_key  # noqa: E402


@dataclass
class _Doc:
    id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None

    @property
    def text(self) -> str:
        return self.metadata.get("title", "")


def _unit(vectors) -> np.ndarray:
    matrix = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def _index() -> NumpyIndex:
    docs = [_Doc(id="near"), _Doc(id="mid"), _Doc(id="far")]
    matrix = _unit([[1.0, 0.0, 0.0], [0.7, 0.7, 0.0], [0.0, 0.0, 1.0]])
    return NumpyIndex(docs, matrix)


def test_orders_by_cosine_similarity() -> None:
    hits = _index().search([1.0, 0.0, 0.0], limit=3)
    assert [doc.id for doc, _ in hits] == ["near", "mid", "far"]
    assert hits[0][1] == pytest.approx(1.0)
    assert hits[1][1] == pytest.approx(0.7071, abs=1e-3)


def test_empty_vector_returns_no_hits() -> None:
    """Matches `retrieve_for_vector`, which guards rather than raising."""
    assert _index().search(None, limit=5) == []
    assert _index().search([], limit=5) == []
    assert _index().search([1.0, 0.0, 0.0], limit=0) == []


def test_similarity_is_clamped_to_unit_interval() -> None:
    docs = [_Doc(id="opposite")]
    index = NumpyIndex(docs, _unit([[-1.0, 0.0, 0.0]]))
    (_doc, similarity), = index.search([1.0, 0.0, 0.0], limit=1)
    assert similarity == 0.0


def test_exclude_ids_are_dropped_without_shortening_the_result() -> None:
    hits = _index().search([1.0, 0.0, 0.0], limit=2, exclude_ids=["near"])
    assert [doc.id for doc, _ in hits] == ["mid", "far"]


def test_limit_larger_than_corpus_is_safe() -> None:
    assert len(_index().search([1.0, 0.0, 0.0], limit=999)) == 3


def test_mismatched_matrix_is_rejected() -> None:
    with pytest.raises(ValueError, match="cache is stale"):
        NumpyIndex([_Doc(id="a")], _unit([[1.0, 0.0], [0.0, 1.0]]))


def test_cache_key_depends_on_ids_and_order() -> None:
    base = dict(model="m", snapshot="s", scope="full")
    ab, ba = ["a", "b"], ["b", "a"]
    assert cache_key(**base, doc_ids=ab) == cache_key(**base, doc_ids=ab)
    assert cache_key(**base, doc_ids=ab) != cache_key(**base, doc_ids=ba)
    assert cache_key(**base, doc_ids=["a"]) != cache_key(**base, doc_ids=["a", "b"])
    assert cache_key(**base, doc_ids=["a"]) != cache_key(
        model="m", snapshot="s", scope="pooled", doc_ids=["a"]
    )


@pytest.mark.slow
def test_parallel_embedding_is_identical_to_serial() -> None:
    """`parallel=` only shards the work; it must not change a single value.

    The harness embeds with `parallel` set purely for wall-clock. If that
    produced even slightly different vectors, harness numbers would not be about
    the same embedding space the scan pipeline writes into.
    """
    from fastembed import TextEmbedding

    texts = [f"document number {i} about retrieval and ranking" for i in range(256)]
    model = TextEmbedding("BAAI/bge-small-en-v1.5")
    serial = np.asarray(list(model.embed(texts, batch_size=64)), dtype=np.float32)
    sharded = np.asarray(
        list(model.embed(texts, batch_size=64, parallel=4)), dtype=np.float32
    )
    assert serial.shape == sharded.shape
    np.testing.assert_allclose(serial, sharded, rtol=0, atol=0)
