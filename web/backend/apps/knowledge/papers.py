"""The demonstrated pipeline, end to end: look up, read, embed, link, roll up.

Two entry points share it. A person's import queues :func:`refresh_person` so
their papers are read the day they arrive; the nightly run calls
:func:`refresh_pending` for whatever is still unread — works imported while the
model was down, a prompt change, an abstract that arrived later — within a
nightly cap, so a backlog is worked through over several nights rather than in
one long bill.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.conf import settings
from django.contrib.auth import get_user_model

from apps.accounts.author_works import MAX_WORKS, enrich_fields
from apps.accounts.models import AuthorWork

from . import demonstrated, works

logger = logging.getLogger(__name__)


@dataclass
class Refreshed:
    looked_up: int = 0
    read: int = 0
    thin: int = 0
    unavailable: int = 0
    vectors: int = 0
    people: int = 0
    edges_created: int = 0
    edges_deleted: int = 0
    failures: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "looked_up": self.looked_up,
            "read": self.read,
            "thin": self.thin,
            "unavailable": self.unavailable,
            "vectors": self.vectors,
            "people": self.people,
            "edges_created": self.edges_created,
            "edges_deleted": self.edges_deleted,
            "failures": len(self.failures),
        }


def _lookup(candidates, limit: int | None, fetch=None) -> int:
    unchecked = [w for w in candidates if w.field_checked_at is None and w.doi]
    if limit is not None:
        unchecked = unchecked[: max(0, limit)]
    return enrich_fields(
        unchecked,
        fetch=fetch,
        mailto=settings.OPENALEX_MAILTO,
        api_key=settings.OPENALEX_API_KEY,
    )


def _refresh(
    candidates, *, limit, lookups, complete, everyone: bool, fetch=None
) -> Refreshed:
    out = Refreshed()
    candidates = list(candidates)
    if lookups:
        out.looked_up = _lookup(candidates, lookups, fetch)
    unread = works.pending(candidates)
    if limit is not None:
        unread = unread[: max(0, limit)]
    outcomes = works.extract_many(unread, complete=complete)
    out.unavailable = len(unread) - len(outcomes)
    by_pk = {work.pk: work for work in unread}
    for pk, outcome in outcomes.items():
        works.store(by_pk[pk], outcome)
        out.read += 1
        out.thin += int(outcome.thin)
    out.vectors = works.fill_vectors(
        works.missing_vectors().filter(author_work__in=[w.pk for w in candidates])
    )

    # Only the people whose papers changed tonight need their edges rebuilt;
    # everyone else's are already what their stored facets say.
    people = (
        {work.user_id for work in candidates}
        if everyone
        else {by_pk[pk].user_id for pk in outcomes}
    )
    User = get_user_model()
    for user in User.objects.filter(pk__in=people).order_by("pk"):
        try:
            result = demonstrated.record_person(user)
        except Exception:  # noqa: BLE001 - one person must not stop the rest
            logger.exception("could not record demonstrated edges for %s", user.pk)
            out.failures.append(f"user:{user.pk}")
            continue
        out.people += 1
        out.edges_created += result.created
        out.edges_deleted += result.deleted
    return out


def refresh_person(user, *, complete=None, fetch=None) -> Refreshed:
    """Everything for one person's works, uncapped: an import is small."""
    return _refresh(
        AuthorWork.objects.filter(user=user).select_related("user__profile"),
        limit=None,
        lookups=MAX_WORKS,
        complete=complete,
        everyone=True,
        fetch=fetch,
    )


def refresh_pending(
    *, limit=None, lookups=None, complete=None, fetch=None
) -> Refreshed:
    """The nightly pass over every person's works, within the nightly caps."""
    limit = settings.KNOWLEDGE_WORK_FACETS_NIGHTLY_CAP if limit is None else limit
    lookups = (
        settings.KNOWLEDGE_FIELD_LOOKUPS_NIGHTLY_CAP if lookups is None else lookups
    )
    candidates = AuthorWork.objects.select_related("user__profile").order_by(
        "user_id", "-year", "pk"
    )
    return _refresh(
        candidates,
        limit=limit,
        lookups=lookups,
        complete=complete,
        everyone=False,
        fetch=fetch,
    )
