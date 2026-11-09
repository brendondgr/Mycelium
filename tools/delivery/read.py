"""The delivery read door: what other tools and the platform read about what
was shown to people and what they did with it.

The names below are the stable surface. The modules listed in the tool's
``exports`` are still imported directly by the platform (Mylo's Discord
commands, project views, the ambient ledger); new code reads through here.
"""

from tools.delivery.models import (
    Announcement,
    AnnouncementSettings,
    Collection,
    CollectionItem,
    DailyBriefing,
    IgnoredItem,
    MemberSuggestion,
    Notification,
    ProjectAlert,
    ProjectItemSeen,
    ProjectShare,
    ReflectionProposal,
    ReminderSubscription,
    SavedOpportunity,
)


def announcement_post_for_thread(thread_id: str) -> dict | None:
    """The announcement posted in a Discord thread, for the place that asks:
    ``{announcement_id, binding_id, title, closed}``, or ``None``. A thread
    someone deleted by hand is no announcement's any more."""
    from tools.delivery.models import AnnouncementPost

    if not thread_id:
        return None
    post = (
        AnnouncementPost.objects.filter(thread_id=str(thread_id), deleted_at=None)
        .select_related("announcement")
        .order_by("-posted_at")
        .first()
    )
    if post is None:
        return None
    ann = post.announcement
    return {
        "announcement_id": str(ann.pk),
        "binding_id": post.binding_id,
        "title": post.thread_name or (ann.snapshot or {}).get("title", ""),
        "closed": bool(post.closed_at or ann.closed_at),
    }


def closing_soon_for_thread(thread_id: str) -> dict | None:
    """A day's closing-soon thread: ``{binding_id, category, on_date}``."""
    from tools.delivery.models import ClosingSoonPost

    if not thread_id:
        return None
    post = ClosingSoonPost.objects.filter(thread_id=str(thread_id)).first()
    if post is None:
        return None
    return {
        "binding_id": post.binding_id,
        "category": post.category,
        "on_date": post.on_date.isoformat(),
    }


__all__ = [
    "announcement_post_for_thread",
    "closing_soon_for_thread",
    "Announcement",
    "AnnouncementSettings",
    "Collection",
    "CollectionItem",
    "DailyBriefing",
    "IgnoredItem",
    "MemberSuggestion",
    "Notification",
    "ProjectAlert",
    "ProjectItemSeen",
    "ProjectShare",
    "ReflectionProposal",
    "ReminderSubscription",
    "SavedOpportunity",
]
