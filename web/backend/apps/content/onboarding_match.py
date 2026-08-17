"""On-demand, single-area personalization for the post-onboarding match window.

Right after a user finishes onboarding we walk them through a live "matching"
screen that, one area at a time, matches their freshly-saved interests against the
already-scraped corpus and shows how many papers, grants, fellowships, and
conferences fit. Each area is one call to :func:`onboarding_match_area`.

This is a thin wrapper over :func:`apps.content.refitting.refit_user` scoped to a
single area: it reuses the exact daily-pipeline code path (retrieve → fuse → LLM
score over the existing store — **no** literature scan and **no** re-scrape),
persists the per-user :class:`RelevanceScore` rows the workspace pages then read,
and returns a small JSON-able summary (counts + a short sample) for the UI.

Grants, conferences, and fellowships are corpus-only: we surface what the store
already holds rather than scraping inside the request. **Papers are a hybrid** —
they too match the existing (latest-batch) corpus first, but when that batch is too
thin (fewer than ``PAPER_ONBOARDING_MIN_HIGH_QUALITY`` high-quality matches) we kick
off an *asynchronous* background scan of the user's watch topics (a Celery task, not
a live scrape in the request) and report ``scanning`` so the page can say so until
the fresh results land. See :mod:`.scan_status`.
"""

from __future__ import annotations

from collections.abc import Callable

from django.conf import settings
from django.contrib.auth.models import User

from .models import ContentItem, RelevanceScore
from .refitting import refit_user
from .scan_status import trigger_paper_scan
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


def _latest_suggested_rows(user: User, content_type: str) -> list[RelevanceScore]:
    """This area's just-persisted matches from the latest run, ranked."""
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
    return current


def _sample_from(rows: list[RelevanceScore]) -> list[dict]:
    """A short title + match-percent preview for the live onboarding table."""
    sample: list[dict] = []
    for row in rows[:SAMPLE_LIMIT]:
        match = row.signals.get("match_percent")
        sample.append(
            {
                "title": _item_title(row),
                "match_percent": match if isinstance(match, int) else None,
            }
        )
    return sample


def _high_quality_count(rows: list[RelevanceScore], threshold: int) -> int:
    """How many surfaced rows scored at or above ``threshold`` percent match."""
    count = 0
    for row in rows:
        match = row.signals.get("match_percent")
        if isinstance(match, int) and match >= threshold:
            count += 1
    return count


def onboarding_match_area(
    user: User,
    area: str,
    *,
    complete: CompleteFn | None = None,
    enqueue_scan: Callable[[str], None] | None = None,
) -> dict:
    """Match one area for ``user`` over the existing corpus and summarize it.

    Reuses :func:`refit_user` for the single ``area`` (persisting the scores) over
    the latest gather batch — no live scan — then returns
    ``{area, status, matched, llm, fallback, scanning, sample}``. ``matched`` is the
    number of surfaced items, ``sample`` a short ranked preview for the live table.

    **Papers are a hybrid**: if the latest batch yields fewer than
    ``PAPER_ONBOARDING_MIN_HIGH_QUALITY`` suggestions at or above
    ``PAPER_ONBOARDING_HIGH_QUALITY_PERCENT`` match, a background scan of the user's
    watch topics is kicked off and ``scanning`` is ``True`` — the Research Papers
    page then shows a "scanning new articles for you" state until it lands. A rich
    batch shows immediately with ``scanning`` false. The other areas never scan.

    ``complete`` is the injectable LLM seam (``None`` uses the configured model; a
    stub forces the deterministic fallback); ``enqueue_scan`` is the injectable
    background-scan hand-off (tests pass a fake). Both keep the suite offline.

    Raises :class:`UnknownArea` for an unrecognized area.
    """
    if area not in AREA_CONTENT_TYPE:
        raise UnknownArea(area)

    # LLM gate (A3): a Free user still gets this on-demand match (D6), but semantic
    # only — force the deterministic path so they see fallback verdicts, no percent.
    from apps.billing.entitlements import Feature, has_feature

    if not has_feature(user, Feature.LLM_FIT_SCORING):
        complete = lambda _p: None  # noqa: E731 — deliberate force-fallback seam

    result = refit_user(user, areas=(area,), persist=True, complete=complete)
    summary = result.areas.get(area, {})
    rows = _latest_suggested_rows(user, AREA_CONTENT_TYPE[area])

    scanning = False
    if area == "papers":
        threshold = getattr(settings, "PAPER_ONBOARDING_HIGH_QUALITY_PERCENT", 80)
        minimum = getattr(settings, "PAPER_ONBOARDING_MIN_HIGH_QUALITY", 30)
        if _high_quality_count(rows, threshold) < minimum:
            scanning = trigger_paper_scan(user, enqueue=enqueue_scan)

    return {
        "area": area,
        "status": result.status,
        "matched": summary.get("suggestions", 0),
        "llm": summary.get("llm", 0),
        "fallback": summary.get("fallback", 0),
        "scanning": scanning,
        "sample": _sample_from(rows),
    }
