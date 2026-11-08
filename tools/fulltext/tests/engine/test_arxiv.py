"""arXiv: id spellings, metadata (arXiv API / DataCite), routing, the PDF."""

import pytest

from tools.fulltext.engine.fetcher import Fetcher
from tools.fulltext.engine.identifiers import parse_item
from tools.fulltext.engine.resolver import parse_arxiv_feed
from tools.fulltext.engine.routing import explain, plan

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/hep-th/9901001v3</id>
    <title>String Junctions and
      Their Duals</title>
    <summary>  We explicitly give the correspondence.</summary>
    <published>1999-01-04T00:00:00Z</published>
    <author><name>Yosuke Imamura</name></author>
    <arxiv:doi>10.1143/PTP.101.1155</arxiv:doi>
    <arxiv:journal_ref>Prog.Theor.Phys.101:1155,1999</arxiv:journal_ref>
    <arxiv:primary_category term="hep-th"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2101.00001v1</id>
    <title>Etat de l'art</title>
    <published>2021-01-04T00:00:00Z</published>
    <author><name>A</name></author><author><name>B</name></author>
  </entry>
</feed>"""


def test_old_style_ids_drop_the_subject_class_and_versions_are_noted():
    item = parse_item("math.GT/0309136")
    assert item.doi == "10.48550/arxiv.math/0309136"
    assert any("subject class dropped" in n for n in item.notes)
    item = parse_item("arXiv:2101.00001v2")
    assert item.doi == "10.48550/arxiv.2101.00001"
    assert any("v2 requested" in n for n in item.notes)


@pytest.mark.parametrize(
    "raw", ["arxiv:2113.00001", "arXiv:hep-th/991301", "https://arxiv.org/abs/nonsense"]
)
def test_malformed_arxiv_ids_are_rejected(raw):
    assert "arXiv id" in parse_item(raw).error


def test_feed_parsing_maps_entries_back_to_requested_ids():
    out = parse_arxiv_feed(FEED, ["hep-th/9901001", "2101.00001", "2101.99999"])
    assert set(out) == {"hep-th/9901001", "2101.00001"}
    hep = out["hep-th/9901001"]
    assert hep["title"] == "String Junctions and Their Duals" and hep["year"] == "1999"
    assert hep["published_doi"] == "10.1143/ptp.101.1155"
    assert hep["journal"] == "arXiv (hep-th)"
    assert out["2101.00001"]["authors"] == "A; B"


def test_feed_error_entry_fails_the_batch():
    err = FEED.replace("String Junctions and\n      Their Duals", "Error")
    assert parse_arxiv_feed(err, ["hep-th/9901001"]) is None


def test_resolve_gives_arxiv_titles_and_datacite_fallback(engine):
    out = engine.resolve(["hep-th/9901001", "arXiv:2101.99999", "10.5281/zenodo.42"])
    assert [r["status"] for r in out] == ["resolved", "not_found", "resolved"]
    assert out[0]["metadata"]["title"] == "String junctions and their duals"
    assert out[0]["will_try"][0] == "arxiv"
    assert out[0]["ids"]["arxiv"] == "hep-th/9901001"
    assert any("10.1143/ptp.101.1155" in n for n in out[0]["notes"])
    assert "arXiv has no paper" in out[1]["explanation"]
    assert out[2]["metadata"] == {
        "title": "A dataset paper on Zenodo",
        "journal": "Zenodo",
        "year": "2023",
        "authors": "Jane Doe",
    }
    assert "arxiv" not in out[2]["will_try"]


def test_arxiv_paper_is_fetched_and_open(engine):
    res = engine.fetch(["hep-th/9901001"])
    assert res[0]["status"] == "full_text" and res[0]["source"] == "arxiv"
    assert res[0]["licensed"] is False
    assert res[0]["document"].startswith("# String junctions and their duals")


def test_arxiv_is_only_routed_arxiv_dois():
    order = ["pmc", "europepmc", "elsevier", "arxiv", "unpaywall"]
    arx = {
        s["source"]: s for s in plan({}, None, "10.48550/arxiv.2101.00001", None, order)
    }
    assert arx["arxiv"]["action"] == "try" and arx["elsevier"]["action"] == "skip"
    els = {s["source"]: s for s in plan({}, "1", "10.1016/x", None, order)}
    assert els["arxiv"]["action"] == "skip" and "Elsevier" in els["arxiv"]["reason"]
    why, retry, _ = explain(
        "arXiv (preprint)", "arxiv", list(arx.values()), {"arxiv": "http 404"}
    )
    assert "arXiv preprint" in why and "HTTP 404" in why and not retry


def test_arxiv_source_downloads_the_pdf_from_export(tmp_path, monkeypatch):
    f = Fetcher({}, tmp_path)
    asked = []
    monkeypatch.setattr(
        f,
        "download",
        lambda src, url, tried: asked.append(url) or ("text", "pdf", "ok"),
    )
    md, prov, note = f.src_arxiv(None, "10.48550/arxiv.hep-th/9901001", None, set())
    assert (md, note) == ("text", "ok")
    assert asked == ["https://export.arxiv.org/pdf/hep-th/9901001"]
    assert prov["url"] == "https://arxiv.org/abs/hep-th/9901001"
    assert f.src_arxiv("1", "10.1016/x", None, set()) == ("", None, "not-arxiv")
