"""Combine author drafts from different sources into one aggregated draft.

A user may import from one site *and* upload a résumé; each produces an
:class:`AuthorProfileDraft`. Merging unions their term lists and provenance, then
re-runs :func:`aggregate` so a term appearing in both sources is ranked higher
and duplicates collapse — the same logic that ranks within a single source.
"""

from __future__ import annotations

from .aggregate import aggregate
from .drafts import AuthorProfileDraft

__all__ = ["merge_drafts"]


def merge_drafts(*drafts: AuthorProfileDraft | None) -> AuthorProfileDraft:
    """Return one frequency-ranked draft combining every provided draft.

    Empty/``None`` drafts are ignored. ``display_name`` and ``institution`` take
    the first non-empty value (sites are passed before résumés, so a site's
    canonical name wins); list fields union and re-aggregate.
    """

    present = [draft for draft in drafts if draft is not None]
    if not present:
        return AuthorProfileDraft()
    if len(present) == 1:
        return aggregate(present[0])

    merged = AuthorProfileDraft()
    for draft in present:
        if not merged.display_name and draft.display_name:
            merged.display_name = draft.display_name
        if not merged.institution and draft.institution:
            merged.institution = draft.institution
        merged.areas.extend(draft.areas)
        merged.keywords.extend(draft.keywords)
        merged.methods.extend(draft.methods)
        merged.skills.extend(draft.skills)
        merged.coauthors.extend(draft.coauthors)
        merged.evidence.extend(draft.evidence)
        for key, value in draft.external_ids.items():
            if value and key not in merged.external_ids:
                merged.external_ids[key] = value
    return aggregate(merged)
