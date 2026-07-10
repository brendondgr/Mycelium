"""Project collaboration services (briefing Features A / B / D).

The write-side helpers behind the Projects collaboration surface: the seen ledger
(dedup + "already seen by your team"), the weighted engagement log, and the
share-to-project action that ties them together. Kept out of the views so the same
paths are reachable from the backfill command, the (deferred) fan-out task, and the
future team-signal recompute.

Nothing here mutates an individual :class:`~apps.accounts.models.Profile` — the team
signal updates the project, never the member (project principle).
"""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.db.models import Count

from apps.research.models import Project

from .models import ContentItem, ProjectItemSeen, ProjectShare, RelevanceEvent


def event_weight(action: str) -> float:
    """The configured weight for an engagement action (0 for unknown actions)."""
    return float(settings.RELEVANCE_EVENT_WEIGHTS.get(action, 0.0))


def mark_seen(
    project: Project,
    content: ContentItem,
    via: str,
    *,
    user=None,
) -> ProjectItemSeen:
    """Record that ``content`` has surfaced in ``project``; idempotent.

    Writes one :class:`ProjectItemSeen` per ``(project, content)`` — the first path
    wins for ``first_seen_via`` and never changes on later calls. When ``user`` is
    given (an actual in-app view, not a delivery), they are added to ``seen_by``.
    """
    seen, _created = ProjectItemSeen.objects.get_or_create(
        project=project,
        content=content,
        defaults={"first_seen_via": via},
    )
    if user is not None and user.is_authenticated:
        seen.seen_by.add(user)
    return seen


def project_seen_map(project: Project, content_ids) -> dict[str, dict]:
    """One-query seen metadata for a set of items, keyed by content id (str).

    ``{content_id: {"first_seen_at", "first_seen_via", "seen_by_count"}}`` — used to
    badge the feed without an N+1. Items with no ledger row are simply absent.
    """
    ids = list(content_ids)
    if not ids:
        return {}
    rows = (
        ProjectItemSeen.objects.filter(project=project, content_id__in=ids)
        .annotate(seen_by_count=Count("seen_by"))
        .values("content_id", "first_seen_at", "first_seen_via", "seen_by_count")
    )
    return {
        str(row["content_id"]): {
            "first_seen_at": row["first_seen_at"],
            "first_seen_via": row["first_seen_via"],
            "seen_by_count": row["seen_by_count"],
        }
        for row in rows
    }


def record_event(
    user,
    content: ContentItem,
    action: str,
    *,
    project: Project | None = None,
) -> RelevanceEvent:
    """Append a weighted engagement event (a weak relevance label for Feature D)."""
    return RelevanceEvent.objects.create(
        user=user,
        project=project,
        content=content,
        action=action,
        weight=event_weight(action),
    )


@transaction.atomic
def share_to_project(
    project: Project,
    content: ContentItem,
    user,
    *,
    note: str = "",
    source: str = ProjectShare.Source.DIGEST,
) -> ProjectShare:
    """Share an item into a project: the share row, the seen ledger, and the event.

    Re-sharing is allowed (no ``(project, content)`` uniqueness) — the feed collapses
    by content. Emits a ``share`` :class:`RelevanceEvent` and marks the item seen via
    ``share``.
    """
    share = ProjectShare.objects.create(
        project=project,
        content=content,
        shared_by=user,
        note=note or "",
        source=source,
    )
    # A pasted link is the item's own entry path; a re-share of an existing item is
    # not. first_seen_via only sticks the first time (mark_seen is first-wins).
    via = (
        ProjectItemSeen.Via.EXTERNAL_LINK
        if source == ProjectShare.Source.EXTERNAL_LINK
        else ProjectItemSeen.Via.SHARE
    )
    mark_seen(project, content, via)
    record_event(user, content, RelevanceEvent.Action.SHARE, project=project)
    # Fan-out seam (Feature F, deferred): when cross-member relevance ships, enqueue
    # fanout_relevance(share.id) here — score the item's embedding against each other
    # member's interest text, notify above-floor members, persist abstentions.
    return share
