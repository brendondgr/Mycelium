"""Fixtures shared by the collaboration tests (the knowledge core's fakes)."""

import pytest

from apps.content import embeddings
from apps.knowledge.tests.fakes import FakeEmbedder


@pytest.fixture
def embedder():
    fake = FakeEmbedder()
    embeddings.set_embedder(fake)
    yield fake
    embeddings.reset_embedder()
