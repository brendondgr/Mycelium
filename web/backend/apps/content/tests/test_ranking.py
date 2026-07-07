"""The research-focus re-rank: overlap scoring and weighted re-ordering."""

from types import SimpleNamespace

from apps.content.ranking import focus_overlap, rerank_by_focus


def _item(title: str = "", abstract: str = ""):
    # rerank only reads ``.metadata``, so a lightweight stand-in avoids the DB.
    meta = {"title": title, "abstract": abstract}
    return SimpleNamespace(id=title or "x", metadata=meta)


def test_focus_overlap_is_fraction_of_areas_present() -> None:
    item = _item("A paper on graphs and retrieval")
    fraction, matched = focus_overlap(["graphs", "retrieval", "genomics"], item)

    assert matched == ["graphs", "retrieval"]
    assert fraction == 2 / 3


def test_focus_overlap_zero_without_text_or_areas() -> None:
    assert focus_overlap([], _item("anything")) == (0.0, [])
    assert focus_overlap(["graphs"], _item("", "")) == (0.0, [])


def test_rerank_boosts_focus_matches_above_raw_similarity() -> None:
    on_focus = _item("knowledge graphs for biomedicine")  # matches the focus area
    off_focus = _item("an unrelated survey")  # slightly higher raw similarity
    hits = [(off_focus, 0.60), (on_focus, 0.50)]

    ranked = rerank_by_focus(hits, ["knowledge graphs"], weight=0.25)

    # The focus boost (0.50 + 0.25*1.0 = 0.75) overtakes the raw 0.60.
    assert [hit.item for hit in ranked] == [on_focus, off_focus]
    assert ranked[0].similarity == 0.50
    assert ranked[0].focus_overlap == 1.0
    assert ranked[0].matched_areas == ["knowledge graphs"]
    assert ranked[0].score == 0.75


def test_rerank_is_order_preserving_noop_without_areas() -> None:
    a, b = _item("first"), _item("second")
    hits = [(a, 0.9), (b, 0.4)]

    ranked = rerank_by_focus(hits, [], weight=0.25)

    assert [hit.item for hit in ranked] == [a, b]
    assert all(hit.focus_overlap == 0.0 for hit in ranked)
    assert ranked[0].score == 0.9  # blended == raw similarity when no boost
