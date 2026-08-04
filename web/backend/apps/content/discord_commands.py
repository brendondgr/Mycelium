"""What Mylo's slash commands actually do, once the gate has said yes.

Each function here runs synchronously inside ``mycelium.db``, takes only a Discord
snowflake and the command's arguments, and returns a plain ``(status, payload)``
dict — no Discord objects, no embed building. Rendering lives in the cog, so this
module is testable without a gateway and the same result could feed any surface.

Every function starts with :func:`apps.integrations.services.gate.authorize`. That is
the only place authority is decided; a snowflake and a slug arrive here equally
untrusted, and the gate resolves one into a user and refuses to let the other grant
anything.
"""

from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.content.models import (
    DailyBriefing,
    ReminderSubscription,
    SavedOpportunity,
)
from apps.integrations.services import gate

#: How many rows a Discord embed can carry before it stops being scannable. Well
#: under Discord's own limits — the constraint here is the reader, not the API.
SEARCH_RESULTS = 5
SAVES_PAGE = 5

_MATCH_LABEL = {
    "lexical": "title text",
    "semantic": "meaning",
    "fuzzy": "close spelling",
}


def _denied(verdict) -> tuple[str, dict]:
    return str(verdict.denial), {"message": verdict.message}


# --------------------------------------------------------------------------- #
# /mylo search
# --------------------------------------------------------------------------- #
def search(discord_user_id: str, query: str) -> tuple[str, dict]:
    """The portal's own search, run for the person who asked.

    Reuses ``search_service.search_for_user`` rather than calling ``run_search``
    directly, so Mylo and the website cannot disagree about the same query. Note
    there is no match percentage: search scores by rank fusion and never computes
    one, and inventing a number here would be a figure with nothing behind it.
    """
    verdict = gate.authorize(discord_user_id=discord_user_id, action="search")
    if not verdict.ok:
        return _denied(verdict)

    query = (query or "").strip()
    if not query:
        return "empty_query", {
            "message": "Tell me what to look for — `/mylo search query:<words>`."
        }

    from apps.content.search_service import search_for_user

    context = search_for_user(verdict.user, query, limit=SEARCH_RESULTS)
    items = context.items[:SEARCH_RESULTS]
    if not items:
        return "no_results", {
            "query": query,
            "message": f"Nothing in the corpus matches **{query}** yet.",
        }

    return "ok", {
        "query": query,
        "count": context.result.count,
        "confidence": context.result.confidence,
        "results": [_search_row(item, context) for item in items],
    }


def _search_row(item, context) -> dict:
    meta = item.metadata or {}
    cluster = getattr(item, "_cluster", None)
    matched = getattr(item, "_search_matched_on", []) or []
    return {
        "title": meta.get("title") or meta.get("name") or "Untitled",
        "url": meta.get("pdf_url") or item.source_url or "",
        "type": item.type,
        "cluster": (cluster or {}).get("label", ""),
        # Why it surfaced, in words. The honest substitute for a match percentage:
        # it says what actually happened rather than implying a score that isn't there.
        "matched_on": [_MATCH_LABEL.get(c, c) for c in matched],
        "saved": item.id in context.saved_ids,
    }


# --------------------------------------------------------------------------- #
# /mylo digest
# --------------------------------------------------------------------------- #
def digest(discord_user_id: str, lab_slug: str = "") -> tuple[str, dict]:
    """Today's compiled report, pulled rather than pushed.

    Three honest outcomes and no fabricated fourth: today's report, an older one
    named as older, or a plain statement that none exists. A Free account is never
    run through the daily pipeline, so it genuinely has nothing to show — saying so
    and naming what Spore adds is more useful than assembling something
    report-shaped out of whatever happens to be stored.
    """
    action = "lab_digest" if lab_slug else "digest"
    verdict = gate.authorize(
        discord_user_id=discord_user_id, action=action, lab_slug=lab_slug
    )
    if not verdict.ok:
        return _denied(verdict)

    if lab_slug:
        briefing = DailyBriefing.latest_for(lab=verdict.lab)
        owner = verdict.lab.name
    else:
        briefing = DailyBriefing.latest_for(user=verdict.user)
        owner = ""

    if briefing is None:
        return "none", {
            "owner": owner,
            "message": _no_digest_message(verdict.user, lab_slug),
        }

    return "ok", {
        "owner": owner,
        "generated_on": briefing.generated_on.isoformat(),
        "stale": briefing.generated_on < timezone.localdate(),
        "counts": briefing.counts or {},
        "new_counts": briefing.new_counts or {},
        "body": briefing.body or "",
    }


def _no_digest_message(user, lab_slug: str) -> str:
    if lab_slug:
        return (
            "Mylo hasn't written this lab a report yet. One is compiled each day "
            "once the lab's research focus is set."
        )
    from apps.billing.entitlements import Feature, has_feature

    if has_feature(user, Feature.SCHEDULED_REPORTS):
        return "Mylo hasn't written today's report yet — it's compiled each morning."
    # Free is an on-demand product: the daily run genuinely never covers it, so
    # promising "not yet" would be misleading rather than reassuring.
    return (
        "Mylo hasn't written you a report. Daily research reports are part of "
        "**Spore** — your searches and saved items keep working either way."
    )


# --------------------------------------------------------------------------- #
# /mylo saves
# --------------------------------------------------------------------------- #
def saves(discord_user_id: str, page: int = 0) -> tuple[str, dict]:
    """The caller's most recent bookmarks, newest first. Read-only."""
    verdict = gate.authorize(discord_user_id=discord_user_id, action="saves")
    if not verdict.ok:
        return _denied(verdict)

    page = max(0, int(page or 0))
    start = page * SAVES_PAGE
    rows = SavedOpportunity.objects.filter(
        user=verdict.user, target_lab__isnull=True
    ).order_by("-created_at")
    total = rows.count()
    # The snapshot columns, not the feed card: the card round-trips four serializers
    # and a batch of relevance scores to render things a Discord list cannot show.
    window = list(rows[start : start + SAVES_PAGE])

    if not window:
        message = (
            "You haven't saved anything yet — the bookmark on any card in Mycelium."
            if total == 0
            else "That's past the end of your saved list."
        )
        return "empty", {"message": message, "total": total}

    today = timezone.localdate()
    return "ok", {
        "total": total,
        "page": page,
        "has_more": start + len(window) < total,
        "items": [_save_row(row, today) for row in window],
    }


def _save_row(row, today: date) -> dict:
    days = (row.deadline_date - today).days if row.deadline_date else None
    return {
        "title": row.title,
        "area": row.area,
        "subtitle": row.subtitle or "",
        "url": row.url or "",
        "deadline": row.deadline_date.isoformat() if row.deadline_date else "",
        "days_remaining": days,
    }


# --------------------------------------------------------------------------- #
# /mylo snooze and /mylo cancel
# --------------------------------------------------------------------------- #
_UNITS = {"day": "days", "week": "weeks", "month": "months"}


def snooze(
    discord_user_id: str,
    *,
    reminder_id: str,
    amount: int = 1,
    unit: str = "week",
    today: date | None = None,
) -> tuple[str, dict]:
    """Push a reminder back, counting from the moment the person asked.

    The date is computed from *now*, not from the deadline: "snooze this for a week"
    means a week from when I said it. Clamped to the deadline itself, since a reminder
    that fires after its own deadline is worse than none.
    """
    verdict = gate.authorize(discord_user_id=discord_user_id, action="snooze")
    if not verdict.ok:
        return _denied(verdict)

    sub, error = _owned_reminder(verdict.user, reminder_id)
    if sub is None:
        return error

    if unit not in _UNITS:
        return "bad_unit", {"message": "Choose day, week or month."}
    amount = max(1, int(amount or 1))

    today = today or timezone.localdate()
    until = today + relativedelta(**{_UNITS[unit]: amount})
    clamped = False
    if sub.due_date and until >= sub.due_date:
        # Snoozing past the deadline would silently cancel it. Stop at the deadline
        # and say so, rather than doing something the person did not intend.
        until = sub.due_date
        clamped = True

    sub.snoozed_until = until
    sub.save(update_fields=["snoozed_until", "updated_at"])
    return "ok", {
        "title": sub.title,
        "snoozed_until": until.isoformat(),
        "clamped": clamped,
        "due_date": sub.due_date.isoformat() if sub.due_date else "",
    }


def cancel(discord_user_id: str, *, reminder_id: str) -> tuple[str, dict]:
    """Stop a reminder without destroying the record that it existed.

    A soft cancel, matching the web app: the row stays, so "why did this stop?" has
    an answer, and the tick simply no longer sees it.
    """
    verdict = gate.authorize(discord_user_id=discord_user_id, action="cancel")
    if not verdict.ok:
        return _denied(verdict)

    sub, error = _owned_reminder(verdict.user, reminder_id)
    if sub is None:
        return error

    already = sub.state == ReminderSubscription.State.CANCELLED
    if not already:
        sub.state = ReminderSubscription.State.CANCELLED
        sub.save(update_fields=["state", "updated_at"])
    return "ok", {"title": sub.title, "already": already}


def list_manageable(discord_user_id: str, prefix: str = "") -> tuple[str, dict]:
    """Reminders the caller may act on — the autocomplete behind snooze and cancel.

    Runs the same ownership rule as the commands themselves. Offering a reminder in a
    dropdown that would then be refused is its own kind of leak: it tells the caller
    the thing exists.
    """
    verdict = gate.authorize(discord_user_id=discord_user_id, action="snooze")
    if not verdict.ok:
        return _denied(verdict)

    rows = _manageable_queryset(verdict.user).filter(
        state=ReminderSubscription.State.ACTIVE
    )
    if prefix:
        rows = rows.filter(title__icontains=prefix)
    return "ok", {
        "items": [
            {"id": str(r.id), "title": r.title, "due_date": (
                r.due_date.isoformat() if r.due_date else ""
            )}
            for r in rows.order_by("due_date")[:25]  # Discord's autocomplete ceiling
        ]
    }


def _manageable_queryset(user):
    """Personal reminders, plus lab reminders the user may manage.

    Deliberately the *manage* right, not mere membership: a lab reminder speaks to
    the whole lab, so silencing one is a management act, exactly as creating one is.
    """
    from apps.accounts.models import LabMembership

    managed_lab_ids = LabMembership.objects.filter(
        user=user,
        role__in=[LabMembership.Role.OWNER, LabMembership.Role.ADMIN],
    ).values_list("lab_id", flat=True)
    return ReminderSubscription.objects.filter(
        target_user=user
    ) | ReminderSubscription.objects.filter(target_lab_id__in=list(managed_lab_ids))


def _owned_reminder(user, reminder_id: str):
    """Load a reminder the caller may act on, or the refusal to send back.

    A reminder that does not exist and one belonging to someone else give the same
    answer, for the same reason the gate does it for labs.
    """
    not_found = (
        "not_found",
        {"message": "I couldn't find that reminder, or it isn't yours to change."},
    )
    if not reminder_id:
        return None, not_found
    try:
        sub = _manageable_queryset(user).filter(pk=reminder_id).first()
    except (ValueError, TypeError, ValidationError):
        # A malformed id is a typo in a command argument, not a server fault — it
        # should read as "no such reminder", not surface in the error funnel.
        return None, not_found
    if sub is None:
        return None, not_found
    return sub, None
