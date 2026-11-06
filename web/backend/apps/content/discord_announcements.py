"""Opportunity announcements in Discord: step 5 of the nightly path, and the update
stage after it (plan D1, D9, D10, D11).

Every surface is a forum thread. An announcement is posted once per live server
binding of its target that routes that kind; each post is an
:class:`~apps.content.models.AnnouncementPost` holding its thread id. All sends go
through the durable outbox (:mod:`apps.integrations.services.outbox`), whose
``forum_thread`` and ``thread_update`` modes this module is the producer for.

A changed call **updates its thread in place**, never reposts: one ``thread_update``
row unarchives and renames the thread ``[🚨 Update <Mon D>] <title>``, adds the
*Updated* tag, edits the opening post to the current facts with *What changed* on
top, and replies tagging the people following it. The reply is what moves the
thread to the top of a forum sorted by recent activity. Discord rate-limits thread
renames, so a thread gets at most one update a night; a second change the same
night waits for the next.

``allowed_mentions`` always lists exactly the users being tagged — never
``everyone``, never a role (see ``discord_api._mentions``).
"""

from __future__ import annotations

from datetime import date, timedelta

from django.conf import settings
from django.utils import timezone

from apps.content import announce_facts, usability
from apps.content.models import (
    Announcement,
    AnnouncementNudge,
    AnnouncementPost,
    AnnouncementReaction,
    AnnouncementSettings,
    ClosingSoonPost,
    ContentItem,
)
from apps.integrations.services import outbox, resolve

GOLD, SAGE, MOSS, BARK, ALERT = 0xC9A35A, 0x8DA66F, 0x5E7A3E, 0x8A6E4B, 0xB5523B

#: kind → (display name, colour, route purpose)
KINDS = {
    ContentItem.Type.GRANT: ("Grant", GOLD, "grants"),
    ContentItem.Type.FELLOWSHIP: ("Fellowship", SAGE, "fellowships"),
    ContentItem.Type.CONFERENCE: ("Conference", MOSS, "conferences"),
}
PURPOSE_KIND = {purpose: kind for kind, (_n, _c, purpose) in KINDS.items()}

#: The tags Mylo keeps on each forum it posts in.
FORUM_TAGS = {
    "grants": [
        ("New call", "🌱"),
        ("Newly relevant", "🔁"),
        ("Already open", "📌"),
        ("Updated", "🚨"),
        ("Daily list", "🗓️"),
        ("Closed", "🔒"),
    ],
    "fellowships": [
        ("New call", "🌱"),
        ("Newly relevant", "🔁"),
        ("Already open", "📌"),
        ("Updated", "🚨"),
        ("Daily list", "🗓️"),
        ("Closed", "🔒"),
    ],
    "conferences": [
        ("Dates published", "📅"),
        ("Newly relevant", "🔁"),
        ("Already open", "📌"),
        ("Updated", "🚨"),
        ("Closed", "🔒"),
    ],
}
#: A department has one forum for every kind, so its tags say the kind and the
#: department-level reason instead of the label (plan "What a department sees").
DEPT_FORUM_TAGS = [
    ("Grant", "💰"),
    ("Fellowship", "🎓"),
    ("Conference", "🗣️"),
    ("Institutional selection", "🏛️"),
    ("Department applicant", "🏫"),
    ("Department-scale programme", "🧪"),
    ("Updated", "🚨"),
    ("Daily list", "🗓️"),
    ("Closed", "🔒"),
]
LABEL_TAG = {
    Announcement.Label.NEW_CALL: "New call",
    Announcement.Label.NEWLY_RELEVANT: "Newly relevant",
    Announcement.Label.ALREADY_OPEN: "Already open",
}
_STATUS_ICON = {"ok": "✅", "warn": "⚠️", "unknown": "❔", "block": "⛔"}
NUDGE_DAYS = {"2d": 2, "1w": 7, "2w": 14, "3w": 21, "1m": 30, "2m": 60}
CLOSING_WINDOW_DAYS = 14


def _strong_fit() -> float:
    return float(getattr(settings, "ANNOUNCE_STRONG_FIT", 0.6))


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _days(n: int) -> str:
    return "1 day" if n == 1 else f"{n} days"


def short_date(d: date) -> str:
    return f"{d:%b} {d.day}"


def long_date(d: date) -> str:
    return f"{d:%a}, {d:%b} {d.day}, {d.year}"


def thread_name(announcement: Announcement, *, updated_on: date | None = None) -> str:
    title = (announcement.snapshot or {}).get("title") or "Opportunity"
    if updated_on is not None:
        return f"[🚨 Update {short_date(updated_on)}] {title}"[:100]
    return title[:100]


def _target_name(announcement: Announcement) -> str:
    target = announcement.target_lab or announcement.target_department
    return target.name if target is not None else ""


def build_embed(
    announcement: Announcement,
    *,
    changes: list[announce_facts.Change] | None = None,
    updated_on: date | None = None,
) -> dict:
    """The opening post. With ``changes``, *What changed* sits above *Why it
    matters* and the post wears the update colour."""
    kind_name, colour, _purpose = KINDS.get(
        announcement.category, ("Opportunity", BARK, "")
    )
    snap = announcement.snapshot or {}
    write_up = announcement.write_up or {}
    label = Announcement.Label(announcement.label).label if announcement.label else ""
    author = f"Mylo · {kind_name}" + (f" · {label}" if label else "")
    if updated_on is not None:
        author += f" · Updated {short_date(updated_on)}"

    facts = announcement.facts or {}
    parts = [f"**{snap['funder']}**"] if snap.get("funder") else []
    if facts.get("award"):
        parts.append(f"**{facts['award']}**")
    fields = []
    if changes:
        lines = [c.line() for c in changes]
        lines.append("-# read from the source record on its overnight refresh")
        fields.append(_field("What changed", "\n".join(lines)))

    why = write_up.get("why_it_matters") or ""
    headline = write_up.get("headline") or ""
    if headline and headline.strip() != (snap.get("title") or "").strip():
        why = f"**{headline}**\n{why}"
    if why:
        fields.append(_field("Why it matters", why))
    reasons = (announcement.alignment or {}).get("dept_reasons") or []
    if announcement.target_department_id and reasons:
        fields.append(
            _field(
                "Why it's here",
                "\n".join(f"**{r['label']}**\n> {r['evidence']}" for r in reasons),
            )
        )
    usable = [
        f"{_STATUS_ICON.get(c['status'], '•')} {c['label']}"
        for c in announcement.checks or []
        if c.get("key") != "team"
    ]
    if usable:
        fields.append(_field("Can we use this?", "\n".join(usable)))
    people = write_up.get("who_should_look") or []
    if people:
        fields.append(
            _field(
                "Labs that could lead"
                if announcement.target_department_id
                else "Who should look",
                "\n".join(
                    f"**{p['name']}**" + (f" · {p['why']}" if p.get("why") else "")
                    for p in people
                ),
            )
        )
    if write_up.get("next_step"):
        fields.append(_field("Next step", write_up["next_step"]))
    embed = {
        "author": {"name": author[:256]},
        "title": (snap.get("title") or "Opportunity")[:256],
        "color": ALERT if updated_on is not None else colour,
        "fields": fields[:25],
        "footer": {"text": f"Mycelium · {_target_name(announcement)}"[:2048]},
    }
    if snap.get("url"):
        embed["url"] = snap["url"]
    if parts:
        embed["description"] = " · ".join(parts)[:4096]
    return embed


def _field(name: str, value: str) -> dict:
    return {"name": name[:256], "value": value[:1024], "inline": False}


def buttons(post_id: int, url: str, interested: int = 0) -> list:
    label = "Interested" + (f" · {interested}" if interested else "")
    row = [
        {
            "type": 2,
            "style": 3,
            "label": label,
            "emoji": {"name": "👍"},
            "custom_id": f"ann:{post_id}:interested",
        },
        {
            "type": 2,
            "style": 2,
            "label": "Remind me",
            "emoji": {"name": "🔔"},
            "custom_id": f"ann:{post_id}:remind",
        },
        {
            "type": 2,
            "style": 2,
            "label": "Not for us",
            "emoji": {"name": "🚫"},
            "custom_id": f"ann:{post_id}:notforus",
        },
    ]
    if url:
        row.append({"type": 2, "style": 5, "label": "View the call", "url": url})
    return [{"type": 1, "components": row}]


def thread_url(post: AnnouncementPost) -> str:
    if not post.thread_id:
        return ""
    return (
        f"https://discord.com/channels/{post.binding.guild.guild_id}/{post.thread_id}"
    )


# --------------------------------------------------------------------------- #
# Who is following
# --------------------------------------------------------------------------- #
def followers(announcement: Announcement) -> list:
    """People whose latest interested/unfollow reaction is *interested*."""
    latest: dict[int, AnnouncementReaction] = {}
    for reaction in announcement.reactions.filter(
        kind__in=[
            AnnouncementReaction.Kind.INTERESTED,
            AnnouncementReaction.Kind.UNFOLLOW,
        ]
    ).select_related("user"):
        latest[reaction.user_id] = reaction
    return [
        r.user
        for r in latest.values()
        if r.kind == AnnouncementReaction.Kind.INTERESTED
    ]


def mentions_for(users) -> tuple[str, dict]:
    """``("<@a> <@b>", {"users": [...]})`` for the linked ones; nobody else."""
    ids = resolve.active_discord_ids_for_users(list(users))
    snowflakes = [ids[u.id] for u in users if u.id in ids]
    return " ".join(f"<@{s}>" for s in snowflakes), {"users": snowflakes}


# --------------------------------------------------------------------------- #
# Forums
# --------------------------------------------------------------------------- #
def route_for(binding, kind: str):
    return resolve.get_route(binding, KINDS[kind][2])


def ensure_forum_tags(route) -> dict:
    """Make sure the forum carries Mylo's tags; return ``{name: id}``. Best effort:
    a forum Mylo may not edit simply gets posts without tags."""
    wanted = forum_tags_for(route)
    have = dict(route.forum_tag_ids or {})
    if all(name in have for name, _emoji in wanted):
        return have
    from apps.integrations.services import discord_api

    try:
        resp = discord_api.get_channel(route.channel_id)
        if resp.status != 200:
            return have
        current = resp.json.get("available_tags") or []
        names = {t.get("name") for t in current}
        tags = [
            {"id": t["id"], "name": t["name"], "emoji_name": t.get("emoji_name")}
            for t in current
        ] + [
            {"name": name, "emoji_name": emoji}
            for name, emoji in wanted
            if name not in names
        ]
        if len(tags) > len(current):
            patched = discord_api.modify_channel(
                route.channel_id, {"available_tags": tags[:20]}
            )
            if patched.status == 200:
                current = patched.json.get("available_tags") or current
        have = {t["name"]: t["id"] for t in current if t.get("id")}
    except discord_api.DiscordHTTPError:
        return have
    route.forum_tag_ids = have
    route.save(update_fields=["forum_tag_ids", "updated_at"])
    return have


def forum_tags_for(route) -> list[tuple[str, str]]:
    """The tags a route's forum carries: per kind for a lab, one shared set for a
    department's single forum."""
    if route.binding.department_id:
        return DEPT_FORUM_TAGS
    return FORUM_TAGS.get(route.purpose, [])


def _tags(route, names: list[str]) -> list[str]:
    ids = route.forum_tag_ids or {}
    return [ids[n] for n in names if n in ids][:5]  # Discord applies at most five


def _post_tags(announcement: Announcement, *extra: str) -> list[str]:
    """Tag names for a thread: the label for a lab; the kind and each
    department-level reason for a department."""
    if announcement.target_department_id:
        kind = KINDS.get(announcement.category, ("",))[0]
        reasons = (announcement.alignment or {}).get("dept_reasons") or []
        names = [kind, *(r["label"] for r in reasons)]
    else:
        names = [_label_tag(announcement)]
    # At most five: a kind, three reasons and one status tag.
    return [*(n for n in names if n), *extra]


def _label_tag(announcement: Announcement) -> str:
    if (
        announcement.category == ContentItem.Type.CONFERENCE
        and announcement.label != Announcement.Label.ALREADY_OPEN
    ):
        return "Dates published"
    return LABEL_TAG.get(announcement.label, "")


# --------------------------------------------------------------------------- #
# Posting
# --------------------------------------------------------------------------- #
def bindings_for(announcement: Announcement) -> list:
    if announcement.target_lab_id:
        return resolve.bindings_for_lab(announcement.target_lab)
    return resolve.bindings_for_department(announcement.target_department)


def post(
    announcement: Announcement, *, drain: bool = True, bindings=None
) -> list[AnnouncementPost]:
    """Queue one thread per live binding that routes this kind (or only in
    ``bindings``, for a manager's manual announce from search)."""
    posts = []
    for binding in bindings if bindings is not None else bindings_for(announcement):
        route = route_for(binding, announcement.category)
        if route is None:
            continue
        ensure_forum_tags(route)
        row, _ = AnnouncementPost.objects.get_or_create(
            announcement=announcement,
            binding=binding,
            defaults={"channel_id": route.channel_id},
        )
        key = f"announce:{binding.id}:{announcement.content_id or announcement.id}"
        if row.deleted_at is not None:
            # Its thread was deleted by hand and someone asked for it again: a
            # fresh thread under a fresh key (the old send stays in the history).
            key = resolve.next_resend_key(key)
            row.thread_id, row.outbox_key, row.deleted_at = "", "", None
            row.update_log, row.closed_at, row.channel_id = [], None, route.channel_id
            row.save()
        elif row.outbox_key:
            posts.append(row)
            continue
        content, allowed = _strong_match_line(announcement)
        outbox_row, _ = resolve.enqueue_outbox(
            dedupe_key=key,
            kind="announcement",
            target_type=resolve.OUTBOX_CHANNEL,
            channel_id=route.channel_id,
            lab=announcement.target_lab,
            content=content,
            embed=build_embed(announcement),
            components=buttons(row.id, (announcement.snapshot or {}).get("url", "")),
            allowed_mentions=allowed,
            subject_type="announcement_post",
            subject_id=str(row.id),
            mode=resolve.OUTBOX_MODE.FORUM_THREAD,
            extra={
                "name": thread_name(announcement),
                "applied_tags": _tags(route, _post_tags(announcement)),
            },
        )
        row.outbox_key = outbox_row.dedupe_key
        row.thread_name = thread_name(announcement)
        row.save(update_fields=["outbox_key", "thread_name", "updated_at"])
        posts.append(row)
    if posts:
        notify_eligible(announcement, posts[0])
    if drain:
        flush()
    return posts


def notify_eligible(announcement: Announcement, post_row: AnnouncementPost) -> int:
    """A department fellowship shows counts only; each member who may be eligible
    is told privately, once (plan "What a department sees")."""
    if not (
        announcement.target_department_id
        and announcement.category == ContentItem.Type.FELLOWSHIP
        and announcement.content is not None
    ):
        return 0
    from apps.content import announce
    from apps.content.fellowships import eligibility_from_profile, evaluate_eligibility

    target = announce.Target(
        "department", announcement.target_department, _settings_for(announcement)
    )
    metadata = announcement.content.metadata or {}
    iso = timezone.localdate().isoformat()
    sent = 0
    for user in announce._members(target):
        profile = getattr(user, "profile", None)
        if profile is None:
            continue
        verdict = evaluate_eligibility(metadata, eligibility_from_profile(profile), iso)
        if verdict["tier"] == "not_eligible":
            continue
        if resolve.active_identity_for_user(user) is None:
            continue
        _row, created = outbox.enqueue_dm(
            dedupe_key=f"ann-eligible:{announcement.id}:{user.id}",
            kind="announcement_eligible",
            user=user,
            embed=_eligible_embed(announcement),
            components=buttons(
                post_row.id, (announcement.snapshot or {}).get("url", "")
            ),
            subject_type="announcement",
            subject_id=str(announcement.id),
        )
        sent += int(created)
    return sent


def _eligible_embed(announcement: Announcement) -> dict:
    snap = announcement.snapshot or {}
    facts = announcement.facts or {}
    lines = [
        f"{_target_name(announcement)} was told about this fellowship, and your "
        "profile suggests you may be eligible. Only you were told that."
    ]
    if facts.get("deadline"):
        lines.append(f"Due **{long_date(date.fromisoformat(facts['deadline']))}**.")
    embed = {
        "author": {"name": "Mylo · Fellowship"},
        "title": (snap.get("title") or "Fellowship")[:256],
        "description": "\n".join(lines)[:4096],
        "color": SAGE,
    }
    if snap.get("url"):
        embed["url"] = snap["url"]
    return embed


def _strong_match_line(announcement: Announcement) -> tuple[str, dict | None]:
    """Strong-match tagging, off unless the target turned it on (plan D7)."""
    if announcement.target_department_id:
        return "", None  # a department post names labs, never tags people
    settings_row = _settings_for(announcement)
    if settings_row is None or not settings_row.strong_match_tagging:
        return "", None
    from django.contrib.auth import get_user_model

    people = (announcement.alignment or {}).get("people") or []
    ids = [p["user_id"] for p in people if (p.get("fit") or 0) >= _strong_fit()]
    users = list(get_user_model().objects.filter(id__in=ids))
    line, allowed = mentions_for(users)
    if not line:
        return "", None
    return f"🎯 Strong match for {line}", allowed


def _settings_for(announcement: Announcement) -> AnnouncementSettings | None:
    if announcement.target_lab_id:
        return AnnouncementSettings.objects.filter(
            target_lab_id=announcement.target_lab_id
        ).first()
    return AnnouncementSettings.objects.filter(
        target_department_id=announcement.target_department_id
    ).first()


def flush() -> None:
    """Drain the outbox now and copy thread ids back onto their posts."""
    outbox.drain()
    sync_thread_ids()


def mark_thread_deleted(thread_id: str) -> int:
    """A thread Mylo posted was deleted by hand: never link or update it again."""
    now = timezone.now()
    count = AnnouncementPost.objects.filter(
        thread_id=str(thread_id), deleted_at__isnull=True
    ).update(deleted_at=now, updated_at=now)
    ClosingSoonPost.objects.filter(
        thread_id=str(thread_id), replaced_at__isnull=True
    ).update(replaced_at=now)
    return count


def verify_threads(target) -> int:
    """Nightly backstop for the gateway's thread-delete event, which a restart can
    miss: ask Discord for each open thread of ``target`` and mark the ones that are
    gone. Returns how many were found deleted."""
    from apps.integrations.services import discord_api

    posts = AnnouncementPost.objects.filter(
        deleted_at__isnull=True, closed_at__isnull=True
    ).exclude(thread_id="")
    posts = posts.filter(
        **(
            {"announcement__target_lab": target.obj}
            if target.kind == "lab"
            else {"announcement__target_department": target.obj}
        )
    )
    gone = 0
    for post in posts:
        try:
            resp = discord_api.get_channel(post.thread_id)
        except discord_api.DiscordHTTPError:
            continue  # a blip is not a deletion
        if resp.status == 404:
            gone += mark_thread_deleted(post.thread_id)
    return gone


def sync_thread_ids() -> int:
    """A created thread's id comes back on its outbox row; record it. A send that
    found its thread gone marks the post deleted."""
    for channel_id in resolve.channels_found_gone(kind_prefix="announcement"):
        mark_thread_deleted(channel_id)
    updated = 0
    for row in AnnouncementPost.objects.filter(thread_id="").exclude(outbox_key=""):
        sent = resolve.get_outbox_by_key(row.outbox_key)
        if (
            sent is not None
            and sent.status == resolve.OUTBOX_SENT
            and sent.discord_message_id
        ):
            row.thread_id = sent.discord_message_id
            row.posted_at = sent.sent_at or timezone.now()
            row.save(update_fields=["thread_id", "posted_at", "updated_at"])
            updated += 1
    for row in ClosingSoonPost.objects.filter(thread_id=""):
        sent = resolve.get_outbox_by_key(row.outbox_key)
        if (
            sent is not None
            and sent.status == resolve.OUTBOX_SENT
            and sent.discord_message_id
        ):
            row.thread_id = sent.discord_message_id
            row.save(update_fields=["thread_id"])
            updated += 1
    return updated


# --------------------------------------------------------------------------- #
# Updates, closing, the closing-soon list
# --------------------------------------------------------------------------- #
def apply_updates(plan, today: date) -> dict:
    """Carry out one target's :class:`~apps.content.announce_updates.UpdatePlan`."""
    from apps.content import announce_updates

    sync_thread_ids()
    done = {"updated": 0, "deferred": 0, "closed": 0, "closing_soon": 0}
    for changed in plan.changed:
        if _update_thread(changed, today, plan.target):
            announce_updates.record_update(changed)
            done["updated"] += 1
        else:
            done["deferred"] += 1
    for announcement in plan.to_close:
        _close(announcement)
        announce_updates.record_closed(announcement, timezone.now())
        done["closed"] += 1
    for kind, rows in plan.closing_soon.items():
        done["closing_soon"] += _closing_soon(plan.target, kind, rows, today)
    for kind in (ContentItem.Type.GRANT, ContentItem.Type.FELLOWSHIP):
        if kind not in plan.closing_soon:
            # Nothing closes: post nothing, but take yesterday's list down rather
            # than leave it saying "today" about a deadline that has passed.
            _retire_lists(plan.target, kind, today)
    flush()
    return done


def _target_bindings(target) -> list:
    return (
        resolve.bindings_for_lab(target.obj)
        if target.kind == "lab"
        else resolve.bindings_for_department(target.obj)
    )


def _retire_lists(target, kind: str, today: date) -> None:
    for binding in _target_bindings(target):
        _retire_old_lists(binding, kind, today)


def _retire_old_lists(binding, kind: str, today: date) -> None:
    for old in ClosingSoonPost.objects.filter(
        binding=binding, category=kind, on_date__lt=today, replaced_at__isnull=True
    ):
        if old.thread_id:
            resolve.enqueue_outbox(
                dedupe_key=f"closing-soon-delete:{old.id}",
                kind="closing_soon_delete",
                target_type=resolve.OUTBOX_CHANNEL,
                channel_id=old.thread_id,
                mode=resolve.OUTBOX_MODE.DELETE_CHANNEL,
            )
        old.replaced_at = timezone.now()
        old.save(update_fields=["replaced_at"])


def _update_thread(changed, today: date, target) -> bool:
    """Queue the in-place update for every thread of one announcement. ``False``
    when it must wait: a thread not created yet, or one already updated today."""
    announcement = changed.announcement
    posts = list(
        announcement.posts.filter(deleted_at__isnull=True).select_related(
            "binding__guild"
        )
    )
    if not posts or any(not p.thread_id for p in posts):
        return False
    if any(
        p.update_log and p.update_log[-1].get("on") == today.isoformat() for p in posts
    ):
        return False  # one rename per thread per night

    # The post shows current facts: refresh the checks against the moved record.
    if announcement.content is not None:
        reader = (
            usability.reader_for_lab(announcement.target_lab)
            if announcement.target_lab_id
            else usability.reader_for_department(announcement.target_department)
        )
        checks = usability.assess(announcement.content, reader, today)
        announcement.checks = [c.as_dict() for c in checks]
    announcement.facts = changed.facts
    announcement.save(update_fields=["checks", "facts", "updated_at"])

    users = followers(announcement)
    line, allowed = mentions_for(users)
    summary = announce_facts.headline(changed.changes)
    reply = (
        f"🚨 **Update {short_date(today)}:** {summary}. "
        "The post above now shows the current call."
    )
    if line:
        reply += f" {line}"
    embed = build_embed(announcement, changes=changed.changes, updated_on=today)
    for p in posts:
        route = route_for(p.binding, announcement.category)
        tag_names = _post_tags(announcement, "Updated")
        name = thread_name(announcement, updated_on=today)
        key = f"announce-update:{p.id}:{today.isoformat()}"
        resolve.enqueue_outbox(
            dedupe_key=key,
            kind="announcement_update",
            target_type=resolve.OUTBOX_CHANNEL,
            channel_id=p.thread_id,
            lab=announcement.target_lab,
            content=reply,
            allowed_mentions=allowed or None,
            subject_type="announcement_post",
            subject_id=str(p.id),
            mode=resolve.OUTBOX_MODE.THREAD_UPDATE,
            extra={
                "patch": {
                    "archived": False,
                    "name": name,
                    **({"applied_tags": _tags(route, tag_names)} if route else {}),
                },
                "edit": {
                    "message_id": p.thread_id,
                    "embed": embed,
                    "components": buttons(
                        p.id, (announcement.snapshot or {}).get("url", ""), len(users)
                    ),
                },
            },
        )
        p.thread_name = name
        p.update_log = [
            *(p.update_log or []),
            {
                "on": today.isoformat(),
                "changes": [c.as_dict() for c in changed.changes],
                "outbox_key": key,
                "tagged": len(allowed.get("users", [])) if allowed else 0,
            },
        ]
        p.save(update_fields=["thread_name", "update_log", "updated_at"])
    return True


def _close(announcement: Announcement) -> None:
    for p in announcement.posts.filter(deleted_at__isnull=True).select_related(
        "binding"
    ):
        if not p.thread_id or p.closed_at:
            continue
        route = route_for(p.binding, announcement.category)
        tags = _post_tags(announcement, "Closed")
        resolve.enqueue_outbox(
            dedupe_key=f"announce-close:{p.id}",
            kind="announcement_close",
            target_type=resolve.OUTBOX_CHANNEL,
            channel_id=p.thread_id,
            lab=announcement.target_lab,
            subject_type="announcement_post",
            subject_id=str(p.id),
            mode=resolve.OUTBOX_MODE.THREAD_UPDATE,
            extra={
                "patch": {
                    "archived": False,
                    **({"applied_tags": _tags(route, tags)} if route else {}),
                },
                "after_patch": {"archived": True},
            },
        )
        p.closed_at = timezone.now()
        p.save(update_fields=["closed_at", "updated_at"])


def closing_soon_embed(target_name: str, kind: str, rows, today: date) -> dict:
    noun = "grant" if kind == ContentItem.Type.GRANT else "fellowship"
    count = len(rows)
    title = (
        f"One {noun} on your list closes in the next two weeks"
        if count == 1
        else f"{count} {noun}s on your list close in the next two weeks"
    )
    lines = []
    for r in rows[:20]:
        when = (
            "**Today**"
            if r.days == 0
            else f"**{r.due:%a}, {r.due:%b} {r.due.day}** · {_days(r.days)}"
        )
        name = f"[{r.title}]({r.url})" if r.url else r.title
        lines.append(f"{when} · {name}" + (f" · {r.funder}" if r.funder else ""))
    lines.append(
        "\nEach title opens the call. Use 🔔 in an item's own thread to set your "
        "own reminder."
    )
    return {
        "author": {"name": "Mylo · Closing soon · replaced every morning"},
        "title": title,
        "description": "\n".join(lines)[:4096],
        "color": BARK,
        "footer": {"text": f"Mycelium · {target_name}"},
    }


def _closing_soon(target, kind: str, rows, today: date) -> int:
    """Today's list thread in each binding's forum for ``kind``; yesterday's is
    deleted once today's is queued. Nothing is posted on a day with nothing."""
    from apps.content.announce import Target  # noqa: F401 — type only

    posted = 0
    for binding in _target_bindings(target):
        route = route_for(binding, kind)
        if route is None:
            continue
        ensure_forum_tags(route)
        key = f"closing-soon:{binding.id}:{kind}:{today.isoformat()}"
        row, created = ClosingSoonPost.objects.get_or_create(
            binding=binding, category=kind, on_date=today, defaults={"outbox_key": key}
        )
        if not created:
            continue
        resolve.enqueue_outbox(
            dedupe_key=key,
            kind="closing_soon",
            target_type=resolve.OUTBOX_CHANNEL,
            channel_id=route.channel_id,
            embed=closing_soon_embed(target.name, kind, rows, today),
            mode=resolve.OUTBOX_MODE.FORUM_THREAD,
            extra={
                # A department's kinds share one forum, so its lists say the kind.
                "name": "⏳ Closing soon"
                + (f" · {KINDS[kind][0]}s" if binding.department_id else "")
                + f": next {CLOSING_WINDOW_DAYS} days "
                f"({today:%a}, {today:%b} {today.day})",
                "applied_tags": _tags(route, ["Daily list"]),
            },
        )
        _retire_old_lists(binding, kind, today)
        posted += 1
    return posted


# --------------------------------------------------------------------------- #
# Nudges
# --------------------------------------------------------------------------- #
def arm_nudge(nudge: AnnouncementNudge, today: date) -> None:
    """A nudge whose moment has already passed for the current deadline is marked
    as fired for it, so asking late never produces an instant, stale tag."""
    ann = nudge.announcement
    if ann.content is None:
        return
    due_iso = announce_facts.facts_for(ann.content, today)["deadline"]
    if not due_iso:
        return
    due = date.fromisoformat(due_iso)
    if due - timedelta(days=NUDGE_DAYS.get(nudge.offset, 14)) <= today:
        if due_iso not in (nudge.fired_for or []):
            nudge.fired_for = [*(nudge.fired_for or []), due_iso]
            nudge.save(update_fields=["fired_for", "updated_at"])


def _dm_nudge(nudge, ann, due: date, days: int, title: str, due_iso: str) -> None:
    """A reminder by DM, with a link to the thread and a way to stop."""
    post = (
        ann.posts.exclude(thread_id="")
        .filter(deleted_at__isnull=True)
        .select_related("binding__guild")
        .order_by("id")
        .first()
    )
    buttons_row = []
    if post is not None:
        buttons_row.append(
            {"type": 2, "style": 5, "label": "Open the thread", "url": thread_url(post)}
        )
        buttons_row.append(
            {
                "type": 2,
                "style": 2,
                "label": "Stop reminding me",
                "emoji": {"name": "🔕"},
                "custom_id": f"ann:{post.id}:unremind",
            }
        )
    snap = ann.snapshot or {}
    embed = {
        "author": {"name": "Mylo · Reminder"},
        "title": (title or "This call")[:256],
        "description": (
            f"⏳ **{days} day{'s' if days != 1 else ''} left.** "
            f"It closes **{long_date(due)}**."
        ),
        "color": GOLD,
    }
    if snap.get("url"):
        embed["url"] = snap["url"]
    outbox.enqueue_dm(
        dedupe_key=f"nudge-dm:{nudge.id}:{due_iso}",
        kind="announcement_nudge",
        user=nudge.user,
        discord_user_id="" if nudge.user_id else nudge.discord_user_id,
        embed=embed,
        components=[{"type": 1, "components": buttons_row}] if buttons_row else None,
        subject_type="announcement_nudge",
        subject_id=str(nudge.id),
    )


def send_due_nudges(today: date) -> int:
    """Tag each person in the thread on the day their nudge falls due, computed
    from the call's *current* deadline so a moved date moves the nudge."""
    sent = 0
    tagged_tonight: set[tuple] = set()
    nudges = (
        AnnouncementNudge.objects.filter(
            active=True, announcement__state=Announcement.State.POSTED
        )
        .select_related("announcement__content", "user")
        .order_by("id")
    )
    for nudge in nudges:
        if nudge.user_id is None and not nudge.discord_user_id:
            continue
        ann = nudge.announcement
        if ann.content is None:
            continue
        due_iso = announce_facts.facts_for(ann.content, today)["deadline"]
        if not due_iso or due_iso in (nudge.fired_for or []):
            continue
        due = date.fromisoformat(due_iso)
        if today < due - timedelta(days=NUDGE_DAYS.get(nudge.offset, 14)):
            continue
        if (
            nudge.source == AnnouncementNudge.Source.INTERESTED
            and nudge.user not in followers(ann)
        ):
            nudge.active = False
            nudge.save(update_fields=["active", "updated_at"])
            continue
        if nudge.user_id is not None:
            line, allowed = mentions_for([nudge.user])
        else:  # a guest: no Mycelium account, only their Discord id
            line = f"<@{nudge.discord_user_id}>"
            allowed = {"users": [nudge.discord_user_id]}
        if not line:
            continue
        pair = (nudge.announcement_id, nudge.user_id or nudge.discord_user_id, due_iso)
        if pair in tagged_tonight:
            # Two of one person's nudges due the same night: one tag says it.
            nudge.fired_for = [*(nudge.fired_for or []), due_iso]
            nudge.save(update_fields=["fired_for", "updated_at"])
            continue
        tagged_tonight.add(pair)
        days = (due - today).days
        title = (ann.snapshot or {}).get("title") or "This call"
        if nudge.delivery == AnnouncementNudge.Delivery.DM:
            _dm_nudge(nudge, ann, due, days, title, due_iso)
            nudge.fired_for = [*(nudge.fired_for or []), due_iso]
            nudge.save(update_fields=["fired_for", "updated_at"])
            sent += 1
            continue
        text = (
            f"⏳ **{days} day{'s' if days != 1 else ''} left.** {title} closes "
            f"**{long_date(due)}**. {line}"
        )
        for p in ann.posts.exclude(thread_id="").filter(deleted_at__isnull=True):
            resolve.enqueue_outbox(
                dedupe_key=f"nudge:{nudge.id}:{due_iso}:{p.id}",
                kind="announcement_nudge",
                target_type=resolve.OUTBOX_CHANNEL,
                channel_id=p.thread_id,
                lab=ann.target_lab,
                content=text,
                allowed_mentions=allowed,
                subject_type="announcement_nudge",
                subject_id=str(nudge.id),
            )
        nudge.fired_for = [*(nudge.fired_for or []), due_iso]
        nudge.save(update_fields=["fired_for", "updated_at"])
        sent += 1
    if sent:
        flush()
    return sent
