"""Suggestion generation: LLM seam when reachable, similarity fallback otherwise."""

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


def test_llm_path_uses_model_ranking() -> None:
    hits = _hits()

    def complete(_prompt: str) -> str:
        return json.dumps(
            {
                "suggestions": [
                    {"paper": 2, "headline": "Graphs for Care", "reason": "On topic."},
                    {"paper": 1, "headline": "Graph Methods", "reason": "Methods."},
                ]
            }
        )

    out = generate_suggestions(INTERESTS, hits, complete=complete)

    assert [s["rank"] for s in out] == [1, 2]
    assert out[0]["content_id"] == str(hits[1][0].id)  # model put paper 2 first
    assert out[0]["headline"] == "Graphs for Care"
    assert all(s["source"] == "llm" for s in out)
    assert out[0]["similarity"] == 0.78


def test_limit_caps_llm_suggestions() -> None:
    hits = _hits()

    def complete(_prompt: str) -> str:
        rows = [{"paper": i, "headline": f"h{i}", "reason": "r"} for i in (1, 2, 3)]
        return json.dumps({"suggestions": rows})

    out = generate_suggestions(INTERESTS, hits, complete=complete, limit=2)

    assert len(out) == 2


def test_fallback_when_no_model() -> None:
    hits = _hits()

    out = generate_suggestions(INTERESTS, hits, complete=lambda _p: None, limit=2)

    assert [s["rank"] for s in out] == [1, 2]
    assert all(s["source"] == "fallback" for s in out)
    # Order follows similarity (already sorted desc).
    assert out[0]["content_id"] == str(hits[0][0].id)


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

    out = generate_suggestions(INTERESTS, _hits(), complete=boom, limit=1)

    assert len(out) == 1 and out[0]["source"] == "fallback"


def test_no_hits_returns_empty() -> None:
    assert generate_suggestions(INTERESTS, [], complete=lambda _p: "x") == []


def test_out_of_range_paper_index_is_skipped() -> None:
    hits = _hits()

    def complete(_prompt: str) -> str:
        return json.dumps(
            {"suggestions": [{"paper": 99, "headline": "x", "reason": "y"}]}
        )

    # The only row references a non-existent paper -> nothing usable -> fallback.
    out = generate_suggestions(INTERESTS, hits, complete=complete)

    assert out and all(s["source"] == "fallback" for s in out)
