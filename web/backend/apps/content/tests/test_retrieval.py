"""pgvector cosine retrieval over the content store.

The cosine-distance query needs pgvector, so the database-backed cases skip on
SQLite (CI runs them against the Postgres service). The empty-vector guard is
pure Python and always runs.
"""

import pytest
from django.db import connection

from apps.content.models import ContentItem
from apps.content.retrieval import retrieve_for_vector


def test_empty_vector_returns_no_hits_without_db() -> None:
    assert retrieve_for_vector(None) == []
    assert retrieve_for_vector([]) == []


@pytest.fixture
def pgvector(db: None):
    if connection.vendor != "postgresql":
        pytest.skip("cosine retrieval requires PostgreSQL + pgvector")


def _paper(source: str, vector, *, type_=ContentItem.Type.PAPER) -> ContentItem:
    return ContentItem.objects.create(
        type=type_, source=source, external_id=source, embedding=vector
    )


@pytest.mark.django_db
def test_orders_by_cosine_similarity(pgvector) -> None:
    near = _paper("near", [1.0, 0.0, 0.0])
    mid = _paper("mid", [0.7, 0.7, 0.0])
    far = _paper("far", [0.0, 0.0, 1.0])

    hits = retrieve_for_vector([1.0, 0.0, 0.0], limit=10)

    assert [item.id for item, _ in hits] == [near.id, mid.id, far.id]
    # The exact-match hit has similarity ~1.0; the orthogonal one ~0.0.
    assert hits[0][1] == pytest.approx(1.0, abs=1e-6)
    assert hits[-1][1] == pytest.approx(0.0, abs=1e-6)


@pytest.mark.django_db
def test_limit_caps_results(pgvector) -> None:
    for i in range(5):
        _paper(f"p{i}", [1.0, float(i), 0.0])

    assert len(retrieve_for_vector([1.0, 0.0, 0.0], limit=2)) == 2


@pytest.mark.django_db
def test_items_without_embeddings_are_ignored(pgvector) -> None:
    _paper("has-vector", [1.0, 0.0, 0.0])
    ContentItem.objects.create(
        type=ContentItem.Type.PAPER, source="no-vector", external_id="no-vector"
    )

    hits = retrieve_for_vector([1.0, 0.0, 0.0], limit=10)

    assert [item.source for item, _ in hits] == ["has-vector"]


@pytest.mark.django_db
def test_content_type_filters(pgvector) -> None:
    _paper("paper", [1.0, 0.0, 0.0])
    _paper("grant", [1.0, 0.0, 0.0], type_=ContentItem.Type.GRANT)

    hits = retrieve_for_vector([1.0, 0.0, 0.0], content_type=ContentItem.Type.PAPER)

    assert [item.source for item, _ in hits] == ["paper"]


@pytest.mark.django_db
def test_exclude_ids_drops_known_items(pgvector) -> None:
    keep = _paper("keep", [1.0, 0.0, 0.0])
    skip = _paper("skip", [0.9, 0.1, 0.0])

    hits = retrieve_for_vector([1.0, 0.0, 0.0], exclude_ids=[skip.id])

    assert [item.id for item, _ in hits] == [keep.id]
