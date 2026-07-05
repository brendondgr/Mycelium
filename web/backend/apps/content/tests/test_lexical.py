"""The BM25 lexical channel: ranking, empty-pool/query guards, no-match drop.

Uses unsaved ``ContentItem`` instances — BM25 only reads ``metadata`` text, so no
database (and no pgvector) is needed here.
"""

from apps.content.lexical import build_bm25_index, rank_bm25_over
from apps.content.models import ContentItem


def _paper(title: str, abstract: str = "") -> ContentItem:
    return ContentItem(
        type=ContentItem.Type.PAPER,
        metadata={"title": title, "abstract": abstract},
    )


def test_unique_term_ranks_its_paper_first() -> None:
    graph = _paper("Knowledge graph embeddings for reasoning")
    health = _paper("A study of public health outcomes")
    other = _paper("Unrelated notes on gardening")
    index = build_bm25_index([graph, health, other])

    hits = rank_bm25_over("knowledge graph", index)

    assert hits, "expected at least one lexical match"
    assert hits[0][0] is graph


def test_non_matching_candidates_are_dropped() -> None:
    graph = _paper("Knowledge graph embeddings")
    # Several unrelated papers so the query terms are rare (positive BM25 IDF)
    # and the non-matching papers score zero and drop out.
    others = [
        _paper("Gardening in the summer"),
        _paper("Notes on baking bread"),
        _paper("A history of jazz music"),
    ]
    index = build_bm25_index([graph, *others])

    hits = rank_bm25_over("knowledge graph", index)

    # Only the paper actually containing the terms contributes.
    assert [item for item, _ in hits] == [graph]


def test_empty_pool_returns_none_index() -> None:
    assert build_bm25_index([]) is None
    assert rank_bm25_over("anything", None) == []


def test_empty_query_returns_no_hits() -> None:
    index = build_bm25_index([_paper("Knowledge graphs")])

    assert rank_bm25_over("", index) == []
    assert rank_bm25_over("   ", index) == []


def test_pool_without_text_returns_none_index() -> None:
    blank = ContentItem(type=ContentItem.Type.PAPER, metadata={})

    assert build_bm25_index([blank]) is None
