"""One search path, shared by the web app and Mylo.

``search.run_search`` is deliberately embedder- and cache-free so it stays unit
testable with an injected vector. Everything *around* it — normalising the query,
embedding it, attaching saved state and the reader's cluster badge — used to live
inline in ``SearchView.get``, which meant a second caller had only two options: call
`run_search` alone and quietly show worse results than the website, or copy the view's
body and drift from it.

So the whole of it lives here, and the view is one of two callers. If Mylo and the
portal ever disagree about the same query, it is a bug in one function rather than a
difference of opinion between two.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.content.query_embedding import embed_query
from apps.content.search import SearchFilters, SearchResult, normalize_query, run_search


@dataclass(frozen=True)
class SearchContext:
    """A completed search plus the per-reader state the results are rendered with."""

    result: SearchResult
    saved_ids: set
    saved_labs: dict
    #: Content ids this reader manually ignored. Search results are **not**
    #: filtered by it — if you typed the query, suppressing the hit would be
    #: dishonest — but the card shows the state, so search doubles as the way to
    #: find something you dismissed and put it back.
    ignored_ids: set

    @property
    def items(self) -> list:
        return self.result.items


def search_for_user(
    user,
    query: str,
    *,
    filters: SearchFilters | None = None,
    sort: str = "relevance",
    limit=None,
    offset: int = 0,
) -> SearchContext:
    """Run a query the way the portal runs it, for ``user``.

    The embedding is the slow step and is Redis-cached by normalised query, so two
    people searching the same words pay for it once.
    """
    from apps.content.views import (
        _attach_search_clusters,
        _ignored_content_ids,
        _saved_content_ids,
        _saved_lab_slugs_by_content,
    )

    normalized = normalize_query(query)
    query_vector = embed_query(normalized) if normalized else None

    result = run_search(
        query,
        filters=filters or SearchFilters(),
        sort=sort,
        limit=limit,
        offset=offset,
        query_vector=query_vector,
    )

    saved_ids = _saved_content_ids(user) if result.items else set()
    saved_labs = _saved_lab_slugs_by_content(user) if result.items else {}
    ignored_ids = (
        {str(cid) for cid in _ignored_content_ids(user)} if result.items else set()
    )
    if result.items:
        # Cluster attribution is a per-reader view of a shared corpus row: which of
        # *this* researcher's focus areas the hit belongs to. It is attached after the
        # search, not during it, and only when they have more than one cluster.
        _attach_search_clusters(result.items, user)
    return SearchContext(
        result=result,
        saved_ids=saved_ids,
        saved_labs=saved_labs,
        ignored_ids=ignored_ids,
    )
