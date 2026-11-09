"""repair_pubmed_ids: put PubMed papers' own DOI/PMCID back (Q-057). No network."""

from io import StringIO

import pytest
from django.core.management import call_command

from tools.retrieval import pubmed_repair
from tools.retrieval.models import ContentItem
from tools.retrieval.pubmed_repair import parse_own_ids, repair_pubmed_ids


def _article(pmid, own="", refs=()):
    ref_xml = "".join(
        f'<Reference><ArticleIdList><ArticleId IdType="{t}">{v}</ArticleId>'
        "</ArticleIdList></Reference>"
        for t, v in refs
    )
    return f"""
      <PubmedArticle>
        <MedlineCitation><PMID>{pmid}</PMID><Article/></MedlineCitation>
        <PubmedData>
          <ArticleIdList>
            <ArticleId IdType="pubmed">{pmid}</ArticleId>{own}
          </ArticleIdList>
          <ReferenceList>{ref_xml}</ReferenceList>
        </PubmedData>
      </PubmedArticle>"""


ARTICLES = {
    # Stored a cited paper's DOI and PMCID; has its own of both.
    "1": _article("1", '<ArticleId IdType="doi">10.1/Own</ArticleId>'
                       '<ArticleId IdType="pmc">PMC11</ArticleId>',
                  [("doi", "10.9/cited"), ("pmc", "PMC99")]),
    # No own ids at all; stored ones are a reference's -> cleared.
    "2": _article("2", "", [("doi", "10.9/ref2"), ("pmc", "PMC22")]),
    # No own DOI; stored DOI is NOT a reference (came from elsewhere) -> kept.
    "3": _article("3", "", [("doi", "10.9/other")]),
    # Already right.
    "4": _article("4", '<ArticleId IdType="doi">10.4/ok</ArticleId>'),
    # Own DOI is one another (OpenAlex) row already has -> duplicate exposed.
    "5": _article("5", '<ArticleId IdType="doi">10.5/dup</ArticleId>',
                  [("doi", "10.9/c5")]),
    # The PMID an OpenAlex row absorbed: its DOI is one of 6's references.
    "6": _article("6", '<ArticleId IdType="doi">10.6/citing</ArticleId>',
                  [("doi", "10.6/cited")]),
}


def _fake_fetch(calls):
    def fetch(pmids):
        calls.append(list(pmids))
        body = "".join(ARTICLES[p] for p in pmids if p in ARTICLES)
        return f"<PubmedArticleSet>{body}</PubmedArticleSet>"
    return fetch


def _paper(source, ext, **md):
    return ContentItem.objects.create(
        type=ContentItem.Type.PAPER, source=source, external_id=ext, metadata=md
    )


@pytest.fixture
def corpus(db):
    return {
        "p1": _paper("PubMed", "doi:10.9/cited", pmid="1", doi="10.9/cited",
                     pmcid="PMC99"),
        "p2": _paper("PubMed", "doi:10.9/ref2", pmid="2", doi="10.9/ref2",
                     pmcid="PMC22"),
        "p3": _paper("PubMed", "doi:10.9/kept", pmid="3", doi="10.9/kept"),
        "p4": _paper("PubMed", "doi:10.4/ok", pmid="4", doi="10.4/ok"),
        "p5": _paper("PubMed", "doi:10.9/c5", pmid="5", doi="10.9/c5"),
        "oa5": _paper("OpenAlex", "doi:10.5/dup", doi="10.5/dup"),
        "oa6": _paper("OpenAlex", "doi:10.6/cited", doi="10.6/cited", pmid="6"),
        "gone": _paper("PubMed", "pmid:7", pmid="7"),
        # A PubMed row PubMed no longer returns, holding the external_id p5
        # needs: p5's metadata is fixed, its external_id is kept and reported.
        "holder": _paper("PubMed", "doi:10.5/dup", pmid="8"),
    }


def test_parse_own_ids_separates_references():
    ids = parse_own_ids(f"<PubmedArticleSet>{ARTICLES['1']}</PubmedArticleSet>")["1"]
    assert (ids.doi, ids.pmcid) == ("10.1/own", "PMC11")
    assert ids.ref_dois == {"10.9/cited"} and ids.ref_pmcids == {"PMC99"}


def test_dry_run_counts_and_writes_nothing(corpus):
    calls = []
    stats = repair_pubmed_ids(fetch=_fake_fetch(calls), batch=3)
    assert [len(c) for c in calls] == [3, 3, 2]          # 8 PMIDs, batches of 3
    assert stats.checked == 8 and stats.pubmed_rows == 5 and stats.not_in_pubmed == 2
    assert (stats.doi_replaced, stats.doi_cleared, stats.doi_unverified) == (2, 1, 1)
    assert (stats.pmcid_replaced, stats.pmcid_cleared) == (1, 1)
    assert stats.rows_changed == 3 and stats.external_id_changed == 2
    assert stats.external_id_collisions == 1             # p5 vs holder
    assert stats.duplicates_exposed == 1
    assert stats.foreign_pmid_rows == 1
    assert stats.written == 0
    corpus["p1"].refresh_from_db()
    assert corpus["p1"].metadata["doi"] == "10.9/cited"


def test_apply_corrects_rows(corpus):
    stats = repair_pubmed_ids(apply=True, fetch=_fake_fetch([]))
    assert stats.written == 3
    p1, p2, p3, p5, oa6 = (ContentItem.objects.get(pk=corpus[k].pk)
                           for k in ("p1", "p2", "p3", "p5", "oa6"))
    assert (p1.metadata["doi"], p1.metadata["pmcid"], p1.external_id) == (
        "10.1/own", "PMC11", "doi:10.1/own")
    assert (p2.metadata["doi"], p2.metadata["pmcid"], p2.external_id) == (
        None, None, "pmid:2")
    assert p3.metadata["doi"] == "10.9/kept"
    assert (p5.metadata["doi"], p5.external_id) == ("10.5/dup", "doi:10.9/c5")
    assert oa6.metadata["pmid"] == "6"                    # reported, never written
    # Idempotent: a second pass finds nothing left to change.
    again = repair_pubmed_ids(fetch=_fake_fetch([]))
    assert again.rows_changed == 0


def test_command_dry_run(corpus, monkeypatch):
    monkeypatch.setattr(pubmed_repair, "efetch_client", lambda: _fake_fetch([]))
    out = StringIO()
    call_command("repair_pubmed_ids", stdout=out)
    text = out.getvalue()
    assert "DRY RUN" in text and "Would correct 3 of 5 PubMed row(s)" in text
    corpus["p2"].refresh_from_db()
    assert corpus["p2"].metadata["pmcid"] == "PMC22"
