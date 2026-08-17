"""Is this opportunity still worth showing anyone? One rule, two callers.

The rule exists because "removed" and "hidden" are different guarantees with
different latencies, and the product needs both:

* :func:`apps.scraper.collect.ingest.prune_expired` **removes** dead rows, but
  it runs once a night.
* the feed reads **hide** them, and they run on every request.

Both must agree, or a conference disappears from the database on a schedule the
feed does not share and the two surfaces contradict each other for up to a day.
So the predicate lives here, in one place, and both import it.

What "still live" means, per type
------------------------------------------------------------------------------
``metadata["prune_after"]`` is the single date every mapper computes for exactly
this question — the **last** date on the record, so a multi-round listing lives
to its final round rather than vanishing at its first (see
``apps.scraper.collect.mapping``). The only thing that varies by type is what an
**empty** ``prune_after`` means, and it means opposite things:

* **Grant / fellowship** — genuinely rolling. ``mapping._grant_deadlines`` writes
  ``""`` precisely to say "no round at all, never expires". Hiding those would
  delete every continuously-open funding call from the product.
* **Conference** — nothing actionable. A venue with no deadline *and* no event
  date is not a call for papers a reader can do anything about; it is a journal
  listing or a stub the collector could not date. On 2026-08-17 that was 156 of
  912 live conferences, none of which ``prune_expired`` could ever remove,
  because an empty ``prune_after`` can never be proven past.

A dateless conference is therefore hidden immediately but deleted only once the
collector has stopped re-seeing it for ``OPPORTUNITY_STALE_DAYS``. That gap is
deliberate: a rolling call the source still lists every night is *wrong* to
delete (it would be re-created on the next run and lose its ``first_seen``),
while one the source dropped months ago is genuinely gone. ``last_seen`` — which
:func:`~apps.scraper.collect.ingest.upsert_items` stamps on every pass that sees
the record — is what separates the two.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from django.conf import settings

from apps.content.models import ContentItem

#: Types this module has an opinion about. A paper is never "expired".
OPPORTUNITY_TYPES = frozenset(
    {
        ContentItem.Type.GRANT,
        ContentItem.Type.CONFERENCE,
        ContentItem.Type.FELLOWSHIP,
    }
)


def stale_days() -> int:
    """How long a dateless conference may go unseen before it is deleted."""
    return int(getattr(settings, "OPPORTUNITY_STALE_DAYS", 60))


def is_live(item_type: str, metadata: dict | None, today: str) -> bool:
    """Should this item still be shown? Pure; no database access.

    ``today`` is an ISO ``YYYY-MM-DD`` string, compared against ``prune_after``
    as a plain string. That is correct **only** because every mapper emits
    zero-padded ``date.isoformat()`` results — the same reason
    ``prune_expired`` has always been able to compare them directly.
    """
    meta = metadata or {}
    prune_after = meta.get("prune_after") or ""
    if item_type == ContentItem.Type.CONFERENCE:
        # No date of any kind → nothing a reader can act on. Hidden, not kept.
        if not prune_after:
            return False
        return prune_after >= today
    # Grants and fellowships: an empty prune_after is a rolling call, kept.
    if not prune_after:
        return True
    return prune_after >= today


def is_expired(item_type: str, metadata: dict | None, today: str) -> bool:
    """The dated half of :func:`is_live` — safe to **delete**, not merely hide.

    Deliberately narrower than ``not is_live(...)``: a dateless conference is
    hidden by ``is_live`` but is only deletable once :func:`is_stale` also
    holds, because the source may still be listing it.
    """
    prune_after = (metadata or {}).get("prune_after") or ""
    return bool(prune_after) and prune_after < today


def is_stale(item_type: str, metadata: dict | None, today: str) -> bool:
    """A dateless conference the collector has not re-seen in a long time.

    Conferences only. A dateless *grant* is a rolling call by design and is
    never stale, however long it sits there.
    """
    if item_type != ContentItem.Type.CONFERENCE:
        return False
    meta = metadata or {}
    if meta.get("prune_after"):
        return False  # dated — that is is_expired's question, not this one
    last_seen = _seen_date(meta)
    if last_seen is None:
        # Never stamped at all: a pre-collector row nothing re-seeing can save.
        return True
    return last_seen < date.fromisoformat(today) - timedelta(days=stale_days())


def _seen_date(meta: dict) -> date | None:
    """``last_seen`` (else ``first_seen``) as a plain date, or None if unusable.

    Both are stored as full ``timezone.now().isoformat()`` timestamps, not plain
    dates, so this takes the leading date component rather than parsing the
    whole instant — the comparison here is in whole days and the time of day the
    collector happened to run is not part of the question.
    """
    for key in ("last_seen", "first_seen"):
        raw = meta.get(key)
        if not raw:
            continue
        try:
            return datetime.fromisoformat(str(raw)).date()
        except ValueError:
            try:
                return date.fromisoformat(str(raw)[:10])
            except ValueError:
                continue
    return None
