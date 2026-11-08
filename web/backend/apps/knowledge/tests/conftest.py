"""Fixtures shared by the knowledge-core tests."""

import pytest
from tools.retrieval import embeddings

from .fakes import FakeEmbedder


@pytest.fixture
def embedder():
    fake = FakeEmbedder()
    embeddings.set_embedder(fake)
    yield fake
    embeddings.reset_embedder()


@pytest.fixture
def no_embedder():
    embeddings.set_embedder(None)
    yield
    embeddings.reset_embedder()
