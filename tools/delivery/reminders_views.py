"""Reminder API (R9): create / list / cancel personal and lab reminders.

Backs the Saves-page "Set reminder" composer and the management list. Authorization
mirrors §9: a personal reminder needs only auth (opportunities are globally visible);
a lab reminder needs ``user_can_edit_lab_profile`` (a PI/lead or owner/admin) and its
mentions ``user_has_lab_access`` (both enforced inside ``create_subscription``). The
addressable deadlines the composer
picks from come from the item's ``deadlines[]`` (R0) — a rolling/unknown deadline has
no date and is rejected here as it is in the service.
"""

from __future__ import annotations

from datetime import date

from apps.accounts import capabilities as caps
from apps.accounts.models import Lab, LabMembership
from apps.accounts.permissions import (
    user_can_edit_lab_profile,
    user_has_lab_access,
)
from apps.core.people import display_name
from apps.integrations.services import resolve as discord_resolve
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from tools.delivery import reminders_discord
from tools.delivery.models import (
    LabReminderPolicy,
    ReminderMention,
    ReminderOffset,
    ReminderSubscription,
    SavedOpportunity,
    default_reminder_offsets,
)
from tools.delivery.reminder_access import lab_reminder_access, personal_reminder_access
from tools.delivery.reminders import (
    ReminderAccessError,
    ReminderError,
    create_or_update_subscription,
    offset_fire_date,
    set_state,
    update_subscription,
)
from tools.delivery.reminders_tick import DEFAULT_TIMEZONE
from tools.retrieval.models import ContentDeadline, ContentItem

User = get_user_model()

_OPPORTUNITY_TYPES = [
    ContentItem.Type.GRANT,
    ContentItem.Type.CONFERENCE,
    ContentItem.Type.FELLOWSHIP,
]
_VALID_UNITS = {c for c, _ in ReminderOffset.Unit.choices}


class ReminderSerializer(serializers.Serializer):
    """Read shape for one reminder (composer + management page).

    The management page needs to answer "when will this actually reach me?", so each
    offset carries the date it resolves to — computed with the very
    :func:`offset_fire_date` the tick uses, so what the page promises and what gets
    delivered cannot drift. ``next_fire_date`` is the soonest of those that is still
    ahead (respecting a snooze), and ``send_hour_local``/``timezone`` say *when* on
    that day — a real hour for a lab, and ``null`` for a personal reminder, which
    rides the daily run rather than a configured hour. Reporting an hour we do not
    honour would be worse than reporting none.
    """

    id = serializers.UUIDField(read_only=True)
    scope = serializers.SerializerMethodField()
    lab_slug = serializers.SerializerMethodField()
    lab_name = serializers.SerializerMethodField()
    content_id = serializers.SerializerMethodField()
    deadline_kind = serializers.CharField()
    # Which round of that kind — "" for a single-round deadline. ``round_label``
    # is the source's own wording, so a client can say "round 2" without owning
    # a vocabulary for something 287 distinct free-text values appear in.
    deadline_round_key = serializers.CharField()
    round_label = serializers.CharField()
    area = serializers.CharField()
    title = serializers.CharField()
    url = serializers.CharField()
    due_date = serializers.DateField()
    confidence = serializers.CharField()
    state = serializers.CharField()
    snoozed_until = serializers.DateField()
    channel_id_override = serializers.CharField()
    has_unlinked_targets = serializers.BooleanField()
    offsets = serializers.SerializerMethodField()
    next_fire_date = serializers.SerializerMethodField()
    send_hour_local = serializers.SerializerMethodField()
    timezone = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()
    mentions = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def get_scope(self, sub: ReminderSubscription) -> str:
        return sub.target_type

    def get_lab_slug(self, sub: ReminderSubscription) -> str | None:
        return sub.target_lab.slug if sub.target_lab_id else None

    def get_lab_name(self, sub: ReminderSubscription) -> str | None:
        return sub.target_lab.name if sub.target_lab_id else None

    def get_content_id(self, sub: ReminderSubscription) -> str | None:
        return str(sub.content_id) if sub.content_id else None

    def get_offsets(self, sub: ReminderSubscription) -> list[dict]:
        return [
            {
                "amount": o.amount,
                "unit": o.unit,
                "fire_date": (
                    offset_fire_date(sub.due_date, o.amount, o.unit).isoformat()
                    if sub.due_date
                    else None
                ),
            }
            for o in sub.offsets.all()
        ]

    def get_next_fire_date(self, sub: ReminderSubscription) -> str | None:
        if sub.due_date is None or sub.state != ReminderSubscription.State.ACTIVE:
            return None
        today = timezone.localdate()
        floor = max(today, sub.snoozed_until or today)
        dates = [
            offset_fire_date(sub.due_date, o.amount, o.unit) for o in sub.offsets.all()
        ]
        upcoming = [d for d in dates if d >= floor]
        return min(upcoming).isoformat() if upcoming else None

    def get_send_hour_local(self, sub: ReminderSubscription) -> int | None:
        return sub.target_lab.send_hour_local if sub.target_lab_id else None

    def get_timezone(self, sub: ReminderSubscription) -> str:
        if sub.target_lab_id:
            return sub.target_lab.timezone or DEFAULT_TIMEZONE
        return DEFAULT_TIMEZONE

    def get_can_manage(self, sub: ReminderSubscription) -> bool:
        request = self.context.get("request")
        return bool(request) and _can_manage(request.user, sub)

    def get_mentions(self, sub: ReminderSubscription) -> list[dict]:
        """Every ping target, whichever of the three kinds it is.

        ``username`` stays for a Mycelium-user target (an existing client reads
        it) and is ``""`` for a role, an @everyone, or a guild member with no
        Mycelium account — none of which has one.
        """
        return [
            {
                "kind": m.kind,
                "id": m.discord_id,
                "username": (
                    m.member.get_username() if m.member_id is not None else ""
                ),
                "name": (
                    display_name(m.member) if m.member_id is not None else m.label
                ),
            }
            for m in sub.mentions.select_related("member").all()
        ]


def _snapshot_for(item: ContentItem) -> tuple[str, str, str]:
    """(area, title, url) snapshot for a content item — mirrors the save snapshot."""
    meta = item.metadata or {}
    if item.type == ContentItem.Type.GRANT:
        return (
            SavedOpportunity.Area.GRANT,
            meta.get("title") or "Untitled grant",
            meta.get("website") or item.source_url or "",
        )
    if item.type == ContentItem.Type.FELLOWSHIP:
        return (
            SavedOpportunity.Area.FELLOWSHIP,
            meta.get("title") or "Untitled fellowship",
            meta.get("external_url") or meta.get("website") or item.source_url or "",
        )
    return (
        SavedOpportunity.Area.CONFERENCE,
        meta.get("name") or "Untitled conference",
        meta.get("website") or item.source_url or "",
    )


def _parse_offsets(raw) -> list[tuple[int, str]]:
    """Validate ``[{amount, unit}]`` into ``[(amount, unit)]``. Raises on bad input."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ReminderError("offsets must be a list of {amount, unit}")
    out: list[tuple[int, str]] = []
    for entry in raw:
        try:
            amount = int(entry["amount"])
            unit = str(entry["unit"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ReminderError(
                "each offset needs an integer amount and a unit"
            ) from exc
        if amount < 1:
            raise ReminderError("offset amount must be at least 1")
        if unit not in _VALID_UNITS:
            raise ReminderError(f"unit must be one of {sorted(_VALID_UNITS)}")
        out.append((amount, unit))
    return out


def _default_offsets(lab: Lab | None) -> list[tuple[int, str]]:
    raw = default_reminder_offsets()
    if lab is not None:
        policy = LabReminderPolicy.objects.filter(lab=lab).first()
        if policy and policy.default_offsets:
            raw = policy.default_offsets
    return [(o["amount"], o["unit"]) for o in raw]


def _resolve_mentions(raw, lab) -> list[dict]:
    """Validate requested mention targets against the lab's own guild.

    Accepts the wire shape ``[{"kind": "user"|"role"|"everyone", "id"?,
    "name"?}]``, and — for compatibility with the original contract — a bare
    list of Mycelium usernames, which still means "these lab members".

    The guard that matters is the guild check. Mentioning by raw snowflake is
    what makes tagging a collaborator who has no Mycelium account possible at
    all, and it is also exactly how Mylo could be pointed at an unrelated
    server. So every id is checked for membership of *this lab's* guild before
    it is stored: roles against the guild's role list, users against its member
    list. An id that is not in either is refused rather than quietly dropped —
    silently ignoring a requested ping produces an alert that reaches fewer
    people than the person who set it believes.

    Returns plain dicts; the service turns them into ``ReminderMention`` rows.
    """
    if not raw:
        return []

    # The original shape: a list of Mycelium usernames meaning lab members.
    if all(isinstance(entry, str) for entry in raw):
        users = list(User.objects.filter(username__in=[str(u) for u in raw]))
        return [{"kind": ReminderMention.Kind.USER, "member": u} for u in users]

    kinds = ReminderMention.Kind
    wanted = [entry for entry in raw if isinstance(entry, dict)]
    needs_roles = any(entry.get("kind") == kinds.ROLE for entry in wanted)
    needs_members = any(
        entry.get("kind") == kinds.USER and entry.get("id") for entry in wanted
    )

    role_ids: set[str] = set()
    member_names: dict[str, str] = {}
    if (needs_roles or needs_members) and lab is not None:
        link = discord_resolve.primary_server_for_lab(lab, "deadlines")
        if not (link and link.guild_id):
            raise ReminderError("This lab has no Discord server linked.")
        if needs_roles:
            role_ids = {
                r["id"] for r in reminders_discord.list_guild_roles(link.guild_id)
            }
        if needs_members:
            member_names = {
                m["id"]: m["name"]
                for m in reminders_discord.list_guild_members(link.guild_id)
            }

    out: list[dict] = []
    for entry in wanted:
        kind = entry.get("kind") or kinds.USER
        if kind == kinds.EVERYONE:
            out.append({"kind": kinds.EVERYONE})
            continue
        target_id = str(entry.get("id") or "")
        if kind == kinds.ROLE:
            if target_id not in role_ids:
                raise ReminderError("That role isn't in this lab's Discord server.")
            out.append(
                {
                    "kind": kinds.ROLE,
                    "discord_id": target_id,
                    "display_name": str(entry.get("name") or ""),
                }
            )
            continue
        # A user target is either a Mycelium member (by username) or a guild
        # member (by snowflake).
        username = entry.get("username")
        if username:
            member = User.objects.filter(username=str(username)).first()
            if member is None:
                raise ReminderError("No such member.")
            out.append({"kind": kinds.USER, "member": member})
            continue
        if target_id not in member_names:
            raise ReminderError("That person isn't in this lab's Discord server.")
        out.append(
            {
                "kind": kinds.USER,
                "discord_id": target_id,
                "display_name": str(entry.get("name") or member_names[target_id]),
            }
        )
    return out


class ReminderListCreateView(APIView):
    """GET the user's reminders; POST a new personal or lab reminder."""

    #: When a lab is named: reading lists only labs the caller belongs to, and a
    #: lab reminder takes org.profile.edit (enforced in ``create_subscription``).
    capabilities = {"GET": caps.MEMBERSHIP, "POST": caps.PROFILE_EDIT}

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Personal reminders + lab reminders for labs the user can access (§9).
        lab_ids = LabMembership.objects.filter(user=request.user).values_list(
            "lab_id", flat=True
        )
        subs = (
            ReminderSubscription.objects.filter(
                target_user=request.user
            )
            | ReminderSubscription.objects.filter(target_lab_id__in=list(lab_ids))
        ).select_related("target_lab").prefetch_related("offsets", "mentions__member")
        # `?state=active,snoozed` narrows the management page's tabs server-side; the
        # unfiltered list stays the default so the composer keeps its current shape.
        wanted = [s for s in (request.GET.get("state") or "").split(",") if s]
        if wanted:
            subs = subs.filter(state__in=wanted)
        if request.GET.get("lab"):
            subs = subs.filter(target_lab__slug=request.GET["lab"])
        subs = subs.order_by("due_date", "created_at")
        return Response(
            {
                "items": ReminderSerializer(
                    subs, many=True, context={"request": request}
                ).data
            }
        )

    def post(self, request):
        data = request.data
        content_id = data.get("content_id")
        deadline_kind = data.get("deadline_kind")
        scope = (data.get("scope") or "personal").lower()
        if not content_id or not deadline_kind:
            return _bad("content_id and deadline_kind are required.")

        item = ContentItem.objects.filter(
            id=content_id, type__in=_OPPORTUNITY_TYPES
        ).first()
        if item is None:
            return _bad("No such grant, conference, or fellowship.", 404)
        # ``deadline_round_key`` selects *which* round of that kind, for an item
        # carrying several (a conference's second paper deadline, a workshop
        # track). Absent, it means "" — the single-round key every grant,
        # fellowship, and conference event row carries — so an older client that
        # never sends it keeps working unchanged.
        round_key = str(data.get("deadline_round_key") or "")
        deadline = ContentDeadline.objects.filter(
            content=item, kind=deadline_kind, round_key=round_key
        ).first()
        if deadline is None:
            return _bad("That item has no such deadline.", 404)
        if deadline.due_date is None:
            return _bad(
                "This deadline has no date (rolling/unknown) and can't be reminded."
            )

        target_user = None
        target_lab = None
        mentions = []
        channel_override = ""
        try:
            offsets = _parse_offsets(data.get("offsets"))
            if scope == "lab":
                lab = Lab.objects.filter(slug=data.get("lab_slug")).first()
                if lab is None:
                    return _bad("No such lab.", 404)
                if not user_has_lab_access(request.user, lab):
                    return _bad("You don't have access to that lab.", 403)
                target_lab = lab
                mentions = _resolve_mentions(data.get("mentions"), lab)
                channel_override = _lab_channel_override(
                    lab, data.get("channel_id_override")
                )
                offsets = offsets or _default_offsets(lab)
            else:
                target_user = request.user
                offsets = offsets or _default_offsets(None)

            area, title, url = _snapshot_for(item)
            sub, created = create_or_update_subscription(
                target_user=target_user,
                target_lab=target_lab,
                content=item,
                deadline_kind=deadline_kind,
                deadline_round_key=deadline.round_key,
                area=area,
                title=title,
                round_label=deadline.round_label,
                url=url,
                due_date=deadline.due_date,
                confidence=deadline.confidence,
                offsets=offsets,
                mentions=mentions,
                channel_id_override=channel_override,
                created_by=request.user,
            )
        except ReminderAccessError as exc:
            # 403, not 400: the request is well-formed, the capability is missing.
            # The reason slug lets the client point at the exact fix (plan vs link).
            return Response(
                {"detail": str(exc), "reason": exc.reason, **exc.access.as_dict()},
                status=status.HTTP_403_FORBIDDEN,
            )
        except ReminderError as exc:
            return _bad(str(exc))

        # 201 only for a genuinely new row. Setting a reminder on an item that already
        # has one for the same deadline reconfigures it (see
        # ``create_or_update_subscription``) and answers 200 — the request succeeded,
        # nothing was created.
        return Response(
            ReminderSerializer(sub, context={"request": request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ReminderDetailView(APIView):
    """Edit or stop one reminder the user owns (personal) or manages (lab).

    ``PATCH`` is the manage page's write path: lead times, channel, mentions, snooze,
    and reinstating a cancelled reminder. Every field is optional and absence means
    "leave alone", so the page can send one change at a time.

    ``DELETE`` is a **soft** cancel: the row is marked ``CANCELLED`` rather than
    destroyed, so the tick stops seeing it while "why did this stop reminding me?"
    keeps an answer, and the fired ledger it sealed stays intact. ``/mylo cancel``
    does exactly the same thing, so the two surfaces cannot drift. ``?purge=1``
    destroys the row for real — the page's way to clear out finished clutter, and the
    only path that loses history, which is why it is opt-in.

    Neither is gated on the reminder entitlement, unlike create. Delivery is already
    gated at send time, so a lapsed plan sends nothing regardless; locking someone out
    of *stopping* or *snoozing* reminders they already own would only trap them.
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        sub = ReminderSubscription.objects.filter(pk=pk).first()
        if sub is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        denied = _authorize(request.user, sub, "edit")
        if denied is not None:
            return denied

        data = request.data
        try:
            offsets = (
                _parse_offsets(data["offsets"]) if "offsets" in data else None
            )
            if offsets is not None and not offsets:
                raise ReminderError("at least one reminder time is required")
            mentions = None
            if "mentions" in data:
                if sub.target_lab_id is None:
                    raise ReminderError("a personal reminder cannot mention anyone")
                # Validated against *this* reminder's lab, so a PATCH can never
                # widen the blast radius past the guild the alert posts to.
                mentions = _resolve_mentions(data["mentions"], sub.target_lab)
            snoozed_until, clear_snooze = _parse_snooze(data, sub)

            channel = data.get("channel_id_override")
            if channel is not None and sub.target_lab_id is None:
                raise ReminderError("a personal reminder has no channel")
            if channel is not None:
                channel = _lab_channel_override(sub.target_lab, channel)

            reactivate = False
            if "state" in data:
                state = str(data["state"])
                if state == ReminderSubscription.State.CANCELLED:
                    set_state(sub, ReminderSubscription.State.CANCELLED)
                elif state == ReminderSubscription.State.ACTIVE:
                    reactivate = True
                    if sub.due_date is None or sub.due_date < timezone.localdate():
                        raise ReminderError(
                            "this deadline has passed, so the reminder can't be "
                            "restarted."
                        )
                else:
                    raise ReminderError("state must be active or cancelled")

            update_subscription(
                sub,
                offsets=offsets,
                mentions=mentions,
                channel_id_override=(
                    str(channel) if channel is not None else None
                ),
                snoozed_until=snoozed_until,
                clear_snooze=clear_snooze,
                reactivate=reactivate,
            )
        except ReminderError as exc:
            return _bad(str(exc))

        sub.refresh_from_db()
        return Response(ReminderSerializer(sub, context={"request": request}).data)

    def delete(self, request, pk):
        sub = ReminderSubscription.objects.filter(pk=pk).first()
        if sub is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        denied = _authorize(request.user, sub, "remove")
        if denied is not None:
            return denied
        if request.GET.get("purge") in ("1", "true", "yes"):
            sub.delete()
        else:
            set_state(sub, ReminderSubscription.State.CANCELLED)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReminderAccessView(APIView):
    """``GET /api/reminders/access/[?lab=<slug>]`` — may I set a reminder here?

    The same :mod:`tools.delivery.reminder_access` answer the create path enforces
    with, so the button the user sees and the rule the server applies come from one
    computation. Without ``lab`` it answers for the caller personally (DM delivery);
    with it, for the lab (channel delivery) — and, since only a manager may create a
    lab reminder at all, a non-manager is answered "not allowed" rather than being
    told about the lab's plan.
    """

    #: With ``?lab=``: may this caller set a lab reminder there.
    capabilities = {"GET": caps.PROFILE_EDIT}

    permission_classes = [IsAuthenticated]

    def get(self, request):
        slug = request.GET.get("lab", "")
        if not slug:
            return Response(personal_reminder_access(request.user).as_dict())

        lab = Lab.objects.filter(slug=slug).first()
        if lab is None:
            return _bad("No such lab.", 404)
        if not user_can_edit_lab_profile(request.user, lab):
            return Response(
                {
                    "allowed": False,
                    "plan_ok": False,
                    "discord_ok": False,
                    "reason": "permission",
                    "detail": "Only a lab PI or admin can set a lab reminder.",
                }
            )
        return Response(lab_reminder_access(lab).as_dict())


class LabMentionTargetsView(APIView):
    """Who a lab alert may @-mention: the guild's roles, its members, @everyone.

    Manager-gated on the same authority as creating a lab reminder — a mention
    reaches a whole server, so offering the roster is itself a management view.

    Degrades the way the channel picker does: an unlinked guild, a missing
    privileged intent, or a Discord hiccup answers HTTP 200 with empty lists and
    a ``detail`` saying so, rather than a 500 that leaves the composer with no
    explanation. ``everyone_allowed`` is always true for a manager — whether the
    bot actually holds Mention Everyone in that guild is only knowable by trying,
    and Discord's failure mode is a message that arrives without the ping, which
    is a far better outcome than refusing to offer the option.
    """

    capabilities = {"GET": caps.PROFILE_EDIT}

    permission_classes = [IsAuthenticated]

    def get(self, request):
        lab = Lab.objects.filter(slug=request.GET.get("lab", "")).first()
        if lab is None:
            return _bad("No such lab.", 404)
        if not user_can_edit_lab_profile(request.user, lab):
            return _bad("Only a lab PI or admin can view mention targets.", 403)

        link = discord_resolve.primary_server_for_lab(lab, "deadlines")
        if not (link and link.guild_id):
            return Response(
                {
                    "roles": [],
                    "members": [],
                    "everyone_allowed": True,
                    "detail": (
                        "This lab has no Discord server linked yet, so there is "
                        "nobody to tag."
                    ),
                }
            )

        roles: list[dict] = []
        members: list[dict] = []
        detail = ""
        try:
            roles = reminders_discord.list_guild_roles(link.guild_id)
        except Exception:  # noqa: BLE001 — a live Discord call; never 500 a picker
            detail = "Couldn't read this server's roles right now."
        try:
            members = reminders_discord.list_guild_members(link.guild_id)
        except Exception:  # noqa: BLE001 — usually the Server Members intent
            detail = (
                "Couldn't read this server's member list. Mylo needs the Server "
                "Members intent enabled to tag individual people."
            )
        return Response(
            {
                "roles": roles,
                "members": members,
                "everyone_allowed": True,
                "detail": detail,
            }
        )


class LabReminderChannelsView(APIView):
    """List a lab's postable Discord channels for the reminder channel picker.

    Manager-gated (same authority as creating a lab reminder). Returns the lab's
    ``/setup`` announcement channel as the default so the composer can label it and
    fall back to it when the user picks nothing (which is exactly what
    ``send_lab_channel`` does server-side when ``channel_id_override`` is empty).

    Degrades gracefully: an unlinked guild, an unset default, or a Discord API
    hiccup all return HTTP 200 with an empty ``channels`` list, so the composer can
    still submit a "lab default" reminder without a live channel roster.
    """

    capabilities = {"GET": caps.PROFILE_EDIT}

    permission_classes = [IsAuthenticated]

    def get(self, request):
        lab = Lab.objects.filter(slug=request.GET.get("lab", "")).first()
        if lab is None:
            return _bad("No such lab.", 404)
        if not user_can_edit_lab_profile(request.user, lab):
            return _bad("Only a lab PI or admin can view lab channels.", 403)

        link = discord_resolve.primary_server_for_lab(lab, "deadlines")
        default_id = link.announcement_channel_id if link else ""
        channels: list[dict] = []
        if link and link.guild_id:
            try:
                channels = reminders_discord.list_postable_channels(link.guild_id)
            except Exception:  # noqa: BLE001 — a live Discord call; never 500 the picker
                channels = []
        default_name = next(
            (c["name"] for c in channels if c["id"] == default_id), ""
        )
        return Response(
            {
                "channels": channels,
                "default_channel_id": default_id,
                "default_channel_name": default_name,
            }
        )


def _lab_channel_override(lab: Lab, raw) -> str:
    """A reminder's channel override, checked against the lab's own server.

    Empty means "the lab's default channel". Anything else must be one of the
    channels :class:`LabReminderChannelsView` would offer for this lab — the
    linked server's postable channels, or its announcement channel. Without the
    check a lab manager could aim the bot at any channel id it can reach,
    including another lab's (or another community's) server. When the lab has no
    linked server, or Discord cannot be asked, nothing can be shown to belong to
    the lab, so an override is refused rather than trusted.
    """
    channel = str(raw or "").strip()
    if not channel:
        return ""
    if channel not in reminders_discord.lab_channel_ids(lab):
        raise ReminderError("pick one of your lab's own Discord channels.")
    return channel


def _can_manage(user, sub: ReminderSubscription) -> bool:
    """May ``user`` change this reminder? Owner for personal, PI/admin for a lab.

    The one rule behind both the ``can_manage`` flag the page reads and the checks the
    write endpoints enforce, so a button is never offered that the server refuses.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if sub.target_user_id:
        return sub.target_user_id == user.id
    return user_can_edit_lab_profile(user, sub.target_lab)


def _authorize(user, sub: ReminderSubscription, verb: str) -> Response | None:
    """``None`` when allowed, else the 403 to return."""
    if _can_manage(user, sub):
        return None
    if sub.target_user_id:
        return _bad("Not your reminder.", 403)
    return _bad(f"Only a lab PI or admin can {verb} a lab reminder.", 403)


def _parse_snooze(data, sub: ReminderSubscription) -> tuple[date | None, bool]:
    """``(snoozed_until, clear)`` from a PATCH body.

    An explicit ``null`` clears the snooze (un-snooze is a real action, distinct from
    "don't touch it", which is the key being absent). A date past the deadline is
    rejected rather than silently clamped: on the page the user picked that date, so
    the honest answer is to say it would swallow the reminder — ``/mylo snooze`` clamps
    because there the date is derived from a relative amount, not chosen.
    """
    if "snoozed_until" not in data:
        return None, False
    raw = data["snoozed_until"]
    if raw in (None, ""):
        return None, True
    try:
        parsed = serializers.DateField().to_internal_value(raw)
    except serializers.ValidationError as exc:
        raise ReminderError("snoozed_until must be a YYYY-MM-DD date.") from exc
    if parsed <= timezone.localdate():
        raise ReminderError("pick a snooze date in the future.")
    if sub.due_date and parsed > sub.due_date:
        raise ReminderError(
            "that's after the deadline — the reminder would never fire."
        )
    return parsed, False


def _bad(detail: str, code: int = status.HTTP_400_BAD_REQUEST) -> Response:
    return Response({"detail": detail}, status=code)
