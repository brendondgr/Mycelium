"""The pure search-interest modelling: dedupe, order, keyword attachment, no-op."""

from apps.content.interests_query import SearchInterest, search_interests


def test_one_interest_per_area_order_preserving_and_deduped() -> None:
    interests = {
        "areas": ["Knowledge Graphs", "Biomedical NLP", "knowledge graphs"],
    }

    result = search_interests(interests)

    assert [i.label for i in result] == ["Knowledge Graphs", "Biomedical NLP"]
    assert all(isinstance(i, SearchInterest) for i in result)


def test_keywords_attach_to_every_interest_query() -> None:
    interests = {
        "areas": ["Knowledge Graphs", "Biomedical NLP"],
        "keywords": ["retrieval augmented generation", "ontology"],
    }

    result = search_interests(interests)

    for interest in result:
        assert interest.label in interest.query_text
        assert "retrieval augmented generation" in interest.query_text
        assert "ontology" in interest.query_text
        # embed_text mirrors query_text so the vector channel carries vocabulary.
        assert interest.embed_text == interest.query_text


def test_no_keywords_leaves_query_as_the_area() -> None:
    result = search_interests({"areas": ["Knowledge Graphs"]})

    assert result[0].query_text == "Knowledge Graphs"
    assert result[0].embed_text == "Knowledge Graphs"


def test_empty_areas_is_a_no_op() -> None:
    assert search_interests({}) == []
    assert search_interests({"areas": []}) == []
    assert search_interests({"areas": ["", "   "]}) == []
    assert search_interests(None) == []
