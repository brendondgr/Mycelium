"""What the buttons on an announcement do (plan D10, D14, "Discord surfaces").

Every press goes through the one authorization gate first
(:func:`apps.integrations.services.gate.authorize`): identity, rate limit, then
membership of *the post's own lab or department* through
``apps.accounts.permissions``. The one exception is **Remind me**: anyone in the
server may set a reminder for themselves without a Mycelium account
(:func:`gate.authorize_guest` — rate limit, the post's binding sits in this
server, the plan covers it). A guest's reminder is a nudge keyed on their Discord
id, by DM or as a thread tag, with a *Stop reminding me* button. The bot calls
these through :mod:`mylo.linking` and relays the returned message.

* **Interested** — a reaction, a personal save (when the target keeps
  ``save_on_interest``), the target's default nudge as a tag in the thread, and a
  DM with the full details.
* **Remind me** — a picker only the presser sees: 2 days to 2 months before (2
  weeks preselected), by DM (an ordinary deadline reminder, listed on the Reminders
  page) or as a tag in the thread. It counts as Interested.
* **Not for us** — managers only; the reason is kept as data.
* **Stop following** — from the DM.
* **Stop reminding me** — from a reminder DM; anyone, for their own reminders.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from apps.content import announce_facts
from apps.content.models import (
    Announcement,
    AnnouncementNudge,
    AnnouncementPost,
    AnnouncementReaction,
    AnnouncementSettings,
    ContentDeadline,
    SavedOpportunity,
)

#: Remind-me choices, in picker order: (value, label, days before).
CHOICES = (
    ("2d", "2 days before", 2),
    ("1w", "1 week before", 7),
    ("2w", "2 weeks before", 14),
    ("3w", "3 weeks before", 21),
    ("1m", "1 month before", 30),
    ("2m", "2 months before", 60),
)
_OFFSET_UNITS = {
    "2d": (2, "day"),
    "1w": (1, "week"),
    "2w": (2, "week"),
    "3w": (3, "week"),
    "1m": (1, "month"),
    "2m": (2, "month"),
}
_AREAS = {
    "grant": SavedOpportunity.Area.GRANT,
    "fellowship": SavedOpportunity.Area.FELLOWSHIP,
    "conference": SavedOpportunity.Area.CONFERENCE,
}


def _gate(discord_user_id: str, post: AnnouncementPost, action: str, guild_id: str):
    from apps.integrations.services import gate

    return gate.authorize(
        discord_user_id=discord_user_id,
        action=action,
        guild_id=guild_id,
        binding_id=post.binding_id,
        subject_id=str(post.announcement_id),
    )


def _remind_gate(discord_user_id: str, post: AnnouncementPost, guild_id: str):
    """``(verdict, guest)``: a member goes through the normal gate; anyone else in
    the server — no Mycelium account, or not a member of this lab — through the
    guest gate, which lets them set reminders for themselves and nothing more."""
    from apps.integrations.services import gate

    verdict = _gate(discord_user_id, post, "ann_follow", guild_id)
    if verdict.ok or verdict.denial not in (
        gate.Denial.NOT_LINKED,
        gate.Denial.FORBIDDEN,
    ):
        return verdict, False
    guest = gate.authorize_guest(
        discord_user_id=discord_user_id,
        action="ann_remind_guest",
        guild_id=guild_id,
        binding_id=post.binding_id,
        subject_id=str(post.announcement_id),
    )
    return guest, True


def _load(post_id) -> AnnouncementPost | None:
    try:
        return (
            AnnouncementPost.objects.select_related(
                "announcement__content", "binding__guild"
            )
            .filter(id=int(post_id))
            .first()
        )
    except (TypeError, ValueError):
        return None


_GONE = ("not_found", {"message": "That announcement is no longer available."})


def _today() -> date:
    return timezone.localdate()


# --------------------------------------------------------------------------- #
# Interested
# --------------------------------------------------------------------------- #
def interested(discord_user_id: str, post_id, guild_id: str = "") -> tuple[str, dict]:
    post = _load(post_id)
    if post is None:
        return _GONE
    verdict = _gate(discord_user_id, post, "ann_follow", guild_id)
    if not verdict.ok:
        from apps.integrations.services import gate

        if verdict.denial in (gate.Denial.NOT_LINKED, gate.Denial.FORBIDDEN):
            return (
                str(verdict.denial),
                {
                    "message": "**Interested** is for members of this lab with a "
                    "Mycelium account. You can still press **🔔 Remind me**: it "
                    "works for anyone here, no account needed."
                },
            )
        return (str(verdict.denial), {"message": verdict.message})
    user, ann = verdict.user, post.announcement
    already = _is_following(ann, user)
    with transaction.atomic():
        if not already:
            AnnouncementReaction.objects.create(
                announcement=ann, user=user, kind=AnnouncementReaction.Kind.INTERESTED
            )
        settings_row = _settings(ann)
        if settings_row and settings_row.save_on_interest and ann.content is not None:
            if not SavedOpportunity.objects.filter(
                user=user, content=ann.content, target_lab__isnull=True
            ).exists():
                from apps.content.views import _save_from_item

                _save_from_item(user, ann.content, note="")
        nudge_offset = settings_row.default_nudge if settings_row else "2w"
        if nudge_offset and nudge_offset != AnnouncementSettings.Nudge.NONE:
            nudge, _ = AnnouncementNudge.objects.update_or_create(
                announcement=ann,
                user=user,
                offset=nudge_offset,
                defaults={
                    "source": AnnouncementNudge.Source.INTERESTED,
                    "active": True,
                },
            )
            _arm(nudge)
    dm_sent = send_details_dm(post, user)
    refresh_count(post)
    if dm_sent:
        note = "👍 Noted. I've sent you the full details by DM."
    else:
        note = (
            "👍 Noted. I couldn't DM you the details: your DMs from this server look "
            "closed, or your Discord isn't linked to Mycelium."
        )
    reminder = _nudge_line(ann, nudge_offset)
    if reminder:
        note += f"\n{reminder}"
    return ("ok", {"message": note})


def _arm(nudge: AnnouncementNudge) -> None:
    from apps.content.discord_announcements import arm_nudge

    arm_nudge(nudge, _today())


def _nudge_line(ann: Announcement, offset: str) -> str:
    due = _due(ann)
    if not due or not offset or offset == "none":
        return ""
    days = dict((v, d) for v, _l, d in CHOICES).get(offset, 14)
    when = due - timedelta(days=days)
    label = dict((v, lbl) for v, lbl, _d in CHOICES).get(offset, "")
    return (
        f"🔔 I'll tag you in the thread {label} (**{when:%a}, {when:%b} {when.day}**)."
    )


def _is_following(ann: Announcement, user) -> bool:
    from apps.content.discord_announcements import followers

    return user in followers(ann)


def _settings(ann: Announcement) -> AnnouncementSettings | None:
    from apps.content.discord_announcements import _settings_for

    return _settings_for(ann)


def _due(ann: Announcement) -> date | None:
    if ann.content is None:
        return None
    iso = announce_facts.facts_for(ann.content, _today())["deadline"]
    return date.fromisoformat(iso) if iso else None


def details_embed(post: AnnouncementPost, user) -> dict:
    """D14: every round, the award, the checks, why it fits them, their reminder."""
    from apps.content.discord_announcements import build_embed, long_date

    ann = post.announcement
    embed = build_embed(ann)
    embed["author"] = {"name": "Mylo · the details you asked for"}
    fields = [f for f in embed.get("fields", []) if f["name"] != "Who should look"]
    rounds = _rounds(ann)
    if rounds:
        fields.insert(
            0,
            {"name": "Every round", "value": "\n".join(rounds)[:1024], "inline": False},
        )
    mine = next(
        (
            p
            for p in (ann.alignment or {}).get("people", [])
            if p.get("user_id") == user.id
        ),
        None,
    )
    if mine and mine.get("why"):
        fields.append(
            {"name": "Why it fits you", "value": mine["why"][:1024], "inline": False}
        )
    reminders = []
    for nudge in AnnouncementNudge.objects.filter(
        announcement=ann, user=user, active=True
    ):
        due = _due(ann)
        days = dict((v, d) for v, _l, d in CHOICES).get(nudge.offset, 14)
        if due:
            when = due - timedelta(days=days)
            reminders.append(f"🔔 Tagged in the thread on **{long_date(when)}**")
    for sub in _reminder_subscriptions(ann, user):
        reminders.append(f"✉️ By DM: {', '.join(_offset_label(o) for o in sub)}")
    fields.append(
        {
            "name": "Your reminder",
            "value": (
                "\n".join(reminders) or "None yet. Use **Change reminder** below."
            )[:1024],
            "inline": False,
        }
    )
    embed["fields"] = fields[:25]
    return embed


def _rounds(ann: Announcement) -> list[str]:
    from apps.content.discord_announcements import long_date

    if ann.content is None:
        return []
    today = _today()
    rows = ContentDeadline.objects.filter(
        content=ann.content, due_date__isnull=False, due_date__gte=today
    ).order_by("due_date")
    return [
        f"**{long_date(r.due_date)}** · {r.round_label or r.get_kind_display()}"
        for r in rows[:10]
    ]


def _reminder_subscriptions(ann: Announcement, user):
    from apps.content.models import ReminderSubscription

    if ann.content is None:
        return []
    subs = ReminderSubscription.objects.filter(
        target_user=user, content=ann.content, state=ReminderSubscription.State.ACTIVE
    ).prefetch_related("offsets")
    return [[(o.amount, o.unit) for o in s.offsets.all()] for s in subs]


def _offset_label(offset: tuple[int, str]) -> str:
    amount, unit = offset
    return f"{amount} {unit}{'s' if amount != 1 else ''} before"


def send_details_dm(post: AnnouncementPost, user) -> bool:
    """Queue the details DM. ``False`` when the person cannot be DMed."""
    from apps.content.discord_announcements import flush, thread_url
    from apps.integrations.services import outbox, resolve

    identity = resolve.active_identity_for_user(user)
    if identity is None or identity.dm_ok is False:
        return False
    components = [
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 1,
                    "label": "Change reminder",
                    "emoji": {"name": "🔔"},
                    "custom_id": f"ann:{post.id}:remind",
                },
                *(
                    [
                        {
                            "type": 2,
                            "style": 5,
                            "label": "Open the thread",
                            "url": thread_url(post),
                        }
                    ]
                    if thread_url(post)
                    else []
                ),
                {
                    "type": 2,
                    "style": 2,
                    "label": "Stop following",
                    "custom_id": f"ann:{post.id}:unfollow",
                },
            ],
        }
    ]
    stamp = timezone.now().strftime("%Y%m%d%H%M%S")
    outbox.enqueue_dm(
        dedupe_key=f"ann-details:{post.announcement_id}:{user.id}:{stamp}",
        kind="announcement_details",
        user=user,
        embed=details_embed(post, user),
        components=components,
        subject_type="announcement",
        subject_id=str(post.announcement_id),
    )
    flush()
    refreshed = resolve.active_identity_for_user(user)
    return refreshed is None or refreshed.dm_ok is not False


def refresh_count(post: AnnouncementPost) -> None:
    """Show the follower count on the Interested button of every thread."""
    from apps.content.discord_announcements import buttons, flush, followers
    from apps.integrations.services import resolve

    ann = post.announcement
    count = len(followers(ann))
    stamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
    for p in ann.posts.exclude(thread_id=""):
        resolve.enqueue_outbox(
            dedupe_key=f"ann-count:{p.id}:{stamp}",
            kind="announcement_count",
            target_type=resolve.OUTBOX_CHANNEL,
            channel_id=p.thread_id,
            mode=resolve.OUTBOX_MODE.THREAD_UPDATE,
            extra={
                "edit": {
                    "message_id": p.thread_id,
                    "components": buttons(
                        p.id, (ann.snapshot or {}).get("url", ""), count
                    ),
                }
            },
        )
    flush()


# --------------------------------------------------------------------------- #
# Remind me
# --------------------------------------------------------------------------- #
def remind_options(
    discord_user_id: str, post_id, guild_id: str = ""
) -> tuple[str, dict]:
    """The picker's choices with their dates; past choices are left out."""
    post = _load(post_id)
    if post is None:
        return _GONE
    verdict, _guest = _remind_gate(discord_user_id, post, guild_id)
    if not verdict.ok:
        return (str(verdict.denial), {"message": verdict.message})
    due = _due(post.announcement)
    if due is None:
        return (
            "no_date",
            {"message": "This call has no dated deadline to remind you about."},
        )
    today = _today()
    options = []
    for value, label, days in CHOICES:
        when = due - timedelta(days=days)
        if when <= today:
            continue
        options.append(
            {
                "value": value,
                "label": f"{label} · {when:%a}, {when:%b} {when.day}",
                "default": value == "2w",
            }
        )
    if not options:
        return (
            "too_late",
            {"message": "Every reminder choice is already past for this call."},
        )
    if not any(o["default"] for o in options):
        options[-1]["default"] = True
    title = (post.announcement.snapshot or {}).get("title") or "this call"
    return (
        "ok",
        {
            "message": f"**Remind you about {title}?** It closes "
            f"{due:%a}, {due:%b} {due.day}, {due.year}.",
            "options": options,
        },
    )


def remind_set(
    discord_user_id: str, post_id, offsets: list[str], where: str, guild_id: str = ""
) -> tuple[str, dict]:
    post = _load(post_id)
    if post is None:
        return _GONE
    verdict, guest = _remind_gate(discord_user_id, post, guild_id)
    if not verdict.ok:
        return (str(verdict.denial), {"message": verdict.message})
    offsets = [o for o in offsets if o in _OFFSET_UNITS][:5]
    if not offsets:
        return ("invalid", {"message": "Pick at least one time."})
    if guest:
        return _guest_remind(str(discord_user_id), post, offsets, where)
    user, ann = verdict.user, post.announcement
    if not _is_following(ann, user):
        AnnouncementReaction.objects.create(
            announcement=ann, user=user, kind=AnnouncementReaction.Kind.INTERESTED
        )
    AnnouncementReaction.objects.create(
        announcement=ann,
        user=user,
        kind=AnnouncementReaction.Kind.REMIND,
        reason=f"{where}:{','.join(offsets)}"[:500],
    )
    labels = ", ".join(dict((v, lbl) for v, lbl, _d in CHOICES)[o] for o in offsets)
    if where == "thread":
        for offset in offsets:
            nudge, _ = AnnouncementNudge.objects.update_or_create(
                announcement=ann,
                user=user,
                offset=offset,
                defaults={"source": AnnouncementNudge.Source.REMIND, "active": True},
            )
            _arm(nudge)
        refresh_count(post)
        return ("ok", {"message": f"🔔 I'll tag you in the thread {labels}."})
    error = _dm_reminder(ann, user, offsets)
    if error:
        return ("refused", {"message": error})
    refresh_count(post)
    return (
        "ok",
        {"message": f"🔔 I'll DM you {labels}. It's on your Reminders page too."},
    )


def _guest_remind(
    discord_user_id: str, post: AnnouncementPost, offsets: list[str], where: str
) -> tuple[str, dict]:
    """A reminder for someone with no Mycelium account (or not in this lab): nudges
    keyed on their Discord id, fired from the call's current deadline each night."""
    ann = post.announcement
    if _due(ann) is None:
        return (
            "no_date",
            {"message": "This call has no dated deadline to remind you about."},
        )
    delivery = (
        AnnouncementNudge.Delivery.THREAD
        if where == "thread"
        else AnnouncementNudge.Delivery.DM
    )
    for offset in offsets:
        nudge, _ = AnnouncementNudge.objects.update_or_create(
            announcement=ann,
            user=None,
            discord_user_id=discord_user_id,
            offset=offset,
            defaults={
                "source": AnnouncementNudge.Source.REMIND,
                "delivery": delivery,
                "active": True,
            },
        )
        _arm(nudge)
    labels = ", ".join(dict((v, lbl) for v, lbl, _d in CHOICES)[o] for o in offsets)
    how = "tag you in the thread" if where == "thread" else "DM you"
    return (
        "ok",
        {
            "message": f"🔔 I'll {how} {labels}. No Mycelium account needed. "
            "Each reminder has a **Stop reminding me** button."
        },
    )


def unremind(discord_user_id: str, post_id, guild_id: str = "") -> tuple[str, dict]:
    """Stop every reminder this person set on this call. Anyone, for their own
    reminders only, from anywhere (the button rides on a DM)."""
    from apps.integrations.services import gate, resolve

    post = _load(post_id)
    if post is None:
        return _GONE
    if not gate._within_rate(str(discord_user_id), "announcements"):
        return ("rate_limited", {"message": gate._RATE_LIMITED})
    ann = post.announcement
    stopped = AnnouncementNudge.objects.filter(
        announcement=ann,
        user__isnull=True,
        discord_user_id=str(discord_user_id),
        active=True,
    ).update(active=False)
    user = resolve.resolve_user(str(discord_user_id))
    if user is not None:
        stopped += AnnouncementNudge.objects.filter(
            announcement=ann,
            user=user,
            source=AnnouncementNudge.Source.REMIND,
            active=True,
        ).update(active=False)
    if not stopped:
        return ("ok", {"message": "You have no reminders left on this call."})
    return ("ok", {"message": "🔕 Done. No more reminders about this call."})


def _dm_reminder(ann: Announcement, user, offsets: list[str]) -> str:
    """An ordinary personal deadline reminder, so it follows a moved date and shows
    on the Reminders page. Returns an error sentence, or ``""``."""
    from apps.content.reminders import ReminderError, create_or_update_subscription

    if ann.content is None:
        return "This call is no longer available."
    row = (
        ContentDeadline.objects.filter(
            content=ann.content, due_date__isnull=False, due_date__gte=_today()
        )
        .exclude(kind=SavedOpportunity.DeadlineKind.EVENT)
        .order_by("due_date")
        .first()
    )
    if row is None:
        return "This call has no dated deadline to remind you about."
    try:
        create_or_update_subscription(
            deadline_kind=row.kind,
            deadline_round_key=row.round_key,
            round_label=row.round_label,
            area=_AREAS.get(ann.category, SavedOpportunity.Area.GRANT),
            title=(ann.snapshot or {}).get("title") or "Opportunity",
            due_date=row.due_date,
            offsets=[_OFFSET_UNITS[o] for o in offsets],
            target_user=user,
            content=ann.content,
            url=(ann.snapshot or {}).get("url", ""),
            confidence=row.confidence,
            created_by=user,
        )
    except ReminderError as exc:
        return (
            f"I couldn't set a DM reminder: {exc}. Pick “Tag me in the thread” instead."
        )
    return ""


# --------------------------------------------------------------------------- #
# Not for us, Stop following
# --------------------------------------------------------------------------- #
def not_for_us(
    discord_user_id: str, post_id, reason: str, guild_id: str = ""
) -> tuple[str, dict]:
    post = _load(post_id)
    if post is None:
        return _GONE
    verdict = _gate(discord_user_id, post, "ann_not_for_us", guild_id)
    if not verdict.ok:
        return (str(verdict.denial), {"message": verdict.message})
    AnnouncementReaction.objects.create(
        announcement=post.announcement,
        user=verdict.user,
        kind=AnnouncementReaction.Kind.NOT_FOR_US,
        reason=" ".join((reason or "").split())[:500],
    )
    return (
        "ok",
        {
            "message": "🚫 Noted as not for us. Thanks, the reason helps Mylo "
            "choose better."
        },
    )


def unfollow(discord_user_id: str, post_id, guild_id: str = "") -> tuple[str, dict]:
    post = _load(post_id)
    if post is None:
        return _GONE
    verdict = _gate(discord_user_id, post, "ann_follow", guild_id)
    if not verdict.ok:
        return (str(verdict.denial), {"message": verdict.message})
    ann = post.announcement
    AnnouncementReaction.objects.create(
        announcement=ann, user=verdict.user, kind=AnnouncementReaction.Kind.UNFOLLOW
    )
    AnnouncementNudge.objects.filter(announcement=ann, user=verdict.user).update(
        active=False
    )
    refresh_count(post)
    return (
        "ok",
        {
            "message": "You've stopped following this call. No more tags or "
            "nudges about it."
        },
    )
