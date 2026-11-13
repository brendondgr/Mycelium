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


def store_author_works(user, draft, *, source: str, verified: bool = False) -> int:
    """Persist one draft's works for ``user``. Returns how many rows were written.

    Never raises. The import's product is the interest draft; the works are a
    bonus, and losing them must not cost someone their profile import.

    ``verified`` says whether the author record is known to be ``user``'s own
    (``AuthorWork.verified``). A self-service import is not — anyone can type
    anyone's ORCID — so it defaults to ``False``; an operator provisioning an
    account from an author record passes ``True``. A re-import never downgrades a
    work that was already verified.
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
            work, _ = AuthorWork.objects.update_or_create(
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
                    "coauthor_ids": [
                        str(value).strip()
                        for value in (row.get("coauthor_ids") or [])
                        if str(value).strip()
                    ][:50],
                    "cited_by": _year_free_int(row.get("cited_by")),
                    **_field(row),
                },
            )
            if verified and not work.verified:
                work.verified = True
                work.save(update_fields=["verified", "updated_at"])
            written += 1
        except Exception:  # noqa: BLE001 — a bonus must never sink the import
            import logging

            logging.getLogger(__name__).warning(
                "could not store an author work for %s", user, exc_info=True
            )
    if written:
        try:
            from apps.knowledge.service import queue_work_facets

            queue_work_facets(user.pk)
        except Exception:  # noqa: BLE001 — the nightly pass reads them anyway
            import logging

            logging.getLogger(__name__).warning(
                "could not queue facets for %s", user, exc_info=True
            )
    return written


def _field(row: dict) -> dict:
    """The work's OpenAlex field, when the source gave one.

    A work from another source is left for :func:`enrich_fields` to look up by
    DOI; one from OpenAlex has been checked already, whatever it said.
    """
    field_id = str(row.get("field_id") or "").strip()[:32]
    if field_id:
        from django.utils import timezone

        return {"openalex_field_id": field_id, "field_checked_at": timezone.now()}
    return {}


def enrich_fields(works, *, fetch=None, mailto: str = "", api_key: str = "") -> int:
    """Look up the OpenAlex field and co-author ids of works that lack them.

    One request per work with a DOI, ever: ``field_checked_at`` is stamped
    whatever the answer, so a DOI OpenAlex does not know is not asked about
    every night. A network failure leaves the work unstamped, to be tried again.
    Returns how many works were checked. Never raises.
    """
    import logging
    import urllib.error
    import urllib.parse

    from django.utils import timezone

    from apps.accounts.intake.normalizers.openalex import _bare_id, primary_field_id
    from apps.accounts.intake.retrievers._http import fetch_json

    fetch = fetch or fetch_json
    checked = 0
    for work in works:
        if work.field_checked_at is not None or not work.doi:
            continue
        params = {"select": "primary_topic,authorships"}
        if mailto:
            params["mailto"] = mailto
        if api_key:
            params["api_key"] = api_key
        url = (
            "https://api.openalex.org/works/doi:"
            + urllib.parse.quote(work.doi, safe="/")
            + "?"
            + urllib.parse.urlencode(params)
        )
        try:
            payload = fetch(url) or {}
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                logging.getLogger(__name__).warning(
                    "OpenAlex lookup failed for %s: %s", work.doi, exc
                )
                continue
            payload = {}
        except Exception as exc:  # noqa: BLE001 - tried again next run
            logging.getLogger(__name__).warning(
                "OpenAlex lookup failed for %s: %s", work.doi, exc
            )
            continue
        own = str(getattr(work.user.profile, "openalex_id", "") or "")
        ids = [
            _bare_id(((row or {}).get("author") or {}).get("id"))
            for row in payload.get("authorships") or []
        ]
        work.coauthor_ids = work.coauthor_ids or [i for i in ids if i and i != own][:50]
        work.openalex_field_id = primary_field_id(payload)
        work.field_checked_at = timezone.now()
        work.save(
            update_fields=[
                "coauthor_ids",
                "openalex_field_id",
                "field_checked_at",
                "updated_at",
            ]
        )
        checked += 1
    return checked


def _year_free_int(value) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None
