"""Query-first search: lexical FTS, filters, facets, fusion, and the endpoint.

The full-text query (``search_vector`` + trigger) needs PostgreSQL, so the
DB-backed cases skip on SQLite (point ``DATABASE_URL`` at Postgres to run them,
as the pgvector suite does). The pure fusion/normalization cases always run.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from tools.delivery.models import SavedOpportunity
from tools.retrieval import embeddings
from tools.retrieval.models import ContentItem
from tools.retrieval.query_embedding import embed_query
from tools.retrieval.search import (
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
    title: str,
    *,
    abstract: str = "",
    authors=None,
    source="OpenAlex",
    ext=None,
    embedding=None,
):
    return ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source=source,
        external_id=ext or title,
        source_url="https://example.org/p",
        embedding=embedding,
        metadata={
            "title": title,
            "abstract": abstract,
            "authors": authors or [],
            "venue": "Nature",
            "year": 2026,
        },
    )


def _grant(title: str, *, sponsor: str = "", source="legacy", ext=None):
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
    # Every surfaced item is tagged with its fused score + matched channels.
    assert result.items[0]._search_score > 0
    assert "lexical" in result.items[0]._search_matched_on
    assert result.confidence == "ok"  # no semantic channel here, never abstains


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
    # A single selected type exposes that type's own facet (grant → sponsor).
    assert result.facets["sponsor"] == [{"value": "NSF", "count": 1}]
    # No stale "source" facet remains on the search path.
    assert "source" not in result.facets


@pytest.mark.django_db
def test_per_type_facet_is_contextual_to_a_single_type(pg) -> None:
    # No type selected → only the type facet (per-type facets need a drill-in).
    _paper("Quantum computing advances")
    _grant("Quantum sensing grant", sponsor="NSF")
    result = run_search("quantum")
    assert set(result.facets) == {"type"}

    # Papers selected → the paper facet is `year`, not sponsor/country.
    papers = run_search("quantum", filters=SearchFilters(types=("paper",)))
    assert papers.facets["year"] == [{"value": "2026", "count": 1}]
    assert "sponsor" not in papers.facets


@pytest.mark.django_db
def test_metadata_facet_filter_scopes_and_counts_ignore_self(pg) -> None:
    # Two sponsors under the same query; the facet lists both with counts…
    _grant("Robotics program grant", sponsor="NSF", ext="g-nsf")
    darpa = _grant("Robotics systems grant", sponsor="DARPA", ext="g-darpa")

    base = run_search("robotics", filters=SearchFilters(types=("grant",)))
    sponsor_counts = {r["value"]: r["count"] for r in base.facets["sponsor"]}
    assert sponsor_counts == {"NSF": 1, "DARPA": 1}

    # …selecting one narrows the results but the facet still shows both, so the
    # user can widen the multi-select (counts ignore the facet's own selection).
    filtered = run_search(
        "robotics",
        filters=SearchFilters(types=("grant",), sponsors=("DARPA",)),
    )
    assert [str(i.id) for i in filtered.items] == [str(darpa.id)]
    assert {r["value"] for r in filtered.facets["sponsor"]} == {"NSF", "DARPA"}


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
    assert result.facets == {"type": []}


@pytest.mark.django_db
def test_search_does_not_abstain_on_a_weak_single_match(pg) -> None:
    # A one-term lexical match is still returned — search never abstains.
    paper = _paper("Bioinformatics pipelines", abstract="metagenomics workflows")
    result = run_search("metagenomics")
    assert [str(i.id) for i in result.items] == [str(paper.id)]


# --------------------------------------------------------------------------- #
# Semantic channel + RRF fusion (PostgreSQL + pgvector)
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_semantic_surfaces_item_with_no_keyword_overlap(pg) -> None:
    # The query shares no lexemes with either title, so only the vector channel
    # can find anything — and it must, without abstaining.
    near = _paper("Alpha manuscript", embedding=[1.0, 0.0, 0.0])
    _paper("Beta manuscript", embedding=[0.0, 1.0, 0.0])

    result = run_search("zzzznonlexical", query_vector=[1.0, 0.0, 0.0])

    # The semantic channel ranks by similarity, so the nearest item leads. The
    # orthogonal item (cosine 0) sits below the floor and is dropped — but a real
    # hit still surfaces, so search does not abstain.
    assert str(result.items[0].id) == str(near.id)
    assert result.items[0]._search_matched_on == ["semantic"]
    assert result.confidence == "ok"  # top cosine ~1.0


@pytest.mark.django_db
def test_low_confidence_cue_when_top_cosine_is_weak(pg, settings) -> None:
    settings.SEARCH_SEMANTIC_FLOOR = 0.30
    settings.SEARCH_LOW_CONFIDENCE_COSINE = 0.35
    _paper("Alpha manuscript", embedding=[1.0, 0.0, 0.0])

    # Cosine ~0.32 sits in the [floor, cue) band: above the inclusion floor (so
    # it is still returned) but below the display cue.
    result = run_search("zzzznonlexical", query_vector=[0.32, 0.9474, 0.0])

    assert result.count == 1  # still returned — a cue, not a gate
    assert result.confidence == "low"


@pytest.mark.django_db
def test_semantic_floor_excludes_far_field_items(pg, settings) -> None:
    # A vaguely-related neighbour (cosine ~0.15 < floor) is not admitted by the
    # semantic channel, so an otherwise-unmatched query returns nothing instead of
    # padding the pool with far-field items. Lexical/fuzzy would still surface a
    # genuine term/typo hit — only the loose semantic tail is trimmed.
    settings.SEARCH_SEMANTIC_FLOOR = 0.30
    _paper("Alpha manuscript", embedding=[1.0, 0.0, 0.0])

    result = run_search("zzzznonlexical", query_vector=[0.15, 0.9887, 0.0])

    assert result.count == 0
    assert result.items == []


@pytest.mark.django_db
def test_fused_beats_either_single_signal(pg) -> None:
    # `both` matches lexically (title) AND semantically (vector). The lexical-only
    # item has no embedding (absent from the semantic channel); the semantic-only
    # item's title shares no term with the query (absent from lexical/fuzzy). So
    # only `both` matches multiple channels, and it must rank first.
    both = _paper("Quantum computing", embedding=[1.0, 0.0, 0.0])
    _paper("Quantum theory", embedding=None)  # lexical + fuzzy only
    _paper("Photonics device", embedding=[1.0, 0.0, 0.0])  # semantic only

    result = run_search("quantum", query_vector=[1.0, 0.0, 0.0])

    assert str(result.items[0].id) == str(both.id)
    assert {"lexical", "semantic"} <= set(result.items[0]._search_matched_on)


# --------------------------------------------------------------------------- #
# Fuzzy channel + sort modes + query-embedding cache
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_fuzzy_recovers_a_typo_when_lexical_cannot(pg) -> None:
    # "Photosynthessis" shares no lexeme with "Photosynthesis", so lexical finds
    # nothing; only the trigram channel can recover the item.
    paper = _paper("Photosynthesis")

    result = run_search("Photosynthessis")

    assert [str(i.id) for i in result.items] == [str(paper.id)]
    assert result.items[0]._search_matched_on == ["fuzzy"]  # lexical missed it


@pytest.mark.django_db
def test_deadline_sort_soonest_first_nulls_last(pg) -> None:
    grant = ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="legacy",
        external_id="q-grant",
        metadata={"title": "Quantum grant", "deadline_date": "2026-09-01"},
    )
    fellowship = ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois",
        external_id="q-fellow",
        metadata={"title": "Quantum fellowship", "deadline": {"date": "2026-07-15"}},
    )
    paper = _paper("Quantum computing paper")  # no deadline

    result = run_search("quantum", sort="deadline")

    ordered = [str(i.id) for i in result.items]
    assert ordered == [str(fellowship.id), str(grant.id), str(paper.id)]


@pytest.mark.django_db
def test_date_sort_is_newest_first(pg) -> None:
    older = _paper("Genomics one", ext="d1")
    newer = _paper("Genomics two", ext="d2")
    ContentItem.objects.filter(pk=older.pk).update(
        created_at=timezone.now() - timedelta(days=3)
    )

    result = run_search("genomics", sort="date")

    assert [str(i.id) for i in result.items] == [str(newer.id), str(older.id)]


def test_embed_query_caches_and_skips_the_model(settings) -> None:
    """A repeated query is served from cache — the model runs at most once."""
    settings.CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
        "search": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "search-test",
        },
    }
    from django.core.cache import caches

    caches["search"].clear()
    calls = {"n": 0}

    def fake(texts: list[str]) -> list[list[float]]:
        calls["n"] += 1
        return [[0.1, 0.2, 0.3] for _ in texts]

    embeddings.set_embedder(fake)
    try:
        first = embed_query("protein folding")
        second = embed_query("protein folding")
    finally:
        embeddings.reset_embedder()

    assert list(first) == [0.1, 0.2, 0.3]
    assert list(second) == [0.1, 0.2, 0.3]
    assert calls["n"] == 1  # second call hit the cache


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
    assert "lexical" in hit["matched_on"]
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
    # "source" is gone from the search payload (facet + per-result field).
    assert "source" not in resp.data["facets"]
    assert "source" not in resp.data["results"][0]


@pytest.mark.django_db
def test_endpoint_exposes_and_applies_a_per_type_facet(pg, client: APIClient) -> None:
    _grant("Ocean sensing grant", sponsor="NSF", ext="g-nsf")
    _grant("Ocean robotics grant", sponsor="ONR", ext="g-onr")
    client.force_authenticate(User.objects.create_user("oceanographer", password="x"))

    # A single selected type surfaces its facet key…
    listed = client.get("/api/search/", {"q": "ocean", "type": "grant"})
    assert {r["value"] for r in listed.data["facets"]["sponsor"]} == {"NSF", "ONR"}

    # …and the matching param narrows the results.
    narrowed = client.get(
        "/api/search/", {"q": "ocean", "type": "grant", "sponsor": "ONR"}
    )
    assert [r["title"] for r in narrowed.data["results"]] == ["Ocean robotics grant"]
