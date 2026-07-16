"""One-shot repair for cross-source duplicate papers.

The live scan path (``apps.scraper.ingest.scan``) now recognizes a paper that
already reached the store from a different source, so new duplicates stop
appearing. This module cleans up the rows that slipped in *before* that fix:
it groups existing ``ContentItem`` papers that share a strong identifier (or,
as a fallback, a normalized title + first author + year), then collapses each
group into a single survivor — repointing every relation so no user's scores,
saves, shares, collections, or suggestions are lost.

Entry point: :func:`dedupe_papers`. The ``dedupe_content_papers`` management
command wraps it with ``--dry-run`` / ``--apply``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from django.db import transaction

from apps.scraper.sources.dedup import (
    metadata_fuzzy_key,
    metadata_identifier_keys,
)

from .models import (
    TARGET_FIELDS,
    CollectionItem,
    ContentItem,
    MemberSuggestion,
    ProjectItemSeen,
    ProjectShare,
    RelevanceEvent,
    RelevanceScore,
    SavedOpportunity,
)

logger = logging.getLogger(__name__)

# Metadata fields worth carrying forward onto the survivor when it is missing
# them. Identifiers first (they drive future dedup), then descriptive fields.
_FILLABLE = (
    "doi", "pmid", "pmcid", "arxiv", "abstract", "venue",
    "pdf_url", "year", "publication_date", "title", "authors", "first_author",
)


@dataclass
class DedupeStats:
    groups: int = 0          # duplicate groups found (size > 1)
    duplicates: int = 0      # rows that would be / were removed
    merged: int = 0          # rows actually merged away (0 on dry-run)

    def as_dict(self) -> dict:
        return {
            "groups": self.groups,
            "duplicates": self.duplicates,
            "merged": self.merged,
        }


def _item_keys(item: ContentItem) -> list[str]:
    """Every key a paper row matches under: canonical id + identifiers + fuzzy."""
    md = item.metadata or {}
    keys = list(metadata_identifier_keys(md))
    if item.external_id:
        keys.append(item.external_id)
    fuzzy = metadata_fuzzy_key(md)
    if fuzzy:
        keys.append(fuzzy)
    return keys


def group_duplicate_papers() -> list[list[ContentItem]]:
    """Return groups of paper rows that denote the same work (size > 1 only).

    Uses union-find over shared keys so a chain of rows linked by different
    identifiers (A shares a DOI with B, B shares an arXiv id with C) collapses
    into one group.
    """
    items = list(ContentItem.objects.filter(type=ContentItem.Type.PAPER))
    parent: dict = {}

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:  # path compression
            parent[x], x = root, parent[x]
        return root

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    key_owner: dict[str, object] = {}
    for item in items:
        parent.setdefault(item.pk, item.pk)
        for key in _item_keys(item):
            if key in key_owner:
                union(item.pk, key_owner[key])
            else:
                key_owner[key] = item.pk

    by_root: dict[object, list[ContentItem]] = {}
    for item in items:
        by_root.setdefault(find(item.pk), []).append(item)

    return [group for group in by_root.values() if len(group) > 1]


def pick_survivor(group: list[ContentItem]) -> ContentItem:
    """Choose the richest row to keep: embedding, then sources, then filled
    identifiers, then the oldest row (stable)."""

    def rank(item: ContentItem):
        md = item.metadata or {}
        created = item.created_at.timestamp() if item.created_at else 0.0
        return (
            item.embedding is not None,
            len(md.get("sources") or []),
            sum(1 for a in ("doi", "pmid", "pmcid", "arxiv", "abstract") if md.get(a)),
            -created,  # older wins ties
        )

    return max(group, key=rank)


@transaction.atomic
def merge_content_items(survivor: ContentItem, loser: ContentItem) -> None:
    """Fold ``loser`` into ``survivor``: repoint every relation, then delete it.

    Each unique-constrained relation is reconciled rather than blindly
    repointed — a colliding row on the survivor is kept (the stronger of the
    two) and the loser's dropped, so no ``IntegrityError`` and no lost signal.
    """
    if survivor.pk == loser.pk:
        return

    # RelevanceScore — unique per (content, target). Keep the higher score.
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

    # SavedOpportunity — unique (user, content).
    for save in SavedOpportunity.objects.filter(content=loser):
        if SavedOpportunity.objects.filter(user=save.user, content=survivor).exists():
            save.delete()
        else:
            save.content = survivor
            save.save(update_fields=["content"])

    # ProjectShare / RelevanceEvent — no per-content uniqueness, repoint in bulk.
    ProjectShare.objects.filter(content=loser).update(content=survivor)
    RelevanceEvent.objects.filter(content=loser).update(content=survivor)

    # ProjectItemSeen — unique (project, content), plus a seen_by M2M to merge.
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

    # CollectionItem — unique (collection, content).
    for citem in CollectionItem.objects.filter(content=loser):
        if CollectionItem.objects.filter(
            collection=citem.collection, content=survivor
        ).exists():
            citem.delete()
        else:
            citem.content = survivor
            citem.save(update_fields=["content"])

    # MemberSuggestion — unique (user, content).
    for sugg in MemberSuggestion.objects.filter(content=loser):
        if MemberSuggestion.objects.filter(user=sugg.user, content=survivor).exists():
            sugg.delete()
        else:
            sugg.content = survivor
            sugg.save(update_fields=["content"])

    # Fold metadata: union sources, back-fill anything the survivor lacks.
    md = dict(survivor.metadata or {})
    lmd = loser.metadata or {}
    have = set(md.get("sources") or [])
    want = set(lmd.get("sources") or []) | {loser.source}
    if not want <= have:
        md["sources"] = sorted(have | want)
    for attr in _FILLABLE:
        if not md.get(attr) and lmd.get(attr):
            md[attr] = lmd[attr]
    survivor.metadata = md

    fields = ["metadata"]
    if survivor.embedding is None and loser.embedding is not None:
        survivor.embedding = loser.embedding
        fields.append("embedding")
    survivor.save(update_fields=fields)

    loser.delete()


def dedupe_papers(
    *, apply: bool = False, log: Callable[[str], None] | None = None
) -> DedupeStats:
    """Find and (optionally) collapse cross-source duplicate paper rows."""

    def emit(message: str) -> None:
        if log is not None:
            log(message)

    stats = DedupeStats()
    groups = group_duplicate_papers()
    for group in groups:
        survivor = pick_survivor(group)
        losers = [item for item in group if item.pk != survivor.pk]
        stats.groups += 1
        stats.duplicates += len(losers)
        title = (survivor.metadata or {}).get("title") or survivor.external_id
        dropped = ", ".join(f"{o.source}:{o.external_id}" for o in losers)
        emit(
            f"group: {len(group)} rows -> keep {survivor.source} "
            f"({survivor.external_id}); drop {dropped} [{title[:80]}]"
        )
        if apply:
            for loser in losers:
                merge_content_items(survivor, loser)
                stats.merged += 1

    emit(
        f"tally: {stats.groups} duplicate groups, {stats.duplicates} redundant rows, "
        f"{stats.merged} merged"
    )
    return stats
