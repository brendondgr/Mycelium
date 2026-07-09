"""On-demand, single-area personalization for the post-onboarding match window.

Right after a user finishes onboarding we walk them through a live "matching"
screen that, one area at a time, matches their freshly-saved interests against the
already-scraped corpus and shows how many papers, grants, fellowships, and
conferences fit. Each area is one call to :func:`onboarding_match_area`.

This is a thin wrapper over :func:`apps.content.refitting.refit_user` scoped to a
single area: it reuses the exact daily-pipeline code path (retrieve → fuse → LLM
score over the existing store — **no** literature scan and **no** Pivot re-scrape),
persists the per-user :class:`RelevanceScore` rows the workspace pages then read,
and returns a small JSON-able summary (counts + a short sample) for the UI.

Corpus-only by design: if today's store holds fewer than the surfaced cap for an
area, we surface what exists rather than triggering a live scrape inside the
onboarding request. A synchronous rescan-when-sparse pass is a documented
follow-up, not part of this path.
"""

from __future__ import annotations

from django.contrib.auth.models import User

from .models import ContentItem, RelevanceScore
from .refitting import refit_user
from .suggest import CompleteFn

# The four opportunity/paper areas the onboarding match can run, mapped to the
# ContentItem type whose persisted scores we read back for the sample preview.
AREA_CONTENT_TYPE: dict[str, str] = {
    "papers": ContentItem.Type.PAPER,
    "grants": ContentItem.Type.GRANT,
    "conferences": ContentItem.Type.CONFERENCE,
    "fellowships": ContentItem.Type.FELLOWSHIP,
}

#: How many matched items to preview back to the UI (titles + match percent).
SAMPLE_LIMIT = 6


class UnknownArea(ValueError):
    """Raised when an area outside :data:`AREA_CONTENT_TYPE` is requested."""


def _item_title(row: RelevanceScore) -> str:
    """The best display title for a matched row (headline → metadata → fallback)."""
    headline = row.signals.get("headline")
    if isinstance(headline, str) and headline.strip():
        return headline.strip()
    meta = row.content.metadata or {}
    for key in ("title", "name"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Untitled"


def _sample(user: User, content_type: str) -> list[dict]:
    """Top few just-persisted matches for the area, ranked, for a UI preview."""
    scores = [
        s
        for s in RelevanceScore.objects.filter(
            target_user=user, content__type=content_type
        ).select_related("content")
        if s.signals.get("suggested")
    ]
    if not scores:
        return []
    latest = max(s.signals.get("run_at", "") for s in scores)
    current = [s for s in scores if s.signals.get("run_at", "") == latest]
    current.sort(key=lambda s: s.signals.get("rank") or 999)
    sample: list[dict] = []
    for row in current[:SAMPLE_LIMIT]:
        match = row.signals.get("match_percent")
        sample.append(
            {
                "title": _item_title(row),
                "match_percent": match if isinstance(match, int) else None,
            }
        )
    return sample


def onboarding_match_area(
    user: User,
    area: str,
    *,
    complete: CompleteFn | None = None,
) -> dict:
    """Match one area for ``user`` over the existing corpus and summarize it.

    Reuses :func:`refit_user` for the single ``area`` (persisting the scores), then
    returns ``{area, status, matched, llm, fallback, sample}`` — ``matched`` is the
    number of surfaced items, ``sample`` a short ranked preview for the live table.
    ``complete`` is the injectable LLM seam (``None`` uses the configured model; a
    stub forces the deterministic fallback), used by tests to run offline.

    Raises :class:`UnknownArea` for an unrecognized area.
    """
    if area not in AREA_CONTENT_TYPE:
        raise UnknownArea(area)

    result = refit_user(user, areas=(area,), persist=True, complete=complete)
    summary = result.areas.get(area, {})

    return {
        "area": area,
        "status": result.status,
        "matched": summary.get("suggestions", 0),
        "llm": summary.get("llm", 0),
        "fallback": summary.get("fallback", 0),
        "sample": _sample(user, AREA_CONTENT_TYPE[area]),
    }
