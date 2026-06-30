"""The shared embedding accessor: pluggable, cached, degrades to None."""

import pytest

from apps.content import embeddings


@pytest.fixture(autouse=True)
def _reset_embedder():
    """Each test starts and ends with the real (probe-based) embedder resolution."""
    embeddings.reset_embedder()
    yield
    embeddings.reset_embedder()


def test_embed_texts_uses_installed_embedder() -> None:
    embeddings.set_embedder(lambda texts: [[float(len(t)), 0.0] for t in texts])

    assert embeddings.embed_texts(["ab", "abcd"]) == [[2.0, 0.0], [4.0, 0.0]]


def test_embed_text_returns_single_vector() -> None:
    embeddings.set_embedder(lambda texts: [[1.0, 2.0, 3.0] for _ in texts])

    assert embeddings.embed_text("anything") == [1.0, 2.0, 3.0]


def test_empty_batch_short_circuits() -> None:
    embeddings.set_embedder(lambda texts: pytest.fail("should not be called"))

    assert embeddings.embed_texts([]) == []


def test_no_embedder_returns_none() -> None:
    embeddings.set_embedder(None)

    assert embeddings.embed_texts(["x"]) is None
    assert embeddings.embed_text("x") is None
