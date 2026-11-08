"""Repoint recommendation rows when retrieval merges two duplicate items.

Subscribed to ``retrieval.items_merging`` through ``RecommendationTool.subscribes``
(so only while this tool is loaded). Runs inside the merge transaction; an
exception aborts the merge.
"""

from __future__ import annotations

from tools.recommendation.models import TARGET_FIELDS, RelevanceEvent, RelevanceScore


def repoint_scores(*, survivor, loser) -> None:
    """Scores and engagement events that point at the loser move to the survivor."""
    _repoint_relevance_scores(survivor=survivor, loser=loser)
    _repoint_relevance_events(survivor=survivor, loser=loser)


def _repoint_relevance_scores(*, survivor, loser) -> None:
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


def _repoint_relevance_events(*, survivor, loser) -> None:
    """RelevanceEvent — no per-content uniqueness, repoint in bulk."""
    RelevanceEvent.objects.filter(content=loser).update(content=survivor)


