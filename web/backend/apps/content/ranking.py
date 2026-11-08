"""Weighted re-ranking of retrieved papers by the researcher's research focus.

Retrieval (``tools.retrieval.index``) ranks scanned papers purely by cosine
similarity to the profile's *semantic* vector (statement + keywords). That answers
"what is this researcher about?" but treats every nearby paper equally. This
module layers the researcher's declared **research focus** (``interests.areas``)
on top as a cheap, explainable boost: a paper that actually mentions one of the
focus areas in its title/abstract is nudged up the list.

The blend is deliberately simple and transparent::

    blended = similarity + weight * focus_overlap

where ``focus_overlap`` is the fraction of focus areas found in the paper text
(in ``[0, 1]``) and ``weight`` is :data:`DEFAULT_FOCUS_WEIGHT` (overridable via
the ``AREA_FOCUS_WEIGHT`` setting). Keeping it lexical and additive means the
re-rank is fast, deterministic, and easy to explain back to the user ("boosted
because it matches your focus on X") — unlike folding areas into the embedding,
which cannot express a tunable weight.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from tools.retrieval.protocols import Retrievable

#: Default weight applied to the focus overlap. At 0.25 a perfect focus match can
#: lift a paper by up to +0.25 over its raw cosine similarity — enough to reorder
#: near-ties without drowning out the semantic signal.
DEFAULT_FOCUS_WEIGHT = 0.25


@dataclass(frozen=True)
class RankedHit:
    """One retrieved paper after the focus re-rank, with its score breakdown."""

    item: Retrievable
    similarity: float  # raw cosine similarity from retrieval
    focus_overlap: float  # fraction of focus areas present in the paper [0, 1]
    score: float  # blended score the digest ranks by

    @property
    def matched_areas(self) -> list[str]:
        return list(self._matched)

    _matched: tuple[str, ...] = ()


def focus_overlap(areas: Sequence[str], item: Retrievable) -> tuple[float, list[str]]:
    """Return ``(fraction, matched_areas)`` for ``areas`` against ``item`` text.

    ``fraction`` is the share of distinct, non-empty focus areas whose text
    appears (case-insensitively) in the paper's title or abstract.
    """
    terms = _clean_list(areas)
    if not terms:
        return 0.0, []
    meta = item.metadata or {}
    haystack = f"{meta.get('title', '')} {meta.get('abstract', '')}".casefold()
    if not haystack.strip():
        return 0.0, []
    matched = [term for term in terms if term.casefold() in haystack]
    return (len(matched) / len(terms)), matched


def rerank_by_focus(
    hits: Sequence[tuple[Retrievable, float]],
    areas: Sequence[str],
    *,
    weight: float = DEFAULT_FOCUS_WEIGHT,
) -> list[RankedHit]:
    """Blend a focus boost into each hit's similarity and re-sort, best first.

    ``hits`` is retrieval output (``(item, similarity)``, already similarity-
    descending). With no focus areas (or ``weight <= 0``) the order is preserved
    and the boost is zero, so this is a safe no-op overlay.
    """
    ranked: list[RankedHit] = []
    for item, similarity in hits:
        overlap, matched = focus_overlap(areas, item)
        blended = float(similarity) + weight * overlap
        ranked.append(
            RankedHit(
                item=item,
                similarity=float(similarity),
                focus_overlap=overlap,
                score=blended,
                _matched=tuple(matched),
            )
        )
    # Stable sort by blended score; ties keep retrieval's original order.
    ranked.sort(key=lambda hit: hit.score, reverse=True)
    return ranked


def _clean_list(value: Sequence[str] | None) -> list[str]:
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
