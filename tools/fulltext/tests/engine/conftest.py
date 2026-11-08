"""Fixtures: an Engine whose network edges are faked, rooted in a temp directory."""

from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest

from tools.fulltext.engine.pipeline import Engine
from tools.fulltext.engine.resolver import Resolver

BODY = " ".join(["Microplastics were detected in every sample we examined."] * 30)

#: Every credential set, so every source is configured.
FULL_ENV = {
    "CONTACT_EMAIL": "lab@fsu.edu",
    "ELSEVIER_API_KEY": "els-key",
    "SPRINGER_API_KEY": "spr-key",
    "WILEY_TDM_TOKEN": "wil-token",
}

# PMID -> PubMed record
PUBMED = {
    "111": dict(
        pmid="111",
        doi="10.1016/j.envpol.2020.111",
        title="Microplastics in the brain",
        abstract="Abstract one.",
        authors="A B",
        journal="Env Pol",
        pub_date="2020",
        mesh_terms="Brain; Microplastics",
    ),
    "222": dict(
        pmid="222",
        doi="10.1002/tox.222",
        title="Nanoplastics and the heart",
        abstract="Abstract two.",
        authors="C D",
        journal="Tox",
        pub_date="2021",
        mesh_terms="",
    ),
    "333": dict(
        pmid="333",
        doi="10.3390/ijms333",
        title="Plastic particles and stroke risk",
        abstract="Abstract three.",
        authors="E F",
        journal="IJMS",
        pub_date="2022",
        mesh_terms="",
    ),
    "444": dict(
        pmid="444",
        doi="10.1021/acs.est.444",
        title="Aging and polystyrene exposure",
        abstract="Abstract four.",
        authors="G H",
        journal="EST",
        pub_date="2023",
        mesh_terms="",
    ),
}
ARXIV = {
    "hep-th/9901001": dict(
        title="String junctions and their duals",
        journal="arXiv (hep-th)",
        year="1999",
        authors="Y I",
        abstract="Junctions.",
        published_doi="10.1143/ptp.101.1155",
        source="arxiv",
    )
}
DATACITE = {
    "10.5281/zenodo.42": {
        "titles": [{"title": "A dataset paper on Zenodo"}],
        "publisher": "Zenodo",
        "publicationYear": 2023,
        "creators": [{"name": "Doe, Jane", "givenName": "Jane", "familyName": "Doe"}],
    }
}
PMC = {"333": "PMC333"}  # PMID -> PMCID
CROSSREF = {
    "10.9999/not-in-pubmed": {
        "title": ["A paper outside PubMed"],
        "container-title": ["Some Journal"],
        "issued": {"date-parts": [[2024]]},
        "publisher": "X",
    }
}


class FakeResolver(Resolver):
    def pubmed_records(self, pmids):
        return {p: dict(PUBMED[p]) for p in pmids if p in PUBMED}

    def dois_to_pmids(self, dois):
        by_doi = {r["doi"]: p for p, r in PUBMED.items()}
        return {d: by_doi[d] for d in dois if d in by_doi}

    def idconv(self, ids):
        out = {}
        for i in ids:
            pm = next((p for p, c in PMC.items() if c == i), None)
            out[i] = (
                {"pmcid": i, "pmid": int(pm), "doi": PUBMED[pm]["doi"]}
                if pm
                else {"status": "error", "errmsg": "Identifier not found in PMC"}
            )
        return out

    def pmcids_for(self, pmids):
        return {p: PMC[p] for p in pmids if p in PMC}

    def title_search(self, title, n=5):
        words = set(title.lower().split())
        return [
            dict(r) for r in PUBMED.values() if words & set(r["title"].lower().split())
        ][:n]

    def crossref(self, doi):
        return CROSSREF.get(doi, {})

    def arxiv_records(self, ids):
        return {i: dict(ARXIV[i]) for i in ids if i in ARXIV}

    def datacite(self, doi):
        return DATACITE.get(doi, {})

    def doi_registered(self, doi):
        return doi in CROSSREF

    def pii_to_doi(self, pii):
        return "10.1016/j.envpol.2020.111" if pii == "S0269749120000001" else ""

    def pmc_articles(self, pmcids):
        out = {}
        for pmcid in pmcids:
            xml = (
                f"<article><body><sec><title>Results</title><p>{BODY}</p></sec>"
                f"</body></article>"
            )
            path = self.cache.write_text("pmc_xml", pmcid, "xml", xml)
            out[pmcid] = (ET.fromstring(xml), str(path))
        return out


def fake_fetch(calls, pdf):
    """Fetcher.fetch stand-in: Wiley 10.1002 and arXiv succeed, Elsevier is
    refused, the rest have nothing."""

    def fetch(pmid, doi, pmcid, order=None):
        calls.append((pmid, doi, tuple(order or ())))
        tried = {}
        for s in order or ():
            if (s == "wiley" and doi.startswith("10.1002/")) or (
                s == "arxiv" and doi.startswith("10.48550/")
            ):
                tried[s] = "ok"
                return (
                    BODY,
                    s,
                    {
                        "url": f"https://doi.org/{doi}",
                        "kind": "pdf",
                        "original": {"path": str(pdf), "kind": "pdf"},
                    },
                    tried,
                    None,
                )
            if s == "elsevier":
                tried[s] = (
                    "http 403 (key valid but the Article Retrieval API is not "
                    "enabled for it — ask the library to add full-text/TDM access, "
                    "or set ELSEVIER_INST_TOKEN)"
                )
            elif s == "unpaywall":
                tried[s] = "closed"
            else:
                tried[s] = "not-found"
        return "", None, None, tried, None

    return fetch


@pytest.fixture
def engine(tmp_path):
    e = Engine(FULL_ENV, tmp_path / "cache")
    e.resolver = FakeResolver(e.fetcher)
    e.calls = []
    pdf = tmp_path / "cache" / "downloads" / "abc123.bin"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.4 fake")
    e.fetcher.fetch = fake_fetch(e.calls, pdf)
    return e
