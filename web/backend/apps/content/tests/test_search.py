"""Query-first search: lexical FTS, filters, facets, fusion, and the endpoint.

The full-text query (``search_vector`` + trigger) needs PostgreSQL, so the
DB-backed cases skip on SQLite (CI runs them against the Postgres service, as the
pgvector suite does). The pure fusion/normalization cases always run.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.db import connection
from rest_framework.test import APIClient

from apps.content.models import ContentItem, SavedOpportunity
from apps.content.search import (
    DEFAULT_RRF_K,
    SearchFilters,
    clamp_limit,
    clean_sort,
    normalize_query,
    rrf_fuse,
    run_search,
)

# --------------------------------------------------------------------------- #
# Pure unit tests (no database) — normalization + rank-only fusion
# --------------------------------------------------------------------------- #


def test_normalize_query_folds_and_collapses() -> None:
    assert normalize_query("  Protein   Folding ") == "protein folding"
    assert normalize_query(None) == ""
    assert normalize_query("\t\n ") == ""


def test_clean_sort_defaults_to_relevance() -> None:
    assert clean_sort("date") == "date"
    assert clean_sort("DEADLINE") == "deadline"
    assert clean_sort("bogus") == "relevance"
    assert clean_sort(None) == "relevance"


def test_clamp_limit_bounds(settings) -> None:
    settings.SEARCH_PAGE_SIZE = 20
    settings.SEARCH_MAX_PAGE_SIZE = 50
    assert clamp_limit(None) == 20
    assert clamp_limit(0) == 1
    assert clamp_limit(9999) == 50
    assert clamp_limit("garbage") == 20


def test_rrf_is_rank_only_not_score_magnitude() -> None:
    """RRF combines rank positions only — raw channel magnitudes never enter.

    The two channels are just ordered id lists (no scores), so an item's fused
    weight depends solely on where it ranks. Symmetric positions ⇒ equal scores;
    this is the "normalize before fusing" invariant for the search path.
    """
    fused = rrf_fuse({"lexical": ["x", "y"], "semantic": ["y", "x"]})
    assert fused["x"] == pytest.approx(fused["y"])
    expected = 1.0 / (DEFAULT_RRF_K + 1) + 1.0 / (DEFAULT_RRF_K + 2)
    assert fused["x"] == pytest.approx(expected)


def test_rrf_rewards_matching_more_channels() -> None:
    # `both` is #2 in each channel; `one` is #1 in a single channel. Matching two
    # channels should still beat a single top-ranked hit.
    fused = rrf_fuse({"lexical": ["one", "both"], "semantic": ["z", "both"]})
    assert fused["both"] > fused["one"]


# --------------------------------------------------------------------------- #
# Database-backed lexical tests (PostgreSQL only)
# --------------------------------------------------------------------------- #


@pytest.fixture
def pg(db: None):
    if connection.vendor != "postgresql":
        pytest.skip("full-text search requires PostgreSQL")


def _paper(
    title: str, *, abstract: str = "", authors=None, source="OpenAlex", ext=None
):
    return ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source=source,
        external_id=ext or title,
        source_url="https://example.org/p",
        metadata={
            "title": title,
            "abstract": abstract,
            "authors": authors or [],
            "venue": "Nature",
            "year": 2026,
        },
    )


def _grant(title: str, *, sponsor: str = "", source="pivot", ext=None):
    return ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source=source,
        external_id=ext or title,
        metadata={"title": title, "sponsor": sponsor, "amount": "$50,000"},
    )


@pytest.mark.django_db
def test_exact_title_ranks_above_body_mention(pg) -> None:
    title_hit = _paper("Deep learning for protein folding")
    body_hit = _paper(
        "A survey of machine learning",
        abstract="Includes a note on protein folding among many topics.",
    )

    result = run_search("protein folding")

    ids = [str(item.id) for item in result.items]
    assert ids[0] == str(title_hit.id)  # title (weight A) beats body (weight B)
    assert str(body_hit.id) in ids
    # Every surfaced item is tagged with its fused score + matched channel.
    assert result.items[0]._search_score > 0
    assert result.items[0]._search_matched_on == ["lexical"]
    assert result.confidence == "ok"  # no semantic channel yet, never abstains


@pytest.mark.django_db
def test_author_name_is_a_lexical_hit(pg) -> None:
    paper = _paper("Compiler theory", authors=["Grace Hopper", "John Backus"])
    _paper("Unrelated networking paper")

    result = run_search("Hopper")

    assert [str(i.id) for i in result.items] == [str(paper.id)]


@pytest.mark.django_db
def test_grant_sponsor_is_a_lexical_hit(pg) -> None:
    grant = _grant("Autonomy research award", sponsor="DARPA")
    _paper("A paper about cats")

    result = run_search("DARPA")

    assert [str(i.id) for i in result.items] == [str(grant.id)]
    assert result.items[0].type == ContentItem.Type.GRANT


@pytest.mark.django_db
def test_type_filter_scopes_results_but_type_facet_shows_all(pg) -> None:
    _paper("Quantum computing advances")
    grant = _grant("Quantum sensing grant", sponsor="NSF")

    result = run_search("quantum", filters=SearchFilters(types=("grant",)))

    # Results are scoped to the requested type…
    assert [str(i.id) for i in result.items] == [str(grant.id)]
    assert all(i.type == ContentItem.Type.GRANT for i in result.items)
    # …but the type facet still counts both, so the user can switch types.
    type_facet = {row["value"]: row["count"] for row in result.facets["type"]}
    assert type_facet == {"paper": 1, "grant": 1}
    # The source facet respects the active type filter (grant sources only).
    source_facet = {row["value"] for row in result.facets["source"]}
    assert source_facet == {"pivot"}


@pytest.mark.django_db
def test_pagination_is_offset_within_the_pool(pg) -> None:
    for i in range(5):
        _paper(f"Genomics study {i}", ext=f"g{i}")

    first = run_search("genomics", limit=2, offset=0)
    assert first.count == 5
    assert len(first.items) == 2
    assert first.next_offset == 2

    last = run_search("genomics", limit=2, offset=4)
    assert len(last.items) == 1
    assert last.next_offset is None


@pytest.mark.django_db
def test_blank_query_returns_empty_never_errors(pg) -> None:
    _paper("Something searchable")
    result = run_search("   ")
    assert result.count == 0
    assert result.items == []
    assert result.next_offset is None
    assert result.facets == {"type": [], "source": []}


@pytest.mark.django_db
def test_search_does_not_abstain_on_a_weak_single_match(pg) -> None:
    # A one-term lexical match is still returned — search never abstains.
    paper = _paper("Bioinformatics pipelines", abstract="metagenomics workflows")
    result = run_search("metagenomics")
    assert [str(i.id) for i in result.items] == [str(paper.id)]


# --------------------------------------------------------------------------- #
# Endpoint tests
# --------------------------------------------------------------------------- #


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_endpoint_requires_authentication(client: APIClient) -> None:
    assert client.get("/api/search/?q=anything").status_code in (401, 403)


@pytest.mark.django_db
def test_endpoint_returns_shape_and_results(pg, client: APIClient) -> None:
    _paper("Reinforcement learning for robotics")
    user = User.objects.create_user("searcher", password="x")
    client.force_authenticate(user)

    resp = client.get("/api/search/", {"q": "reinforcement learning"})

    assert resp.status_code == 200
    body = resp.data
    assert {
        "query",
        "normalized",
        "sort",
        "confidence",
        "count",
        "pool_truncated",
        "facets",
        "limit",
        "offset",
        "next_cursor",
        "results",
    } <= set(body)
    assert body["count"] == 1
    hit = body["results"][0]
    assert hit["type"] == "paper"
    assert hit["title"] == "Reinforcement learning for robotics"
    assert hit["matched_on"] == ["lexical"]
    assert hit["saved"] is False


@pytest.mark.django_db
def test_endpoint_type_filter_and_saved_flag(pg, client: APIClient) -> None:
    _paper("Climate modelling with ML")
    grant = _grant("Climate resilience fund", sponsor="NOAA")
    user = User.objects.create_user("me", password="x")
    SavedOpportunity.objects.create(
        user=user, content=grant, area=SavedOpportunity.Area.GRANT, title="saved"
    )
    client.force_authenticate(user)

    resp = client.get("/api/search/", {"q": "climate", "type": "grant"})

    assert resp.status_code == 200
    assert [r["type"] for r in resp.data["results"]] == ["grant"]
    assert resp.data["results"][0]["saved"] is True
