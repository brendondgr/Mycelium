"""Links from search results to the threads that already discuss them (plan D15).

* In Discord, ``/mylo search`` shows "💬 Already discussed here" for results that
  have a live thread **in the server it ran in** — and nothing in a DM or in a
  server without announcements.
* A manager of a binding in that server gets "Announce to #…" for results that
  binding has not posted, which posts once (:func:`manual_announce`).
* On the web, a search card shows "Discussed in Discord" for every server the
  reader's own labs and departments are bound in.

A thread someone deleted by hand carries ``deleted_at`` (set by the gateway's
thread-delete event, or by a send that found it gone) and is never linked.
"""

from __future__ import annotations

from collections.abc import Iterable

from django.db.models import Q

from apps.content.models import Announcement, AnnouncementPost, ContentItem

_KIND_PURPOSE = {
    ContentItem.Type.GRANT: "grants",
    ContentItem.Type.FELLOWSHIP: "fellowships",
    ContentItem.Type.CONFERENCE: "conferences",
}


def _live_posts():
    from apps.integrations.models import DiscordGuildLink, DiscordTargetBinding

    return (
        AnnouncementPost.objects.exclude(thread_id="")
        .filter(
            deleted_at__isnull=True,
            binding__state=DiscordTargetBinding.State.ACTIVE,
            binding__guild__state=DiscordGuildLink.State.ACTIVE,
            announcement__content__isnull=False,
        )
        .select_related("binding__guild", "announcement")
    )


def _link(post: AnnouncementPost, names: dict[str, str] | None = None) -> dict:
    return {
        "guild_id": post.binding.guild.guild_id,
        "guild_name": post.binding.guild.guild_name_cache,
        "channel_id": post.channel_id,
        "channel_name": (names or {}).get(post.channel_id, ""),
        "thread_id": post.thread_id,
        "thread_url": (
            f"https://discord.com/channels/{post.binding.guild.guild_id}/{post.thread_id}"
        ),
    }


def discussed_in_guild(content_ids: Iterable, guild_id: str) -> dict[str, dict]:
    """``{content_id: link}`` for results with a live thread in ``guild_id``."""
    if not guild_id:
        return {}
    ids = [str(c) for c in content_ids]
    names = _route_names()
    out: dict[str, dict] = {}
    for post in (
        _live_posts()
        .filter(
            binding__guild__guild_id=str(guild_id), announcement__content_id__in=ids
        )
        .order_by("id")
    ):
        out.setdefault(str(post.announcement.content_id), _link(post, names))
    return out


def discussed_for_user(user, content_ids: Iterable) -> dict[str, list[dict]]:
    """``{content_id: [link, …]}`` across the servers of the reader's own labs and
    departments: the web's "Discussed in Discord"."""
    from apps.accounts.models import DeptMembership, LabMembership

    lab_ids = list(
        LabMembership.objects.filter(user=user).values_list("lab_id", flat=True)
    )
    dept_ids = list(
        DeptMembership.objects.filter(user=user).values_list("department_id", flat=True)
    )
    if not lab_ids and not dept_ids:
        return {}
    ids = [str(c) for c in content_ids]
    out: dict[str, list[dict]] = {}
    posts = (
        _live_posts()
        .filter(
            Q(binding__lab_id__in=lab_ids) | Q(binding__department_id__in=dept_ids),
            announcement__content_id__in=ids,
        )
        .order_by("binding__activated_at", "id")
    )
    names = _route_names()
    for post in posts:
        out.setdefault(str(post.announcement.content_id), []).append(_link(post, names))
    return out


def for_target(target_filter: dict, content_ids: Iterable) -> dict[str, dict]:
    """``{content_id: {"label", "posted_at", "discord": [link, …]}}`` for the items
    a lab (or department) announced: the feed card's "Announced" row."""
    lab = target_filter.get("target_lab")
    dept = target_filter.get("target_department")
    if lab is None and dept is None:
        return {}
    field = (
        {"announcement__target_lab": lab}
        if lab is not None
        else {"announcement__target_department": dept}
    )
    ids = [str(c) for c in content_ids]
    names = _route_names()
    out: dict[str, dict] = {}
    for post in (
        _live_posts()
        .filter(**field, announcement__content_id__in=ids)
        .order_by("binding__activated_at", "id")
    ):
        cid = str(post.announcement.content_id)
        row = out.setdefault(
            cid,
            {
                "label": post.announcement.label,
                "posted_at": post.posted_at,
                "discord": [],
            },
        )
        row["discord"].append(_link(post, names))
    return out


def _route_names() -> dict[str, str]:
    from apps.integrations.models import DiscordChannelRoute

    return dict(
        DiscordChannelRoute.objects.exclude(channel_name="").values_list(
            "channel_id", "channel_name"
        )
    )


def announce_options(user, guild_id: str, items) -> dict[str, list[dict]]:
    """``{content_id: [{binding_id, channel_id, purpose, target}]}`` — the bindings in
    this server the caller manages that route the item's kind and have not posted
    it. Empty in a DM."""
    if not guild_id or user is None:
        return {}
    from apps.integrations.services import resolve

    managed = [
        b
        for b in resolve.bindings_for_guild(guild_id)
        if resolve.web_user_can_manage_binding(user, b)
    ]
    if not managed:
        return {}
    ids = [str(i.id) for i in items]
    posted = {
        (p.binding_id, str(p.announcement.content_id))
        for p in AnnouncementPost.objects.filter(
            binding__in=managed,
            announcement__content_id__in=ids,
            deleted_at__isnull=True,
        ).select_related("announcement")
    }
    out: dict[str, list[dict]] = {}
    for item in items:
        purpose = _KIND_PURPOSE.get(item.type)
        if purpose is None:
            continue
        for binding in managed:
            if (binding.id, str(item.id)) in posted:
                continue
            route = resolve.get_route(binding, purpose)
            if route is None:
                continue
            out.setdefault(str(item.id), []).append(
                {
                    "binding_id": binding.id,
                    "channel_id": route.channel_id,
                    "purpose": purpose,
                    "target": resolve.binding_name(binding),
                }
            )
    return out


def manual_announce(
    discord_user_id: str, guild_id: str, binding_id, content_id: str
) -> tuple[str, dict]:
    """A manager posts one search result to one binding. Posts once: a second press
    finds the thread and links it."""
    from django.utils import timezone

    from apps.content import announce, discord_announcements
    from apps.content import announce_editor as editor
    from apps.integrations.services import gate, resolve

    verdict = gate.authorize(
        discord_user_id=discord_user_id,
        action="ann_manual",
        guild_id=guild_id,
        binding_id=binding_id,
        subject_id=str(content_id),
    )
    if not verdict.ok:
        return (str(verdict.denial), {"message": verdict.message})
    binding = verdict.binding
    item = ContentItem.objects.filter(id=content_id).first()
    purpose = _KIND_PURPOSE.get(item.type) if item else None
    if item is None or purpose is None:
        return ("not_found", {"message": "That item can't be announced."})
    route = resolve.get_route(binding, purpose)
    if route is None:
        return ("no_route", {"message": f"This server has no {purpose} forum set up."})

    existing = discussed_in_guild([item.id], guild_id).get(str(item.id))
    target_filter = (
        {"target_lab": binding.lab}
        if binding.lab_id
        else {"target_department": binding.department}
    )
    ann = Announcement.objects.filter(**target_filter, content=item).first()
    if (
        ann is not None
        and ann.posts.filter(binding=binding, deleted_at__isnull=True)
        .exclude(thread_id="")
        .exists()
        and existing
    ):
        return (
            "exists",
            {
                "message": f"Already discussed here → {existing['thread_url']}",
                "thread_url": existing["thread_url"],
            },
        )

    if ann is None or ann.state != Announcement.State.POSTED:
        settings_row = announce.AnnouncementSettings.objects.filter(
            **{
                (
                    "target_lab" if binding.lab_id else "target_department"
                ): binding.target
            }
        ).first() or announce.AnnouncementSettings(
            **{
                (
                    "target_lab" if binding.lab_id else "target_department"
                ): binding.target
            }
        )
        target = announce.Target(binding.target_kind, binding.target, settings_row)
        reader = (
            announce.usability.reader_for_lab(binding.lab)
            if binding.lab_id
            else announce.usability.reader_for_department(binding.department)
        )
        row = announce.RelevanceScore.objects.filter(
            **target.persist_kwargs, content=item
        ).first() or announce.RelevanceScore(content=item, signals={}, score=0)
        prepared = announce.prepare(
            target,
            row,
            timezone.localdate(),
            seeding=False,
            reader=reader,
            members=announce._members(target),
            fellowship_counts={},
            complete=editor._model_complete,
        )
        ann = announce._record(target, prepared, Announcement.State.POSTED, "")
        ann.origin = Announcement.Origin.MANUAL
        ann.created_by = verdict.user
        ann.save(update_fields=["origin", "created_by", "updated_at"])
    _post_to_binding(ann, binding)
    discord_announcements.flush()
    link = discussed_in_guild([item.id], guild_id).get(str(item.id))
    from apps.integrations.services import audit

    audit.discord_audit(
        action="announcements.manual",
        actor=verdict.user,
        guild_id=guild_id,
        metadata={"binding_id": binding.id, "content_id": str(item.id)},
    )
    if link is None:
        return ("queued", {"message": "Queued. The thread will appear in a moment."})
    return (
        "ok",
        {
            "message": f"📣 Posted → {link['thread_url']}",
            "thread_url": link["thread_url"],
        },
    )


def _post_to_binding(ann: Announcement, binding) -> None:
    """Post ``ann`` in this one binding (the others keep their own decisions)."""
    from apps.content import discord_announcements

    discord_announcements.post(ann, drain=False, bindings=[binding])
