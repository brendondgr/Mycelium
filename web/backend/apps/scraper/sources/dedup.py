"""Cross-source de-duplication.

The strategy is a deterministic identifier cascade backed by a union-find style
crosswalk: every known identifier on a record points at one canonical record.
When a new record shares *any* identifier with an existing one, they collapse,
and we learn the additional identifier links for free.

Fallback for records with no shared identifiers is a normalized
title + first-author + year key.

Ported from ``~/Tools/ResearchScraper/utils/dedup.py``.
"""

from __future__ import annotations

from .record import (
    Record,
    normalize_doi,
    normalize_pmcid,
    normalize_pmid,
    normalize_title,
)


def identifier_keys(
    doi: str | None,
    pmid: str | None,
    pmcid: str | None,
    arxiv: str | None,
) -> list[str]:
    """The normalized strong-identifier keys for a paper.

    Shared by in-memory de-duplication, the against-store check in
    ``ingest.scan``, and the one-shot cleanup command so that all three agree on
    what counts as "the same paper".
    """
    keys: list[str] = []
    if doi:
        keys.append(f"doi:{doi}")
    if pmid:
        keys.append(f"pmid:{pmid}")
    if pmcid:
        keys.append(f"pmcid:{pmcid}")
    if arxiv:
        keys.append(f"arxiv:{arxiv.strip().lower()}")
    return keys


def fuzzy_key(title: str | None, first_author: str | None, year) -> str | None:
    """Normalized title + first-author-surname + year fallback key."""
    norm = normalize_title(title)
    if not norm:
        return None
    author = ""
    if first_author:
        author = normalize_title(first_author).split(" ")[-1]
    return f"fuzzy:{norm}|{author}|{year or ''}"


def _identifier_keys(rec: Record) -> list[str]:
    return identifier_keys(rec.doi, rec.pmid, rec.pmcid, rec.arxiv)


def _fuzzy_key(rec: Record) -> str | None:
    return fuzzy_key(rec.title, rec.first_author, rec.year)


def metadata_identifier_keys(metadata: dict) -> list[str]:
    """Strong-identifier keys for a stored ``ContentItem.metadata`` blob.

    Re-normalizes the way :class:`Record` does so a stored row and a freshly
    scraped record produce matching keys regardless of source formatting.
    """
    return identifier_keys(
        normalize_doi(metadata.get("doi")),
        normalize_pmid(metadata.get("pmid")),
        normalize_pmcid(metadata.get("pmcid")),
        metadata.get("arxiv"),
    )


def metadata_fuzzy_key(metadata: dict) -> str | None:
    """Fuzzy fallback key for a stored ``ContentItem.metadata`` blob."""
    return fuzzy_key(
        metadata.get("title"),
        metadata.get("first_author"),
        metadata.get("year"),
    )


class Deduplicator:
    """Accumulates records and merges duplicates across sources."""

    def __init__(self) -> None:
        # identifier-key -> canonical record
        self._index: dict[str, Record] = {}
        self._canonical: list[Record] = []
        self.duplicates_merged = 0

    def add(self, rec: Record) -> None:
        keys = _identifier_keys(rec)
        fuzzy = _fuzzy_key(rec)
        lookup_keys = keys + ([fuzzy] if fuzzy else [])

        existing = None
        for k in lookup_keys:
            if k in self._index:
                existing = self._index[k]
                break

        if existing is None:
            self._canonical.append(rec)
            target = rec
        else:
            self._merge(existing, rec)
            self.duplicates_merged += 1
            target = existing

        # (Re)point every known key for the merged record at the canonical one.
        for k in _identifier_keys(target):
            self._index[k] = target
        fk = _fuzzy_key(target)
        if fk:
            self._index[fk] = target

    @staticmethod
    def _merge(base: Record, other: Record) -> None:
        base.sources |= other.sources
        # Fill in any identifier/field the base is missing.
        for attr in ("doi", "pmid", "pmcid", "arxiv", "abstract", "venue",
                     "url", "pdf_url", "publication_date", "year"):
            if not getattr(base, attr) and getattr(other, attr):
                setattr(base, attr, getattr(other, attr))
        if len(other.title) > len(base.title):
            base.title = other.title
        if len(other.authors) > len(base.authors):
            base.authors = other.authors

    def results(self) -> list[Record]:
        for i, rec in enumerate(self._canonical):
            rec.canonical_id = (
                f"doi:{rec.doi}" if rec.doi
                else f"pmid:{rec.pmid}" if rec.pmid
                else f"pmcid:{rec.pmcid}" if rec.pmcid
                else f"{rec.source.lower()}:{rec.source_id}" if rec.source_id
                else f"rec:{i}"
            )
        return list(self._canonical)
