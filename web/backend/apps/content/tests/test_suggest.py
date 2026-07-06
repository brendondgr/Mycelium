"""Suggestion generation: the two-tier (top-N LLM + fallback tail) digest."""

import json

from apps.content.models import ContentItem
from apps.content.suggest import generate_suggestions

INTERESTS = {
    "statement": "I study knowledge graphs in healthcare.",
    "areas": ["Knowledge Graphs", "AI in Healthcare"],
    "keywords": ["biomedical knowledge discovery"],
}


def _paper(title: str, abstract: str = "") -> ContentItem:
    # Unsaved is fine: suggest only reads ``id`` (auto uuid) and ``metadata``.
    return ContentItem(
        type=ContentItem.Type.PAPER,
        source="test",
        metadata={"title": title, "abstract": abstract, "year": 2026},
    )


def _hits():
    a = _paper("Graph Methods", "general graph theory")
    b = _paper("Biomedical Knowledge Discovery", "knowledge graphs for clinical data")
    c = _paper("Unrelated Paper", "something else")
    return [(a, 0.81), (b, 0.78), (c, 0.40)]


def _many(n: int):
    """n candidates with descending scores, so we can probe the tier boundary."""
    return [(_paper(f"Paper {i}", "graph"), 1.0 - i * 0.01) for i in range(n)]


def test_llm_ranks_top_slice_then_fallback_fills_the_rest() -> None:
    hits = _hits()

    def complete(_prompt: str) -> str:
        return json.dumps(
            {
                "suggestions": [
                    {
                        "paper": 2,
                        "match": 92,
                        "headline": "Graphs for Care",
                        "reason": "On topic.",
                    },
                    {"paper": 1, "headline": "Graph Methods", "reason": "Methods."},
                ]
            }
        )

    out = generate_suggestions(INTERESTS, hits, complete=complete)

    assert [s["rank"] for s in out] == [1, 2, 3]
    # The model put paper 2 first; its two picks lead as source="llm".
    assert out[0]["content_id"] == str(hits[1][0].id)
    assert out[0]["headline"] == "Graphs for Care"
    assert out[0]["source"] == "llm"
    assert out[0]["similarity"] == 0.78
    assert out[0]["match_percent"] == 92  # carried through, clamped to 0-100
    assert out[1]["source"] == "llm"
    assert out[1]["match_percent"] is None  # model gave no "match" -> no percent
    # The paper the model did not pick is a cross-embedding match: no percent.
    assert out[2]["content_id"] == str(hits[2][0].id)
    assert out[2]["source"] == "fallback"
    assert out[2]["match_percent"] is None


def test_only_top_llm_limit_papers_are_llm_ranked() -> None:
    hits = _many(25)

    def complete(_prompt: str) -> str:
        # The model ranks every paper it is shown, best first.
        rows = [
            {"paper": i + 1, "match": 90, "headline": "h", "reason": "r"}
            for i in range(25)
        ]
        return json.dumps({"suggestions": rows})

    out = generate_suggestions(
        INTERESTS, hits, llm_limit=10, surface_limit=25, complete=complete
    )

    # Exactly the top 10 are LLM-ranked; the model was only ever shown those 10,
    # so any paper beyond rank 10 must be a deterministic fallback.
    assert len(out) == 25
    assert [s["source"] for s in out[:10]] == ["llm"] * 10
    assert [s["source"] for s in out[10:]] == ["fallback"] * 15


def test_surface_limit_caps_total_suggestions() -> None:
    out = generate_suggestions(
        INTERESTS, _many(25), surface_limit=5, complete=lambda _p: None
    )

    assert len(out) == 5
    assert [s["rank"] for s in out] == [1, 2, 3, 4, 5]


def test_llm_match_is_clamped_or_dropped() -> None:
    hits = _hits()

    def complete(_prompt: str) -> str:
        return json.dumps(
            {
                "suggestions": [
                    {"paper": 1, "match": 150, "headline": "A", "reason": "r"},
                    {"paper": 2, "match": "oops", "headline": "B", "reason": "r"},
                ]
            }
        )

    out = generate_suggestions(INTERESTS, hits, complete=complete)

    assert out[0]["match_percent"] == 100  # clamped down from 150
    assert out[1]["match_percent"] is None  # garbled -> no fabricated percent


def test_fallback_when_no_model() -> None:
    hits = _hits()

    out = generate_suggestions(
        INTERESTS, hits, surface_limit=2, complete=lambda _p: None
    )

    assert [s["rank"] for s in out] == [1, 2]
    assert all(s["source"] == "fallback" for s in out)
    # Order follows score (already sorted desc).
    assert out[0]["content_id"] == str(hits[0][0].id)
    # Cross-embedding matches never carry a fabricated percent.
    assert all(s["match_percent"] is None for s in out)


def test_fallback_reason_names_overlapping_interest() -> None:
    hits = _hits()

    out = generate_suggestions(INTERESTS, hits, complete=lambda _p: None)

    # Paper 2's text contains "knowledge graphs" -> matches a keyword/area term.
    reason = next(s["reason"] for s in out if s["content_id"] == str(hits[1][0].id))
    assert "interest in" in reason.lower()


def test_fallback_on_unparseable_response() -> None:
    out = generate_suggestions(INTERESTS, _hits(), complete=lambda _p: "not json")

    assert out and all(s["source"] == "fallback" for s in out)


def test_fallback_on_raising_model() -> None:
    def boom(_prompt: str) -> str:
        raise RuntimeError("endpoint down")

    out = generate_suggestions(INTERESTS, _hits(), surface_limit=1, complete=boom)

    assert len(out) == 1 and out[0]["source"] == "fallback"


def test_no_hits_returns_empty() -> None:
    assert generate_suggestions(INTERESTS, [], complete=lambda _p: "x") == []


def test_out_of_range_paper_index_is_skipped() -> None:
    hits = _hits()

    def complete(_prompt: str) -> str:
        return json.dumps(
            {"suggestions": [{"paper": 99, "headline": "x", "reason": "y"}]}
        )

    # The only row references a non-existent paper -> no llm picks -> all fallback.
    out = generate_suggestions(INTERESTS, hits, complete=complete)

    assert out and all(s["source"] == "fallback" for s in out)
