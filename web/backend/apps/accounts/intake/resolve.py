"""Identifier -> (source, canonical_id).

v1 resolves **exact identifiers only** (brief decision 5): a bare or URL-form
OpenAlex author id, Semantic Scholar author id, Google Scholar id, or an ORCID.
Name + institution search is a deferred fast-follow because it needs a
"did we find the right person?" confirmation step.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Accepted ``source`` values for :func:`resolve`.
SOURCES = ("openalex", "semantic", "scholar", "orcid")

_ORCID_RE = re.compile(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", re.IGNORECASE)
_OPENALEX_RE = re.compile(r"A\d{6,}", re.IGNORECASE)


class ResolutionError(ValueError):
    """Raised when an identifier cannot be resolved for the given source."""


@dataclass(frozen=True)
class ResolvedAuthor:
    """A canonical (retriever source, id) pair ready to fetch.

    ``source`` is the *retriever* to use — ORCID input resolves to the OpenAlex
    retriever (it can filter works by ``author.orcid``), with ``canonical_id``
    carrying the ``orcid:`` prefix the OpenAlex API understands.
    """

    source: str
    canonical_id: str


def _last_path_segment(identifier: str) -> str:
    return identifier.rstrip("/").rsplit("/", 1)[-1]


def resolve(identifier: str, source: str) -> ResolvedAuthor:
    raw = (identifier or "").strip()
    src = (source or "").strip().lower()
    if not raw:
        raise ResolutionError("identifier is empty")
    if src not in SOURCES:
        raise ResolutionError(
            f"unknown source {source!r}; expected one of: {', '.join(SOURCES)}"
        )

    if src == "orcid":
        match = _ORCID_RE.search(raw)
        if not match:
            raise ResolutionError(f"{raw!r} is not a valid ORCID")
        # OpenAlex is the retriever; it filters works on author.orcid.
        return ResolvedAuthor(source="openalex", canonical_id=f"orcid:{match.group(0)}")

    if src == "openalex":
        token = _last_path_segment(raw)
        if token.lower().startswith("orcid:"):
            return ResolvedAuthor(source="openalex", canonical_id=token)
        match = _OPENALEX_RE.fullmatch(token)
        if not match:
            raise ResolutionError(f"{raw!r} is not a valid OpenAlex author id")
        return ResolvedAuthor(source="openalex", canonical_id=token.upper())

    # semantic / scholar: take the last URL segment as the bare id.
    token = _last_path_segment(raw)
    if not token:
        raise ResolutionError(f"{raw!r} has no usable id segment")
    return ResolvedAuthor(source=src, canonical_id=token)
