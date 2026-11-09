"""Unit tests for the ported source parsers, dedup, and registry (no network)."""

import pytest

from tools.retrieval.embedding import build_article_text
from tools.retrieval.sources.dedup import Deduplicator
from tools.retrieval.sources.openalex import OpenAlexScraper
from tools.retrieval.sources.pubmed import PubMedScraper
from tools.retrieval.sources.record import Record, rebuild_inverted_abstract
from tools.retrieval.sources.registry import DEFAULT_SOURCES, resolve_sources
from tools.retrieval.sources.semanticscholar import SemanticScholarScraper


def test_record_normalizes_identifiers():
    rec = Record(
        source="OpenAlex",
        source_id="W1",
        title="T",
        doi="https://doi.org/10.1/ABC",
        pmid="PMID: 456",
        pmcid="9999",
    )
    assert rec.doi == "10.1/abc"
    assert rec.pmid == "456"
    assert rec.pmcid == "PMC9999"
    assert rec.sources == {"OpenAlex"}


def test_rebuild_inverted_abstract_orders_words():
    inv = {"Mycelium": [0], "connects": [1], "roots": [2]}
    assert rebuild_inverted_abstract(inv) == "Mycelium connects roots"
    assert rebuild_inverted_abstract(None) is None


def test_dedup_merges_on_shared_doi_and_assigns_canonical_id():
    dd = Deduplicator()
    dd.add(Record("OpenAlex", "W1", title="Paper", doi="10.1/x"))
    dd.add(Record("PubMed", "5", title="Paper", doi="10.1/x", abstract="filled"))
    results = dd.results()
    assert len(results) == 1
    assert dd.duplicates_merged == 1
    assert results[0].abstract == "filled"
    assert results[0].canonical_id == "doi:10.1/x"


def test_dedup_fuzzy_fallback_without_ids():
    dd = Deduplicator()
    author = ["Smith, J"]
    dd.add(Record("OpenAlex", "W1", title="Same Title", authors=author, year=2026))
    dd.add(Record("PubMed", "5", title="Same Title!", authors=["Smith, J"], year=2026))
    assert len(dd.results()) == 1


def test_canonical_id_falls_back_to_source_id():
    dd = Deduplicator()
    dd.add(Record("OpenAlex", "W123", title="No Ids"))
    assert dd.results()[0].canonical_id == "openalex:W123"


def test_resolve_sources_defaults_and_validates():
    assert resolve_sources(None) == list(DEFAULT_SOURCES)
    assert resolve_sources(["openalex", "openalex"]) == ["openalex"]
    with pytest.raises(ValueError):
        resolve_sources(["nope"])


def test_build_article_text_prefers_title_then_abstract():
    assert build_article_text(Record("s", "1", title="T", abstract="A")) == "T\n\nA"
    assert build_article_text(Record("s", "1", title="", abstract="A")) == "A"
    assert build_article_text(Record("s", "1", title="T")) == "T"


def test_openalex_parse():
    work = {
        "id": "https://openalex.org/W1",
        "ids": {"doi": "https://doi.org/10.1/x", "pmid": "123"},
        "title": "Deep Mycology",
        "abstract_inverted_index": {"Hello": [0], "world": [1]},
        "publication_year": 2026,
        "publication_date": "2026-06-01",
        "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
        "primary_location": {"source": {"display_name": "Nature"}, "landing_page_url": "http://x"},
        "best_oa_location": {"pdf_url": "http://x.pdf"},
    }
    rec = OpenAlexScraper._parse(work)
    assert rec.title == "Deep Mycology"
    assert rec.doi == "10.1/x"
    assert rec.abstract == "Hello world"
    assert rec.authors == ["Ada Lovelace"]
    assert rec.venue == "Nature"


def test_semanticscholar_parse():
    paper = {
        "paperId": "abc",
        "title": "Quantum Roots",
        "abstract": "An abstract.",
        "externalIds": {"DOI": "10.2/y", "PubMed": "999", "ArXiv": "2406.1"},
        "publicationDate": "2026-05-15",
        "authors": [{"name": "Grace Hopper"}],
        "venue": "ICML",
        "openAccessPdf": {"url": "http://y.pdf"},
        "url": "http://y",
    }
    rec = SemanticScholarScraper._parse(paper)
    assert rec.doi == "10.2/y"
    assert rec.pmid == "999"
    assert rec.arxiv == "2406.1"
    assert rec.year == 2026
    assert rec.authors == ["Grace Hopper"]


def test_pubmed_parse_xml():
    xml = """
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation>
          <PMID>777</PMID>
          <Article>
            <ArticleTitle>Fungal Computing</ArticleTitle>
            <Abstract>
              <AbstractText Label="Background">Spores compute.</AbstractText>
            </Abstract>
            <AuthorList>
              <Author><LastName>Turing</LastName><ForeName>Alan</ForeName></Author>
            </AuthorList>
            <ArticleDate><Year>2026</Year><Month>6</Month><Day>2</Day></ArticleDate>
            <Journal><Title>Journal of Mycelium</Title></Journal>
          </Article>
        </MedlineCitation>
        <PubmedData>
          <ArticleIdList>
            <ArticleId IdType="doi">10.3/z</ArticleId>
            <ArticleId IdType="pmc">PMC123</ArticleId>
          </ArticleIdList>
        </PubmedData>
      </PubmedArticle>
    </PubmedArticleSet>
    """
    records = PubMedScraper._parse_xml(xml)
    assert len(records) == 1
    rec = records[0]
    assert rec.pmid == "777"
    assert rec.title == "Fungal Computing"
    assert rec.doi == "10.3/z"
    assert rec.pmcid == "PMC123"
    assert "Background: Spores compute." in rec.abstract
    assert rec.publication_date == "2026-06-02"


_REFERENCE_LIST = """
          <ReferenceList>
            <Reference>
              <Citation>A cited paper.</Citation>
              <ArticleIdList>
                <ArticleId IdType="doi">10.1016/j.bandl.2004.10.010</ArticleId>
                <ArticleId IdType="pmc">PMC999</ArticleId>
              </ArticleIdList>
            </Reference>
          </ReferenceList>
"""


def _pubmed_article(own_ids: str, elocation: str = "") -> str:
    return f"""
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation>
          <PMID>42389617</PMID>
          <Article><ArticleTitle>Own paper</ArticleTitle>{elocation}</Article>
        </MedlineCitation>
        <PubmedData>
          <ArticleIdList>
            <ArticleId IdType="pubmed">42389617</ArticleId>
            {own_ids}
          </ArticleIdList>
          {_REFERENCE_LIST}
        </PubmedData>
      </PubmedArticle>
    </PubmedArticleSet>
    """


def test_pubmed_ignores_the_reference_lists_ids():
    """Q-057: a cited paper's DOI/PMCID must never become the article's own."""
    xml = _pubmed_article(
        '<ArticleId IdType="doi">10.63144/ijt.2026.6735</ArticleId>'
        '<ArticleId IdType="pmc">PMC13321850</ArticleId>'
    )
    [rec] = PubMedScraper._parse_xml(xml)
    assert rec.doi == "10.63144/ijt.2026.6735"
    assert rec.pmcid == "PMC13321850"


def test_pubmed_without_own_ids_takes_none_from_references():
    [rec] = PubMedScraper._parse_xml(_pubmed_article(""))
    assert rec.doi is None
    assert rec.pmcid is None


def test_pubmed_falls_back_to_elocation_doi():
    xml = _pubmed_article(
        "", '<ELocationID EIdType="doi" ValidYN="Y">10.5/Own</ELocationID>'
    )
    [rec] = PubMedScraper._parse_xml(xml)
    assert rec.doi == "10.5/own"
    assert rec.pmcid is None
