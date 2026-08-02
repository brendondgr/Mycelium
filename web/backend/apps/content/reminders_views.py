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

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Lab, LabMembership
from apps.accounts.permissions import (
    user_can_edit_lab_profile,
    user_has_lab_access,
)
from apps.core.people import display_name
from apps.integrations.services import resolve as discord_resolve

from . import reminders_discord
from .models import (
    ContentDeadline,
    ContentItem,
    LabReminderPolicy,
    ReminderOffset,
    ReminderSubscription,
    SavedOpportunity,
    default_reminder_offsets,
)
from .reminder_access import lab_reminder_access, personal_reminder_access
from .reminders import (
    ReminderAccessError,
    ReminderError,
    create_or_update_subscription,
    offset_fire_date,
    set_state,
    update_subscription,
)
from .reminders_tick import DEFAULT_TIMEZONE

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
        return [
            {"username": m.member.get_username(), "name": display_name(m.member)}
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


def _resolve_mentions(usernames) -> list:
    if not usernames:
        return []
    users = list(User.objects.filter(username__in=[str(u) for u in usernames]))
    return users


class ReminderListCreateView(APIView):
    """GET the user's reminders; POST a new personal or lab reminder."""

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
        deadline = ContentDeadline.objects.filter(
            content=item, kind=deadline_kind
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
                mentions = _resolve_mentions(data.get("mentions"))
                channel_override = str(data.get("channel_id_override") or "")
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
                area=area,
                title=title,
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
            mentions = (
                _resolve_mentions(data["mentions"]) if "mentions" in data else None
            )
            if mentions is not None:
                if sub.target_lab_id is None:
                    raise ReminderError("a personal reminder cannot mention anyone")
                for member in mentions:
                    if not user_has_lab_access(member, sub.target_lab):
                        raise ReminderError("mention target must be a lab member")
            snoozed_until, clear_snooze = _parse_snooze(data, sub)

            channel = data.get("channel_id_override")
            if channel is not None and sub.target_lab_id is None:
                raise ReminderError("a personal reminder has no channel")

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

    The same :mod:`apps.content.reminder_access` answer the create path enforces
    with, so the button the user sees and the rule the server applies come from one
    computation. Without ``lab`` it answers for the caller personally (DM delivery);
    with it, for the lab (channel delivery) — and, since only a manager may create a
    lab reminder at all, a non-manager is answered "not allowed" rather than being
    told about the lab's plan.
    """

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

    permission_classes = [IsAuthenticated]

    def get(self, request):
        lab = Lab.objects.filter(slug=request.GET.get("lab", "")).first()
        if lab is None:
            return _bad("No such lab.", 404)
        if not user_can_edit_lab_profile(request.user, lab):
            return _bad("Only a lab PI or admin can view lab channels.", 403)

        link = discord_resolve.get_guild_link_for_lab(lab)
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
