"""Keep what the author import read, instead of reducing it to keywords.

The import pulls a person's recent works, mines areas and keywords out of them,
and discards the works. This module is the "and keep them" half (plan M9/2.4).

It exists for one job the reports cannot do without it: knowing which papers the
reader **wrote**. Surfacing someone their own paper as a discovery is the single
most credibility-destroying thing a research feed can do, and it is entirely
avoidable — Mylo already read the list.

Idempotent by construction. Re-importing the same author updates each work in
place on ``(user, source, source_id)``, so a profile refresh does not accumulate
four copies of every paper.
"""

from __future__ import annotations

import hashlib

#: A guard against an adapter that returns a person's entire career. The import
#: itself is already bounded; this is the second line, and it is generous.
MAX_WORKS = 200


def _fallback_id(title: str) -> str:
    """A stable id for a work whose source gave none.

    Hashed from the title because the title is what the matcher compares anyway,
    and because an index-based key would renumber the whole list whenever the
    source returned the works in a different order.
    """
    digest = hashlib.sha256((title or "").strip().casefold().encode("utf-8"))
    return f"title:{digest.hexdigest()[:24]}"


def _year(value) -> int | None:
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    # A four-digit sanity bound: a source that returns 0 or 20260 is wrong, and
    # storing it would put a nonsense date in front of a reader.
    return year if 1500 <= year <= 2200 else None


def store_author_works(user, draft, *, source: str) -> int:
    """Persist one draft's works for ``user``. Returns how many rows were written.

    Never raises. The import's product is the interest draft; the works are a
    bonus, and losing them must not cost someone their profile import.
    """
    from apps.accounts.models import AuthorWork

    if user is None or not getattr(user, "pk", None):
        return 0
    rows = list(getattr(draft, "evidence", None) or [])[:MAX_WORKS]
    written = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = " ".join(str(row.get("title") or "").split())[:500]
        if not title:
            continue
        source_id = str(row.get("source_id") or "").strip()[:200] or _fallback_id(title)
        try:
            AuthorWork.objects.update_or_create(
                user=user,
                source=source[:40],
                source_id=source_id,
                defaults={
                    "title": title,
                    "year": _year(row.get("year")),
                    "doi": str(row.get("doi") or "").strip()[:200],
                    "abstract": str(row.get("abstract") or "")[:20000],
                    "coauthors": [
                        " ".join(str(name).split())
                        for name in (row.get("coauthors") or [])
                        if str(name).strip()
                    ][:50],
                    "cited_by": _year_free_int(row.get("cited_by")),
                },
            )
            written += 1
        except Exception:  # noqa: BLE001 — a bonus must never sink the import
            import logging

            logging.getLogger(__name__).warning(
                "could not store an author work for %s", user, exc_info=True
            )
    return written


def _year_free_int(value) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None
