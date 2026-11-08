"""The normalized :class:`Record` shared by every source.

Each source scraper maps its native payload onto this common shape so that the
orchestrator can deduplicate and ingest a single stream regardless of origin.

Identifier normalization lives here too, because consistent DOI/PMID/PMCID
formatting is the foundation of cross-source de-duplication.

Ported from ``~/Tools/ResearchScraper/utils/record.py`` (the CSV writer is
dropped — ingestion writes ``content.ContentItem`` rows instead).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


def normalize_doi(value: str | None) -> str | None:
    """Lowercase, strip URL prefix and whitespace. DOIs are case-insensitive."""
    if not value:
        return None
    doi = value.strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    doi = doi.removeprefix("doi:").strip()
    return doi or None


def normalize_pmid(value) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    return digits or None


def normalize_pmcid(value: str | None) -> str | None:
    if not value:
        return None
    pmc = str(value).strip().upper()
    pmc = re.sub(r"^https?://.*/", "", pmc)
    if pmc and not pmc.startswith("PMC"):
        pmc = "PMC" + re.sub(r"\D", "", pmc)
    return pmc or None


def normalize_title(title: str | None) -> str:
    """Aggressive normalization used only for fuzzy fallback matching."""
    if not title:
        return ""
    t = title.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def rebuild_inverted_abstract(inv_index: dict | None) -> str | None:
    """Reconstruct an OpenAlex abstract from its inverted index."""
    if not inv_index:
        return None
    positions: list[tuple[int, str]] = []
    for word, locs in inv_index.items():
        for pos in locs:
            positions.append((pos, word))
    if not positions:
        return None
    positions.sort(key=lambda p: p[0])
    return " ".join(word for _, word in positions)


@dataclass
class Record:
    source: str
    source_id: str
    title: str = ""
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    arxiv: str | None = None
    abstract: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    publication_date: str | None = None
    venue: str | None = None
    url: str | None = None
    pdf_url: str | None = None
    # Set of source names that contributed to this (possibly merged) record.
    sources: set[str] = field(default_factory=set)
    canonical_id: str = ""

    def __post_init__(self) -> None:
        self.doi = normalize_doi(self.doi)
        self.pmid = normalize_pmid(self.pmid)
        self.pmcid = normalize_pmcid(self.pmcid)
        if not self.sources:
            self.sources = {self.source}

    @property
    def first_author(self) -> str:
        return self.authors[0] if self.authors else ""

    @property
    def clean_title(self) -> str:
        return re.sub(r"\s+", " ", self.title or "").strip()

    @property
    def clean_abstract(self) -> str:
        return re.sub(r"\s+", " ", self.abstract or "").strip()

    def to_metadata(self) -> dict:
        """The JSON blob stored on ``ContentItem.metadata``."""
        return {
            "title": self.clean_title,
            "abstract": self.clean_abstract,
            "authors": list(self.authors),
            "first_author": self.first_author,
            "year": self.year,
            "publication_date": self.publication_date,
            "venue": (self.venue or "").strip() or None,
            "doi": self.doi,
            "pmid": self.pmid,
            "pmcid": self.pmcid,
            "arxiv": self.arxiv,
            "pdf_url": self.pdf_url,
            "sources": sorted(self.sources),
            "primary_source": self.source,
        }
