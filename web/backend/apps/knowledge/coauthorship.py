"""Who on Mycelium has published with whom (plan CN-07).

:func:`rebuild` derives the :class:`~apps.knowledge.models.Coauthorship` table
from people's own works; :mod:`apps.knowledge.read` walks it. Two people are
linked when a work of one names the other's OpenAlex id among its co-authors,
or when both hold the same work — either is enough, since a person's own
paper list and their co-authors' lists are imported at different times.

The walk itself is a recursive query in Postgres. Whether that holds up at
scale, or the graph belongs in Neo4j, is EXP-2026-09-011's question; the
decision is in ``docs/research/DECISIONS.md``.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass
class Rebuilt:
    pairs: int = 0
    created: int = 0
    updated: int = 0
    removed: int = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def derive() -> dict[tuple[int, int], tuple[int, int | None]]:
    """``{(a, b): (works, last_year)}`` for every co-authoring pair, ``a < b``."""
    from apps.accounts.models import AuthorWork, Profile

    user_of = {
        oid: uid
        for uid, oid in Profile.objects.exclude(openalex_id="").values_list(
            "user_id", "openalex_id"
        )
    }
    works: dict[tuple[int, int], set[str]] = defaultdict(set)
    years: dict[tuple[int, int], int] = {}
    holders: dict[tuple[str, str], set[int]] = defaultdict(set)
    year_of: dict[tuple[str, str], int | None] = {}

    def link(x: int, y: int, work: tuple[str, str], year: int | None) -> None:
        if x == y:
            return
        pair = (x, y) if x < y else (y, x)
        works[pair].add(f"{work[0]}:{work[1]}")
        if year and year > years.get(pair, 0):
            years[pair] = year

    # Verified works only: a self-service import of someone else's author id
    # must not make its importer anybody's co-author.
    for uid, source, source_id, year, ids in (
        AuthorWork.objects.filter(verified=True)
        .values_list("user_id", "source", "source_id", "year", "coauthor_ids")
        .iterator(chunk_size=2000)
    ):
        work = (source, source_id)
        holders[work].add(uid)
        year_of[work] = year
        for oid in ids or []:
            other = user_of.get(str(oid))
            if other is not None:
                link(uid, other, work, year)
    for work, people in holders.items():
        ordered = sorted(people)
        for i, x in enumerate(ordered):
            for y in ordered[i + 1 :]:
                link(x, y, work, year_of[work])
    return {pair: (len(w), years.get(pair)) for pair, w in works.items()}


def rebuild() -> Rebuilt:
    """Make the table exactly what :func:`derive` says. Safe to run any time."""
    from .models import Coauthorship

    wanted = derive()
    out = Rebuilt(pairs=len(wanted))
    now = timezone.now()
    with transaction.atomic():
        existing = {
            (row.a_id, row.b_id): row
            for row in Coauthorship.objects.select_for_update()
        }
        stale = [row.pk for pair, row in existing.items() if pair not in wanted]
        if stale:
            out.removed = Coauthorship.objects.filter(pk__in=stale).delete()[0]
        new, changed = [], []
        for (a, b), (count, year) in wanted.items():
            row = existing.get((a, b))
            if row is None:
                new.append(Coauthorship(a_id=a, b_id=b, works=count, last_year=year))
            elif (row.works, row.last_year) != (count, year):
                row.works, row.last_year, row.updated_at = count, year, now
                changed.append(row)
        Coauthorship.objects.bulk_create(new, batch_size=2000)
        Coauthorship.objects.bulk_update(
            changed, ["works", "last_year", "updated_at"], batch_size=2000
        )
        out.created, out.updated = len(new), len(changed)
    logger.info("coauthorship rebuilt: %s", out.as_dict())
    return out
