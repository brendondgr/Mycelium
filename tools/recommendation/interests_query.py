"""Model a researcher's declared focus as explicit, per-interest search queries.

The daily pipeline used to embed the *whole* profile once and search with that
single vector. This module turns the researcher's declared research focus
(``interests.areas``) into a list of distinct **search interests**, each of which
becomes its own retrieval query downstream (a pgvector channel + a BM25 channel,
fused per interest — see :mod:`tools.recommendation.fusion`). A paper that matches
several
of these interests can then be preferred over one that only matches a single area.

Design:

- One :class:`SearchInterest` per distinct, non-empty entry in ``interests.areas``.
- Each interest carries a little **context**, drawn from the other areas in its
  own research theme — never from the whole profile.

**Why context is theme-scoped, and capped.** It used to be the profile's entire
``keywords`` list (and, for opportunities, every watch topic too) appended to
every single area. On a real profile that was a 473-character suffix on a
24-character label: all 22 of one reader's searches were ~95% the same string, so
BM25 and the embedder both returned the same documents for "nanotechnology" as
for "agentic querying". One knowledge-graph workshop scored the normalised
maximum, 1.0, on all 22 interests at once — including nanotechnology and quantum
computing — and therefore led *every* theme's slate. Per-theme ranking cannot
help when every theme is asking the same question.

Context still earns its place: a bare two-word area is a thin query, and the
reader's own vocabulary disambiguates it. But it has to be vocabulary that
*differs between themes*, which is exactly what a theme's sibling areas are. The
cap keeps a six-area theme from recreating the same problem at a smaller scale.

Pure and dependency-free (like :func:`tools.recommendation.pipeline.build_queries`) so
it
is trivially unit-testable without the database. With zero areas it returns ``[]``;
callers must treat that as "fall back to the single-vector path," not an error.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SearchInterest:
    """One search interest derived from a researcher's declared focus.

    ``label`` is the raw area string (kept for the signals/audit trail);
    ``query_text`` is the area plus its theme's context, fed to the BM25 lexical
    channel; ``embed_text`` is what gets embedded for the vector channel.
    """

    label: str
    query_text: str
    embed_text: str


#: How many sibling areas of the same theme are appended to an interest's query.
#: Small on purpose — see the module docstring. ``0`` disables context entirely
#: and makes each area its own bare query, which is what the evaluation harness
#: has always measured.
DEFAULT_CONTEXT_TERMS = 3


def context_terms() -> int:
    """The sibling-area cap, overridable by ``settings.INTEREST_CONTEXT_TERMS``."""
    from django.conf import settings

    return max(
        0, int(getattr(settings, "INTEREST_CONTEXT_TERMS", DEFAULT_CONTEXT_TERMS))
    )


def search_interests(
    interests: dict | None,
    *,
    clusters: Sequence[Any] | None = None,
    context_limit: int | None = None,
) -> list[SearchInterest]:
    """Turn a profile's interests contract into distinct search interests.

    ``interests`` is the profile's interests dict (``areas``, ``keywords``,
    ``statement`` …). Each distinct, non-empty ``areas`` entry becomes one
    :class:`SearchInterest`, order-preserving and deduped case-insensitively
    (the researcher's stated priority survives). Returns ``[]`` when there are no
    usable areas — the caller's signal to fall back to the single-vector path.

    ``clusters`` are the profile's themes
    (:func:`tools.recommendation.clustering.cluster_interests`). When given, each area's
    query is padded with up to ``context_limit`` of **its own theme's** other
    areas, so two themes never ask the same question. Without them the areas
    stand alone, which is the honest fallback: profile-wide context is what this
    function exists to stop adding.

    ``keywords`` are deliberately **not** appended any more. They are still the
    reader's vocabulary and still reach the profile vector and the model prompts;
    they are simply not bolted onto all 22 searches at once.
    """
    interests = interests or {}
    areas = _clean_list(interests.get("areas"))
    if not areas:
        return []
    limit = context_terms() if context_limit is None else max(0, context_limit)
    siblings = _siblings_by_area(areas, clusters) if limit else {}

    out: list[SearchInterest] = []
    for area in areas:
        context = " ".join(siblings.get(area.casefold(), [])[:limit])
        text = f"{area} {context}".strip() if context else area
        out.append(SearchInterest(label=area, query_text=text, embed_text=text))
    return out


def _siblings_by_area(
    areas: Sequence[str], clusters: Sequence[Any] | None
) -> dict[str, list[str]]:
    """``{area_casefold: [other areas in its theme]}``, in declaration order.

    An area belongs to exactly one theme (the interests contract validates the
    partition), so its context is unambiguous. An area no theme claims gets no
    context rather than borrowing another theme's — that is the whole point.

    **The implicit cluster contributes nothing.** It is not a theme; it is the
    single fallback grouping an unclustered profile falls into, and it holds
    *every* area. Padding each area with its siblings there would rebuild the
    profile-wide suffix this function exists to remove — the same bug at a
    different address. So an unclustered profile gets bare area queries, which is
    also the configuration the evaluation harness has always measured.
    """
    if not clusters:
        return {}
    declared = {area.casefold(): area for area in areas}
    out: dict[str, list[str]] = {}
    for cluster in clusters:
        if getattr(cluster, "is_implicit", False):
            continue
        members = [
            declared[a.casefold()]
            for a in (getattr(cluster, "areas", None) or [])
            if a.casefold() in declared
        ]
        for area in members:
            out[area.casefold()] = [other for other in members if other != area]
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
