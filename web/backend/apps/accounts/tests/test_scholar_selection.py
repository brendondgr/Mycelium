"""Phase C — the Google Scholar popular-10 + recent-10 selection (no network)."""

from apps.accounts.intake.retrievers.scholar import _pub_key, select_publications

from .intake_fixtures import scholar_selection_pubs


def _keys(pubs) -> list[str]:
    return [_pub_key(p) for p in pubs]


def test_selection_is_capped_at_20() -> None:
    out = select_publications(scholar_selection_pubs())
    assert len(out) <= 20


def test_no_duplicates() -> None:
    out = select_publications(scholar_selection_pubs())
    keys = _keys(out)
    assert len(keys) == len(set(keys))


def test_overlap_appears_once() -> None:
    out = select_publications(scholar_selection_pubs())
    assert _keys(out).count("OVERLAP") == 1


def test_single_most_cited_present() -> None:
    out = select_publications(scholar_selection_pubs())
    assert "OVERLAP" in _keys(out)  # 10000 citations — the top-cited paper


def test_missing_year_excluded_from_recent() -> None:
    pubs = scholar_selection_pubs()
    out = select_publications(pubs)
    # MISSING is neither top-10 cited (500 cites) nor recent (no year): excluded.
    assert "MISSING" not in _keys(out)


def test_result_equals_union_of_cited_and_recent() -> None:
    pubs = scholar_selection_pubs()
    out_keys = set(_keys(select_publications(pubs)))

    by_cites = sorted(pubs, key=lambda p: p.get("num_citations", 0), reverse=True)
    expected_cited = {_pub_key(p) for p in by_cites[:10]}
    recent = sorted(
        pubs,
        key=lambda p: int(p["bib"]["pub_year"]) if p["bib"].get("pub_year") else -1,
        reverse=True,
    )
    expected_recent = {_pub_key(p) for p in recent[:10]}

    assert out_keys == expected_cited | expected_recent
    assert len(out_keys) == 19  # 10 + 10 - 1 overlap


def test_empty_input() -> None:
    assert select_publications([]) == []
