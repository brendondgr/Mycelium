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

from .record import Record, normalize_title


def _identifier_keys(rec: Record) -> list[str]:
    keys: list[str] = []
    if rec.doi:
        keys.append(f"doi:{rec.doi}")
    if rec.pmid:
        keys.append(f"pmid:{rec.pmid}")
    if rec.pmcid:
        keys.append(f"pmcid:{rec.pmcid}")
    if rec.arxiv:
        keys.append(f"arxiv:{rec.arxiv.lower()}")
    return keys


def _fuzzy_key(rec: Record) -> str | None:
    title = normalize_title(rec.title)
    if not title:
        return None
    author = ""
    if rec.first_author:
        author = normalize_title(rec.first_author).split(" ")[-1]
    year = rec.year or ""
    return f"fuzzy:{title}|{author}|{year}"


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
