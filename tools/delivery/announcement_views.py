"""Opportunity announcements on the web (plan "Web surfaces", D17).

* ``GET  /api/announcements/?lab=<slug>|department=<id>`` — what Mylo announced,
  what it held back and why, the closing-soon list, and every server the target is
  bound in with its forums. Any member may read it.
* ``GET/PUT /api/announcements/settings/?lab=|department=`` — the target's
  announcement settings; managers write. Switching on for the first time posts the
  activation seed straight away (in the background).
* ``POST /api/announcements/test/?lab=|department=`` — a test thread in each of the
  target's forums, so a manager can see where posts land. Managers only.
* ``POST /api/announcements/create-channels/?binding=<id>`` — "Create them for me"
  for one server binding. That binding's own managers only.
* ``POST /api/announcements/link-click/`` — ``{thread_url, surface}``: a web link
  into a thread was opened (plan Phase 8 measurement). Recorded only for a reader
  who can see that lab or department; always 204, so a link never waits on it.
* ``GET  /api/announcements/department-opportunities/?department=<id>`` — the
  department's Opportunities page: its slate's department-level items only, each
  with its reasons (quoted evidence), the labs that could lead, its checks, and
  its Discord thread once announced. Any member may read it.

Every Discord link carries the server, the channel's name and the thread URL, so
the web can render it as the Discord logo plus ``#channel`` opening in a new tab.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from apps.accounts import capabilities as caps
from apps.accounts.models import Department, Lab
from apps.accounts.permissions import (
    user_has_department_access,
    user_has_lab_access,
)
from apps.integrations.services import resolve
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from tools.delivery import announce, announce_facts
from tools.delivery.announce_editor import looker_label
from tools.delivery.discord_announcements import followers
from tools.delivery.models import Announcement, AnnouncementSettings

#: How far back the announced list reaches.
LIST_DAYS = 60
LIST_MAX = 100
_SETTINGS_FIELDS = (
    "enabled",
    "grants",
    "fellowships",
    "conferences",
    "daily_cap",
    "default_nudge",
    "closing_soon_list",
    "strong_match_tagging",
    "save_on_interest",
    "activation_seed",
    "min_award",
)


def _target(request, *, manage: bool = False):
    """``(kind, obj, None)`` or ``(None, None, error Response)``."""
    slug = request.query_params.get("lab", "")
    dept_id = request.query_params.get("department", "")
    if slug:
        obj = Lab.objects.filter(slug=slug).first()
        kind = "lab"
        allowed = obj is not None and caps.has_capability(
            request.user, obj, caps.ANNOUNCEMENTS_MANAGE if manage else caps.MEMBERSHIP
        )
    elif dept_id:
        try:
            obj = Department.objects.filter(pk=dept_id).first()
        except (ValueError, DjangoValidationError):
            obj = None
        kind = "department"
        allowed = obj is not None and caps.has_capability(
            request.user, obj, caps.ANNOUNCEMENTS_MANAGE if manage else caps.MEMBERSHIP
        )
    else:
        return (
            None,
            None,
            Response(
                {"detail": "Pass ?lab=<slug> or ?department=<id>."},
                status=status.HTTP_400_BAD_REQUEST,
            ),
        )
    if obj is None:
        return None, None, Response({"detail": "Not found."}, status=404)
    if not allowed:
        return (
            None,
            None,
            Response(
                {
                    "detail": "Only a manager can change announcements."
                    if manage
                    else "You do not have access to this."
                },
                status=status.HTTP_403_FORBIDDEN,
            ),
        )
    return kind, obj, None


def _settings_row(kind: str, obj) -> AnnouncementSettings:
    field = "target_lab" if kind == "lab" else "target_department"
    row = AnnouncementSettings.objects.filter(**{field: obj}).first()
    return row or AnnouncementSettings(**{field: obj})


def _settings_payload(row: AnnouncementSettings) -> dict:
    out = {name: getattr(row, name) for name in _SETTINGS_FIELDS}
    out["min_award"] = float(row.min_award) if row.min_award is not None else None
    out["activated_at"] = row.activated_at
    return out


def _bindings(kind: str, obj) -> list:
    if kind == "lab":
        return resolve.all_bindings_for_lab(obj)
    return resolve.bindings_for_department(obj)


def _channel_names(bindings) -> dict[str, str]:
    names = {}
    for binding in bindings:
        for route in resolve.routes_for_binding(binding).values():
            if route.channel_name:
                names[route.channel_id] = route.channel_name
    return names


def _discord_links(announcement: Announcement, names: dict[str, str]) -> list[dict]:
    out = []
    for post in (
        announcement.posts.filter(deleted_at__isnull=True)
        .exclude(thread_id="")
        .select_related("binding__guild")
    ):
        guild = post.binding.guild
        out.append(
            {
                "guild_id": guild.guild_id,
                "guild_name": guild.guild_name_cache,
                "channel_id": post.channel_id,
                "channel_name": names.get(post.channel_id, ""),
                "thread_url": f"https://discord.com/channels/{guild.guild_id}/{post.thread_id}",
            }
        )
    return out


def _announced_row(ann: Announcement, names: dict[str, str]) -> dict:
    write_up = ann.write_up or {}
    posts = list(ann.posts.all())
    updated = sorted(
        {
            entry.get("on")
            for p in posts
            for entry in (p.update_log or [])
            if entry.get("on")
        }
    )
    posted = min((p.posted_at for p in posts if p.posted_at), default=ann.created_at)
    return {
        "id": str(ann.id),
        "content_id": str(ann.content_id) if ann.content_id else None,
        "category": ann.category,
        "label": ann.label,
        "label_text": Announcement.Label(ann.label).label if ann.label else "",
        "state": ann.state,
        "origin": ann.origin,
        "title": (ann.snapshot or {}).get("title", ""),
        "url": (ann.snapshot or {}).get("url", ""),
        "funder": (ann.snapshot or {}).get("funder", ""),
        "posted_at": posted,
        "updated_on": updated,
        "deadline": (ann.facts or {}).get("deadline", ""),
        "checks": ann.checks or [],
        "write_up": {
            "headline": write_up.get("headline", ""),
            "why_it_matters": write_up.get("why_it_matters", ""),
            "who_should_look": [
                {"name": looker_label(p, bold=False), "why": p.get("why", "")}
                for p in write_up.get("who_should_look") or []
            ],
            "next_step": write_up.get("next_step", ""),
        },
        "interested": len(followers(ann)),
        "discord": _discord_links(ann, names),
        "dept_reasons": (ann.alignment or {}).get("dept_reasons") or [],
    }


class AnnouncementsView(APIView):
    capabilities = {"GET": caps.MEMBERSHIP}

    permission_classes = [IsAuthenticated]

    def get(self, request):
        kind, obj, error = _target(request)
        if error is not None:
            return error
        row = _settings_row(kind, obj)
        bindings = _bindings(kind, obj)
        names = _channel_names(bindings)
        since = timezone.now() - timedelta(days=LIST_DAYS)
        field = "target_lab" if kind == "lab" else "target_department"
        rows = Announcement.objects.filter(**{field: obj}, created_at__gte=since)
        announced = [
            _announced_row(a, names)
            for a in rows.filter(
                state__in=[Announcement.State.POSTED, Announcement.State.CLOSED]
            ).prefetch_related("posts")[:LIST_MAX]
        ]
        held = [
            {
                "id": str(a.id),
                "content_id": str(a.content_id) if a.content_id else None,
                "category": a.category,
                "title": (a.snapshot or {}).get("title", ""),
                "url": (a.snapshot or {}).get("url", ""),
                "reason": a.skip_reason,
                "created_at": a.created_at,
            }
            for a in rows.filter(state=Announcement.State.SKIPPED)[:LIST_MAX]
        ]
        manage = caps.has_capability(request.user, obj, caps.ANNOUNCEMENTS_MANAGE)
        return Response(
            {
                "settings": _settings_payload(row),
                "can_manage": manage,
                "feature_on": announce.enabled(),
                "announced": announced,
                "held": held,
                "closing_soon": _closing_soon(kind, obj, row, names),
                "servers": [_server(b) for b in bindings],
            }
        )


#: Where a web link into Discord can be opened from.
LINK_SURFACES = {"announced", "closing_soon", "card", "search", "dept_page"}


class LinkClickView(APIView):
    """Count one opened thread link (Discord itself reports no link clicks)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from tools.delivery.models import AnnouncementPost, AnnouncementReaction

        url = str(request.data.get("thread_url") or "")
        surface = str(request.data.get("surface") or "")
        thread_id = url.rstrip("/").rsplit("/", 1)[-1]
        if surface not in LINK_SURFACES or not thread_id.isdigit():
            return Response(status=status.HTTP_204_NO_CONTENT)
        post = (
            AnnouncementPost.objects.filter(thread_id=thread_id)
            .select_related(
                "announcement__target_lab", "announcement__target_department"
            )
            .first()
        )
        if post is not None:
            ann = post.announcement
            allowed = (
                user_has_lab_access(request.user, ann.target_lab)
                if ann.target_lab_id
                else user_has_department_access(request.user, ann.target_department)
            )
            if allowed:
                AnnouncementReaction.objects.create(
                    announcement=ann,
                    user=request.user,
                    kind=AnnouncementReaction.Kind.LINK_CLICK,
                    reason=surface,
                )
        return Response(status=status.HTTP_204_NO_CONTENT)


class DepartmentOpportunitiesView(APIView):
    """Department-level calls on the department's slate (plan "What a department
    sees"). Nothing else is listed: no reason, no department item."""

    capabilities = {"GET": caps.MEMBERSHIP}

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.query_params.get("department"):
            return Response(
                {"detail": "Pass ?department=<id>."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        kind, obj, error = _target(request)
        if error is not None:
            return error
        from tools.delivery import dept_level, lab_fit, usability

        today = timezone.localdate()
        row = _settings_row(kind, obj)
        target = announce.Target(kind, obj, row)
        names = _channel_names(_bindings(kind, obj))
        # The slate's department-level items, plus everything already announced
        # to the department (a manager can announce a search result off-slate).
        items_by_id = {
            r.content_id: r.content
            for r in announce.slate_rows(target, today)
            if dept_level.reasons(r.content.metadata)
        }
        announced = {
            a.content_id: a
            for a in Announcement.objects.filter(
                target_department=obj, content__isnull=False
            )
            .select_related("content")
            .prefetch_related("posts")
        }
        for content_id, ann in announced.items():
            if ann.state == Announcement.State.POSTED:
                items_by_id.setdefault(content_id, ann.content)
        reader = usability.reader_for_department(
            obj, min_award=announce._min_award(target)
        )
        members = announce._members(target)
        counts = usability.fellowship_counts(
            [m.id for m in members],
            [i for i in items_by_id.values() if i.type == "fellowship"],
            today,
        )
        labs = lab_fit.candidates(obj)
        items = []
        for item in items_by_id.values():
            if not dept_level.reasons(item.metadata):
                continue
            ann = announced.get(item.id)
            fit = lab_fit.rank(item, labs)
            checks = usability.assess(
                item,
                replace(
                    reader,
                    suited=tuple(lab["name"] for lab in fit),
                    suited_are_labs=True,
                    fellowship_counts=counts.get(str(item.id)),
                ),
                today,
            )
            facts = announce_facts.facts_for(item, today)
            blocked = usability.blocking(checks)
            items.append(
                {
                    "content_id": str(item.id),
                    "category": item.type,
                    "title": announce_facts.item_title(item),
                    "url": announce_facts.item_url(item),
                    "funder": announce_facts.item_host(item),
                    "deadline": facts.get("deadline", ""),
                    "reasons": [
                        rs.as_dict() for rs in dept_level.reasons(item.metadata)
                    ],
                    "labs": [{"name": lab["name"], "why": lab["why"]} for lab in fit],
                    "checks": [c.as_dict() for c in checks],
                    "held": blocked.label if blocked else "",
                    "announced": bool(
                        ann and ann.state == Announcement.State.POSTED
                    ),
                    "discord": _discord_links(ann, names) if ann else [],
                }
            )
        # Announced first, then what could still be, then what Mylo held back.
        items.sort(
            key=lambda i: (bool(i["held"]), not i["announced"], i["deadline"] or "9")
        )
        return Response(
            {
                "department": {"id": str(obj.pk), "name": obj.name},
                "announcements_on": row.enabled,
                "items": items,
            }
        )


def _closing_soon(kind, obj, row, names) -> list[dict]:
    today = timezone.localdate()
    target = announce.Target(kind, obj, row)
    items = announce.list_items(target, today)
    field = "target_lab" if kind == "lab" else "target_department"
    by_content = {
        str(a.content_id): a
        for a in Announcement.objects.filter(
            **{field: obj},
            content__in=[i.id for i in items],
            state=Announcement.State.POSTED,
        )
    }
    out = []
    for r in announce_facts.closing_soon(items, today):
        ann = by_content.get(r.content_id)
        out.append(
            {
                "content_id": r.content_id,
                "category": r.kind,
                "title": r.title,
                "url": r.url,
                "funder": r.funder,
                "due": r.due,
                "days": r.days,
                "discord": _discord_links(ann, names) if ann else [],
            }
        )
    return out


def _server(binding) -> dict:
    health = resolve.binding_health(binding)
    return {
        **health,
        "target_kind": binding.target_kind,
        "announcement_routes": {
            p: health["routes"][p]
            for p in ("grants", "fellowships", "conferences")
            if p in health["routes"]
        },
    }


class AnnouncementSettingsView(APIView):
    capabilities = {"GET": caps.MEMBERSHIP, "PUT": caps.ANNOUNCEMENTS_MANAGE}

    permission_classes = [IsAuthenticated]

    def get(self, request):
        kind, obj, error = _target(request)
        if error is not None:
            return error
        return Response(_settings_payload(_settings_row(kind, obj)))

    def put(self, request):
        kind, obj, error = _target(request, manage=True)
        if error is not None:
            return error
        row = _settings_row(kind, obj)
        data = request.data or {}
        errors = {}
        for name in _SETTINGS_FIELDS:
            if name not in data:
                continue
            value = data[name]
            if name in ("daily_cap", "activation_seed"):
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    errors[name] = "Must be a whole number."
                    continue
                if name == "daily_cap" and value < -1:
                    errors[name] = "Use -1 for no limit."
                    continue
                if name == "activation_seed" and not 0 <= value <= 20:
                    errors[name] = "Between 0 and 20."
                    continue
            elif name == "default_nudge":
                if value not in AnnouncementSettings.Nudge.values:
                    errors[name] = "Unknown choice."
                    continue
            elif name == "min_award":
                if value in ("", None):
                    value = None
                else:
                    try:
                        value = float(value)
                    except (TypeError, ValueError):
                        errors[name] = "Must be a number."
                        continue
            else:
                value = bool(value)
            setattr(row, name, value)
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        first = row.enabled and row.activated_at is None
        if first:
            row.activated_at = timezone.now()
        row.updated_by = request.user
        row.save()
        from apps.accounts.services import record_audit_event

        record_audit_event(
            actor=request.user,
            action="announcements.settings_changed",
            target_type=kind,
            target_id=str(obj.pk),
            metadata={k: str(data[k]) for k in data if k in _SETTINGS_FIELDS},
        )
        activating = False
        if first and announce.enabled():
            from tools.delivery.tasks import enqueue_activation

            activating = enqueue_activation(kind, obj.pk)
        return Response({**_settings_payload(row), "activating": activating})


class AnnouncementTestView(APIView):
    """A clearly labelled test thread in each of the target's forums."""

    capabilities = {"POST": caps.ANNOUNCEMENTS_MANAGE}

    permission_classes = [IsAuthenticated]

    def post(self, request):
        kind, obj, error = _target(request, manage=True)
        if error is not None:
            return error
        from apps.integrations.services import discord_api

        results = []
        for binding in _bindings(kind, obj):
            # One test thread per forum: a department's kinds share one.
            forums: dict[str, list] = {}
            for purpose, route in resolve.routes_for_binding(binding).items():
                if purpose in ("grants", "fellowships", "conferences"):
                    forums.setdefault(route.channel_id, []).append((purpose, route))
            for channel_id, entries in forums.items():
                order = ("grants", "fellowships", "conferences")
                purposes = sorted(
                    (purpose for purpose, _route in entries), key=order.index
                )
                route = entries[0][1]
                what = (
                    purposes[0]
                    if len(purposes) == 1
                    else ", ".join(purposes[:-1]) + " and " + purposes[-1]
                )
                try:
                    resp = discord_api.create_forum_thread(
                        channel_id,
                        name=f"[Test] Mylo announcements for {obj.name}",
                        embed={
                            "title": "This is a test post",
                            "description": (
                                f"New {what} for **{obj.name}** will appear in this "
                                "forum, one thread each. You can delete this thread."
                            ),
                            "color": 0x5E7A3E,
                        },
                    )
                    ok = resp.status in (200, 201)
                except discord_api.DiscordHTTPError:
                    ok = False
                results.append(
                    {
                        "guild_name": binding.guild.guild_name_cache,
                        "purpose": purposes[0],
                        "channel_id": channel_id,
                        "channel_name": route.channel_name,
                        "ok": ok,
                    }
                )
        return Response({"results": results})


class AnnouncementCreateChannelsView(APIView):
    """ "Create them for me" for one binding, from the web."""

    capabilities = {"POST": caps.SERVERS_MANAGE}

    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            binding = resolve.get_binding(int(request.query_params.get("binding", "")))
        except (TypeError, ValueError):
            binding = None
        if binding is None or not resolve.web_user_can_manage_binding(
            request.user, binding
        ):
            return Response({"detail": "Not found."}, status=404)
        from tools.delivery import announcement_setup

        ok, message = announcement_setup.create_forums(binding, actor=request.user)
        return Response(
            {"ok": ok, "message": message, **announcement_setup.state(binding)},
            status=200 if ok else 409,
        )
