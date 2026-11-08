"""The pure search-interest modelling: dedupe, order, keyword attachment, no-op."""

from tools.recommendation.interests_query import SearchInterest, search_interests


def test_one_interest_per_area_order_preserving_and_deduped() -> None:
    interests = {
        "areas": ["Knowledge Graphs", "Biomedical NLP", "knowledge graphs"],
    }

    result = search_interests(interests)

    assert [i.label for i in result] == ["Knowledge Graphs", "Biomedical NLP"]
    assert all(isinstance(i, SearchInterest) for i in result)


def test_keywords_no_longer_attach_to_every_interest_query() -> None:
    """They used to, and that is the defect this function was rewritten to remove.

    On a real profile the shared suffix was 473 characters against a 24-character
    label, so every area searched for nearly the same string and one document
    could score the normalised maximum on all of them at once.
    """
    interests = {
        "areas": ["Knowledge Graphs", "Biomedical NLP"],
        "keywords": ["retrieval augmented generation", "ontology"],
    }

    result = search_interests(interests)

    for interest in result:
        assert interest.query_text == interest.label
        assert "ontology" not in interest.query_text
        assert interest.embed_text == interest.query_text


def test_context_is_the_interests_own_theme_and_is_capped() -> None:
    from tools.recommendation.clustering import Cluster

    interests = {"areas": ["a", "b", "c", "d", "e", "z"]}
    clusters = [
        Cluster(id="c-1", label="One", areas=["a", "b", "c", "d", "e"]),
        Cluster(id="c-2", label="Two", areas=["z"]),
    ]

    result = {
        i.label: i.query_text
        for i in search_interests(interests, clusters=clusters, context_limit=3)
    }

    # Three siblings at most, so a wide theme cannot rebuild the old suffix.
    assert result["a"] == "a b c d"
    # A theme's context never crosses into another theme.
    assert result["z"] == "z"


def test_the_implicit_cluster_contributes_no_context() -> None:
    """It holds every area, so its "siblings" are the profile-wide suffix again."""
    from tools.recommendation.clustering import cluster_interests

    interests = {"areas": ["graph", "health", "robotics"]}
    clusters = cluster_interests(interests)

    assert len(clusters) == 1 and clusters[0].is_implicit
    result = search_interests(interests, clusters=clusters)
    assert [i.query_text for i in result] == ["graph", "health", "robotics"]


def test_context_can_be_switched_off_entirely() -> None:
    from tools.recommendation.clustering import Cluster

    clusters = [Cluster(id="c-1", label="One", areas=["a", "b"])]
    result = search_interests(
        {"areas": ["a", "b"]}, clusters=clusters, context_limit=0
    )

    assert [i.query_text for i in result] == ["a", "b"]


def test_no_context_leaves_query_as_the_area() -> None:
    result = search_interests({"areas": ["Knowledge Graphs"]})

    assert result[0].query_text == "Knowledge Graphs"
    assert result[0].embed_text == "Knowledge Graphs"


def test_empty_areas_is_a_no_op() -> None:
    assert search_interests({}) == []
    assert search_interests({"areas": []}) == []
    assert search_interests({"areas": ["", "   "]}) == []
    assert search_interests(None) == []
