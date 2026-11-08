from pathlib import Path

from tools.fulltext.engine.pipeline import Engine


def test_resolve_cross_checks_and_plans_without_fetching(engine):
    out = engine.resolve(
        [
            "111",
            {"pmid": "111", "doi": "10.1002/tox.222"},  # different article
            {"pmid": "222", "title": "Something else entirely about fish"},
            "PMC333",
            "999",
            "10.9999/not-in-pubmed",
            "10.9999/typo",
            "https://www.sciencedirect.com/science/article/pii/S0269749120000001",
            "Nanoplastics and the heart",
            "plastic",
        ]
    )
    st = [r["status"] for r in out]
    assert st == [
        "resolved",
        "identifier_mismatch",
        "identifier_mismatch",
        "resolved",
        "not_found",
        "resolved",
        "not_found",
        "resolved",
        "resolved",
        "invalid_identifier",
    ]
    assert out[0]["metadata"]["title"] == "Microplastics in the brain"
    assert out[0]["will_try"][:2] == ["europepmc", "elsevier"]
    assert out[3]["ids"] == {
        "pmid": "333",
        "pmcid": "PMC333",
        "doi": "10.3390/ijms333",
        "arxiv": None,
    }
    assert out[3]["will_try"][0] == "pmc"
    assert "Crossref" in out[5]["notes"][0]
    assert out[7]["ids"]["pmid"] == "111"
    assert out[8]["ids"]["pmid"] == "222"
    assert engine.calls == []


def test_ambiguous_title_returns_candidates(engine):
    out = engine.resolve(["plastics exposure and outcomes in people"])
    assert out[0]["status"] == "needs_identifier"
    assert out[0]["candidates"] and "pmid" in out[0]["candidates"][0]


def test_fetch_returns_documents_originals_and_reasons(engine):
    res = engine.fetch(["111", "222", "333", "444", "999", "plastic"])
    st = {r["ids"]["pmid"]: r for r in res if r.get("ids")}

    wiley = st["222"]
    assert wiley["status"] == "full_text" and wiley["source"] == "wiley"
    assert wiley["licensed"] is True
    assert Path(wiley["original"]["path"]).read_bytes().startswith(b"%PDF")
    assert "## Full text" in wiley["document"] and "## Abstract" in wiley["document"]
    assert "**Full text source:** Wiley" in wiley["document"]

    pmc = st["333"]
    assert pmc["status"] == "full_text" and pmc["source"] == "pmc"
    assert pmc["licensed"] is False and pmc["original"]["kind"] == "xml"
    assert Path(pmc["original"]["path"]).exists()

    assert (
        st["111"]["status"] == "abstract_only"
        and "Elsevier" in st["111"]["explanation"]
    )
    assert st["111"]["next_steps"] and "markdown" not in st["111"]
    assert (
        st["444"]["status"] == "abstract_only"
        and "no self-serve" in st["444"]["explanation"]
    )
    assert [r["status"] for r in res[4:]] == ["not_found", "invalid_identifier"]

    # Only the owning publisher's API was asked; PMC articles skipped the chain.
    orders = {pmid: order for pmid, _, order in engine.calls}
    assert "elsevier" in orders["111"] and "wiley" not in orders["111"]
    assert "wiley" in orders["222"] and "elsevier" not in orders["222"]
    assert "333" not in orders


def test_on_result_is_called_per_article_and_cancel_stops_early(engine):
    seen = []
    engine.fetch(["222", "444"], on_result=lambda i, r: seen.append((i, r["status"])))
    assert sorted(seen) == [(0, "full_text"), (1, "abstract_only")]
    res = engine.fetch(["222", "444"], cancelled=lambda: True)
    assert res == [None, None]


def test_keyed_sources_are_off_without_keys_and_free_ones_on(tmp_path):
    e = Engine({"CONTACT_EMAIL": "lab@fsu.edu"}, tmp_path)
    live = {s["source"]: s for s in e.sources()}
    for keyed in ("elsevier", "springer", "wiley"):
        assert not live[keyed]["available"] and live[keyed]["reason"].startswith(
            "missing"
        )
    for free in (
        "pmc",
        "europepmc",
        "arxiv",
        "unpaywall",
        "openalex",
        "crossref",
        "core",
        "semanticscholar",
    ):
        assert live[free]["available"], free


def test_unpaywall_needs_a_real_contact_address(tmp_path):
    live = {
        s["source"]: s
        for s in Engine({"CONTACT_EMAIL": "you@example.com"}, tmp_path).sources()
    }
    assert not live["unpaywall"]["available"]
    assert live["unpaywall"]["reason"] == "missing CONTACT_EMAIL"
