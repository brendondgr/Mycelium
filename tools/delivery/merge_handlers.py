"""Repoint this app's rows when retrieval merges two duplicate items.

Subscribed to ``retrieval.items_merging`` (see ``tools/retrieval/events.py``)
from :meth:`tools.delivery.apps.ContentConfig.ready`. Retrieval publishes the
event and calls nobody; whoever keeps rows pointing at a ``ContentItem``
reconciles its own. Each handler runs inside the merge transaction, and an
exception aborts the merge.

Each unique-constrained relation is reconciled rather than blindly repointed:
a colliding row on the survivor is kept (the stronger of the two) and the
loser's dropped, so no ``IntegrityError`` and no lost signal.
"""

from __future__ import annotations

from tools.delivery.models import (
    CollectionItem,
    MemberSuggestion,
    ProjectItemSeen,
    ProjectShare,
    SavedOpportunity,
)


def repoint_saves(*, survivor, loser) -> None:
    """SavedOpportunity — unique (user, content)."""
    for save in SavedOpportunity.objects.filter(content=loser):
        if SavedOpportunity.objects.filter(user=save.user, content=survivor).exists():
            save.delete()
        else:
            save.content = survivor
            save.save(update_fields=["content"])


def repoint_shares(*, survivor, loser) -> None:
    """ProjectShare — no per-content uniqueness, repoint in bulk."""
    ProjectShare.objects.filter(content=loser).update(content=survivor)


def repoint_seen(*, survivor, loser) -> None:
    """ProjectItemSeen — unique (project, content), plus a seen_by M2M to merge."""
    for seen in ProjectItemSeen.objects.filter(content=loser):
        twin = ProjectItemSeen.objects.filter(
            project=seen.project, content=survivor
        ).first()
        if twin is None:
            seen.content = survivor
            seen.save(update_fields=["content"])
        else:
            twin.seen_by.add(*seen.seen_by.all())
            seen.delete()


def repoint_collections(*, survivor, loser) -> None:
    """CollectionItem — unique (collection, content)."""
    for citem in CollectionItem.objects.filter(content=loser):
        if CollectionItem.objects.filter(
            collection=citem.collection, content=survivor
        ).exists():
            citem.delete()
        else:
            citem.content = survivor
            citem.save(update_fields=["content"])


def repoint_suggestions(*, survivor, loser) -> None:
    """MemberSuggestion — unique (user, content)."""
    for sugg in MemberSuggestion.objects.filter(content=loser):
        if MemberSuggestion.objects.filter(user=sugg.user, content=survivor).exists():
            sugg.delete()
        else:
            sugg.content = survivor
            sugg.save(update_fields=["content"])


#: In the order the merge always reconciled them. (Scores and engagement
#: events are the recommendation tool's: ``tools/recommendation/handlers.py``.)
HANDLERS = (
    repoint_saves,
    repoint_shares,
    repoint_seen,
    repoint_collections,
    repoint_suggestions,
)
