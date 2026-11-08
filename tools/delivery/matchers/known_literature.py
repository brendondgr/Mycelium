"""What the reader already has — and what they wrote themselves.

Two failures this prevents, and both are the kind a reader does not forgive:

**Surfacing someone their own paper as a discovery.** The author import already
read their published works (:class:`~apps.accounts.models.AuthorWork`); presenting
one back as news says plainly that nothing in the system knows who they are.

**Re-announcing something they filed last week.** A paper in the project's
collections, or shared into its feed, is a paper the team has. Calling it new
again is the behaviour that trains people to skim past the "new" badge, after
which the badge is worth nothing on the day it matters.

There is a third, rarer, and more interesting case: a paper the team *does* know,
**revised**. That is news again, and it is the one time re-surfacing something
known is right. Revisions are detected from the précis source fingerprint — the
hash of the item's own text that
:class:`~tools.recommendation.models.ItemComprehension` already keeps to decide when to
re-read a paper. A changed fingerprint on an item the team knows means the paper
moved under them.

Matching is by identifier first (DOI, arXiv id, source id) and by normalised
title second. Titles are compared because the same paper genuinely arrives under
two identifiers — a preprint and its published version — and a reader does not
consider those different papers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_SPACE = re.compile(r"\s+")


def title_key(title: str) -> str:
    """A comparison key for a title: lowercase, punctuation dropped, collapsed.

    Deliberately crude. The failure mode of a *loose* key is calling two distinct
    papers the same, which suppresses one — and the failure mode of a strict key
    is announcing a preprint and its published version as two discoveries. The
    second is the one readers notice.
    """
    text = _PUNCT.sub(" ", (title or "").casefold())
    return _SPACE.sub(" ", text).strip()


@dataclass
class KnownItem:
    """One item the reader already has, and how it is known."""

    content_id: str
    #: ``authored`` / ``collection`` / ``shared`` / ``saved``.
    how: str
    where: str = ""
    #: The stored précis fingerprint at the time it became known, when there is
    #: one. A change is what makes a known paper news again.
    fingerprint: str = ""


@dataclass
class KnownLiterature:
    """Everything one reader-and-project pair already has."""

    by_content: dict[str, KnownItem] = field(default_factory=dict)
    by_title: dict[str, KnownItem] = field(default_factory=dict)

    def lookup(self, content) -> KnownItem | None:
        """Whether this item is already known, by id then by title."""
        found = self.by_content.get(str(getattr(content, "id", "")))
        if found is not None:
            return found
        metadata = getattr(content, "metadata", None) or {}
        key = title_key(metadata.get("title") or metadata.get("name") or "")
        return self.by_title.get(key) if key else None

    def verdict(self, content, precis=None) -> tuple[bool, bool, KnownItem | None]:
        """``(is_known, is_revision, how)`` for one candidate item.

        A revision is a known item whose text has changed since it became known.
        It is the one case where re-surfacing something known is right, so it is
        reported separately rather than folded into "known".
        """
        known = self.lookup(content)
        if known is None:
            return False, False, None
        current = str(getattr(precis, "source_fingerprint", "") or "")
        revised = bool(known.fingerprint and current and current != known.fingerprint)
        return True, revised, known


def _register(store: KnownLiterature, content, how: str, where: str = "") -> None:
    if content is None:
        return
    fingerprint = ""
    precis = getattr(content, "comprehension", None)
    if precis is not None:
        fingerprint = str(getattr(precis, "source_fingerprint", "") or "")
    item = KnownItem(
        content_id=str(content.id), how=how, where=where, fingerprint=fingerprint
    )
    store.by_content.setdefault(item.content_id, item)
    metadata = getattr(content, "metadata", None) or {}
    key = title_key(metadata.get("title") or metadata.get("name") or "")
    if key:
        store.by_title.setdefault(key, item)


def known_literature(project=None, reader=None) -> KnownLiterature:
    """Everything this project and this reader already have.

    Both, because either alone leaves a gap: a paper a reader saved personally is
    theirs whichever project it touches, and a paper the team collected is the
    team's whether or not this particular reader filed it.
    """
    from tools.delivery.models import CollectionItem, ProjectShare, SavedOpportunity

    store = KnownLiterature()

    if project is not None:
        fast = getattr(getattr(project, "state", None), "fast", None) or {}
        wanted = {
            name.casefold()
            for name in (fast.get("known_literature") or {}).get("collections") or []
        }
        rows = CollectionItem.objects.filter(
            collection__project=project
        ).select_related("content", "content__comprehension", "collection")
        for row in rows:
            # A project that named specific collections means those; one that
            # named none means all of them, because a team that curates a list
            # has already said the papers on it are theirs.
            if wanted and row.collection.name.casefold() not in wanted:
                continue
            _register(store, row.content, "collection", row.collection.name)

        for share in ProjectShare.objects.filter(project=project).select_related(
            "content", "content__comprehension"
        ):
            _register(store, share.content, "shared")

    if reader is None or not getattr(reader, "pk", None):
        return store

    from apps.accounts.models import AuthorWork, Lab

    # A lab reads the *lab's* saves. One member's personal bookmark is not the
    # lab's knowledge, and treating it as such would suppress an item for
    # everyone because one person filed it.
    is_lab = isinstance(reader, Lab)
    saves_filter = (
        {"target_lab": reader} if is_lab else {"user": reader, "target_lab": None}
    )
    for save in (
        SavedOpportunity.objects.filter(**saves_filter)
        .exclude(content__isnull=True)
        .select_related("content", "content__comprehension")
    ):
        _register(store, save.content, "saved")

    if is_lab:
        # A lab writes no papers; its members do, and their own reports already
        # know that. Fanning every member's bibliography into the lab's known set
        # would suppress a paper for the whole lab because one person wrote it —
        # which is exactly backwards, since that is the lab's own work.
        return store

    for work in AuthorWork.objects.filter(user=reader):
        key = title_key(work.title)
        if key:
            store.by_title.setdefault(
                key, KnownItem(content_id="", how="authored", where=work.source)
            )
    return store
