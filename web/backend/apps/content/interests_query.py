"""Model a researcher's declared focus as explicit, per-interest search queries.

The daily pipeline used to embed the *whole* profile once and search with that
single vector. This module turns the researcher's declared research focus
(``interests.areas``) into a list of distinct **search interests**, each of which
becomes its own retrieval query downstream (a pgvector channel + a BM25 channel,
fused per interest — see :mod:`apps.content.fusion`). A paper that matches several
of these interests can then be preferred over one that only matches a single area.

Design (locked in ``docs/plans/multi-interest-fusion.md``):

- One :class:`SearchInterest` per distinct, non-empty entry in ``interests.areas``.
- ``interests.keywords`` are auxiliary terms attached to *every* interest (they
  sharpen each area's lexical + semantic query) rather than being their own
  interests — that would multiply the query count without adding new axes.

Pure and dependency-free (like :func:`apps.content.pipeline.build_queries`) so it
is trivially unit-testable without the database. With zero areas it returns ``[]``;
callers must treat that as "fall back to the single-vector path," not an error.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class SearchInterest:
    """One search interest derived from a researcher's declared focus.

    ``label`` is the raw area string (kept for the signals/audit trail);
    ``query_text`` is the area plus shared keywords fed to the BM25 lexical
    channel; ``embed_text`` is what gets embedded for the vector channel.
    """

    label: str
    query_text: str
    embed_text: str


def search_interests(interests: dict | None) -> list[SearchInterest]:
    """Turn a profile's interests contract into distinct search interests.

    ``interests`` is the profile's interests dict (``areas``, ``keywords``,
    ``statement`` …). Each distinct, non-empty ``areas`` entry becomes one
    :class:`SearchInterest`, order-preserving and deduped case-insensitively
    (the researcher's stated priority survives). The shared ``keywords`` are
    appended to every interest's ``query_text`` and ``embed_text`` so each area
    query carries the researcher's vocabulary. Returns ``[]`` when there are no
    usable areas — the caller's signal to fall back to the single-vector path.
    """
    interests = interests or {}
    areas = _clean_list(interests.get("areas"))
    if not areas:
        return []
    keyword_suffix = " ".join(_clean_list(interests.get("keywords")))

    out: list[SearchInterest] = []
    for area in areas:
        text = f"{area} {keyword_suffix}".strip() if keyword_suffix else area
        out.append(SearchInterest(label=area, query_text=text, embed_text=text))
    return out


def _clean_list(value: Sequence[str] | None) -> list[str]:
    """Normalize whitespace, drop blanks, and dedupe case-insensitively."""
    if not value:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = " ".join(str(item).split())
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out
