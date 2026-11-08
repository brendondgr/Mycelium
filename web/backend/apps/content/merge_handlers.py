"""Repoint this app's rows when retrieval merges two duplicate items.

Subscribed to ``retrieval.items_merging`` (see ``tools/retrieval/events.py``)
from :meth:`apps.content.apps.ContentConfig.ready`. Retrieval publishes the
event and calls nobody; whoever keeps rows pointing at a ``ContentItem``
reconciles its own. Each handler runs inside the merge transaction, and an
exception aborts the merge.

Each unique-constrained relation is reconciled rather than blindly repointed:
a colliding row on the survivor is kept (the stronger of the two) and the
loser's dropped, so no ``IntegrityError`` and no lost signal.
"""

from __future__ import annotations

from tools.retrieval.models import (
    TARGET_FIELDS,
    CollectionItem,
    MemberSuggestion,
    ProjectItemSeen,
    ProjectShare,
    RelevanceEvent,
    RelevanceScore,
    SavedOpportunity,
)


def repoint_scores(*, survivor, loser) -> None:
    """RelevanceScore — unique per (content, target). Keep the higher score."""
    for score in RelevanceScore.objects.filter(content=loser):
        target_field = next(
            f for f in TARGET_FIELDS if getattr(score, f"{f}_id") is not None
        )
        target_id = getattr(score, f"{target_field}_id")
        twin = RelevanceScore.objects.filter(
            content=survivor, **{target_field: target_id}
        ).first()
        if twin is None:
            score.content = survivor
            score.save(update_fields=["content"])
        else:
            if score.score > twin.score:
                twin.score = score.score
                twin.signals = score.signals
                twin.save(update_fields=["score", "signals"])
            score.delete()


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


def repoint_events(*, survivor, loser) -> None:
    """RelevanceEvent — no per-content uniqueness, repoint in bulk."""
    RelevanceEvent.objects.filter(content=loser).update(content=survivor)


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


#: In the order the merge always reconciled them.
HANDLERS = (
    repoint_scores,
    repoint_saves,
    repoint_shares,
    repoint_events,
    repoint_seen,
    repoint_collections,
    repoint_suggestions,
)
