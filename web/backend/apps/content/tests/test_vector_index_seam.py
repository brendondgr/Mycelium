"""The `VectorIndex` seam: substituting the index must not change the ranking.

`_build_pool` grew an `index` parameter so an offline evaluation harness can run
the *production* ranking stack against an external collection (see `eval/`). That
is only worth anything if the seam is behaviour-preserving, so these tests pin the
two properties the harness depends on:

1. The default path still goes through pgvector — the parameter is opt-in, and a
   caller that omits it gets exactly the query it got before.
2. A non-ORM object satisfying :class:`~apps.content.protocols.Retrievable` ranks
   identically to the `ContentItem` it mirrors, ordering and scores alike.

The second is the load-bearing one: it is what lets the harness claim it measures
this repository's ranking rather than a reimplementation of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from apps.content.interests_query import SearchInterest
from apps.content.models import ContentItem
from apps.content.pipeline import _build_pool
from apps.content.protocols import Retrievable, VectorIndex
from apps.content.retrieval import PgVectorIndex


@dataclass
class _Doc:
    """A plain, DB-free candidate — what an external collection looks like."""

    id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None


class _StubIndex:
    """A `VectorIndex` that replays a fixed hit list, ignoring the query vector."""

    def __init__(self, hits: list[tuple[Retrievable, float]]) -> None:
        self.hits = hits
        self.calls: list[dict] = []

    def search(self, vector, *, limit, exclude_ids=None):
        self.calls.append(
            {"vector": vector, "limit": limit, "exclude_ids": exclude_ids}
        )
        return self.hits[:limit]


def _interest(label: str) -> SearchInterest:
    return SearchInterest(label=label, query_text=label, embed_text=label)


def test_protocols_are_satisfied_by_both_worlds() -> None:
    """The ORM model and a plain dataclass both satisfy `Retrievable`."""
    assert isinstance(_Doc(id="a"), Retrievable)
    assert isinstance(ContentItem(), Retrievable)
    assert isinstance(_StubIndex([]), VectorIndex)
    assert isinstance(PgVectorIndex(), VectorIndex)


def test_omitting_the_index_uses_pgvector(monkeypatch) -> None:
    """The default is unchanged: no `index` argument means the pgvector query."""
    seen: dict = {}

    def fake_retrieve(vector, **kwargs):
        seen.update(kwargs)
        seen["vector"] = vector
        return []

    monkeypatch.setattr("apps.content.retrieval.retrieve_for_vector", fake_retrieve)
    monkeypatch.setattr(
        "apps.content.embeddings.embed_text", lambda _text: [1.0, 0.0, 0.0]
    )

    pool, scores, best = _build_pool(
        [_interest("alpha")],
        content_type=ContentItem.Type.GRANT,
        pool_per_interest=7,
        created_on=None,
    )

    assert (pool, scores, best) == ({}, {}, {})
    # The scoping arguments still reach the pgvector query untouched.
    assert seen["content_type"] == ContentItem.Type.GRANT
    assert seen["limit"] == 7
    assert seen["created_on"] is None


def test_stub_index_reproduces_the_orm_ranking(monkeypatch) -> None:
    """A DB-free pool ranks byte-identically to the same pool of `ContentItem`s.

    Both runs feed `_build_pool` the *same* candidates and the same similarities,
    differing only in the object type behind the index. Any divergence would mean
    the ranking stack reads something beyond the `Retrievable` surface, and the
    harness's numbers would not be about production code.
    """
    monkeypatch.setattr(
        "apps.content.embeddings.embed_text", lambda _text: [1.0, 0.0, 0.0]
    )
    interests = [_interest("graph neural networks"), _interest("protein folding")]

    payloads = [
        ("11111111-1111-1111-1111-111111111111", "Graph neural networks for protein contact maps", 0.91),
        ("22222222-2222-2222-2222-222222222222", "Protein folding with diffusion models", 0.84),
        ("33333333-3333-3333-3333-333333333333", "Graph attention over citation networks", 0.77),
        ("44444444-4444-4444-4444-444444444444", "Unrelated work on supply chain logistics", 0.40),
    ]

    def run(make) -> tuple[dict, dict]:
        hits = [(make(pk, title), sim) for pk, title, sim in payloads]
        index = _StubIndex(hits)
        pool, scores, best = _build_pool(
            interests,
            content_type=ContentItem.Type.PAPER,
            pool_per_interest=10,
            created_on=None,
            index=index,
        )
        return scores, best

    orm_scores, orm_best = run(
        lambda pk, title: ContentItem(
            id=pk, type=ContentItem.Type.PAPER, metadata={"title": title}
        )
    )
    plain_scores, plain_best = run(
        lambda pk, title: _Doc(id=pk, metadata={"title": title})
    )

    assert plain_scores == orm_scores
    assert plain_best == orm_best
    # Not vacuous: the fixture really did produce a discriminating ranking.
    assert orm_scores, "expected the fixture pool to score at least one interest"
    assert len(orm_best) == len(payloads)


def test_index_receives_the_pool_width_and_exclusions() -> None:
    """`_build_pool` passes its width and exclusions straight through."""
    index = _StubIndex([(_Doc(id="a", metadata={"title": "alpha beta"}), 0.9)])
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            "apps.content.embeddings.embed_text", lambda _text: [0.0, 1.0, 0.0]
        )
        _build_pool(
            [_interest("alpha")],
            content_type=ContentItem.Type.PAPER,
            pool_per_interest=5,
            created_on=None,
            exclude_ids=["zzz"],
            index=index,
        )
    assert index.calls == [
        {"vector": [0.0, 1.0, 0.0], "limit": 5, "exclude_ids": ["zzz"]}
    ]
