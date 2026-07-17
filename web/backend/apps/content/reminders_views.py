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

from django.contrib.auth import get_user_model
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

from .models import (
    ContentDeadline,
    ContentItem,
    LabReminderPolicy,
    ReminderOffset,
    ReminderSubscription,
    SavedOpportunity,
    default_reminder_offsets,
)
from .reminders import ReminderError, create_subscription

User = get_user_model()

_OPPORTUNITY_TYPES = [
    ContentItem.Type.GRANT,
    ContentItem.Type.CONFERENCE,
    ContentItem.Type.FELLOWSHIP,
]
_VALID_UNITS = {c for c, _ in ReminderOffset.Unit.choices}


class ReminderSerializer(serializers.Serializer):
    """Read shape for one reminder (composer + management list)."""

    id = serializers.UUIDField(read_only=True)
    scope = serializers.SerializerMethodField()
    lab_slug = serializers.SerializerMethodField()
    content_id = serializers.SerializerMethodField()
    deadline_kind = serializers.CharField()
    area = serializers.CharField()
    title = serializers.CharField()
    url = serializers.CharField()
    due_date = serializers.DateField()
    confidence = serializers.CharField()
    state = serializers.CharField()
    channel_id_override = serializers.CharField()
    has_unlinked_targets = serializers.BooleanField()
    offsets = serializers.SerializerMethodField()
    mentions = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)

    def get_scope(self, sub: ReminderSubscription) -> str:
        return sub.target_type

    def get_lab_slug(self, sub: ReminderSubscription) -> str | None:
        return sub.target_lab.slug if sub.target_lab_id else None

    def get_content_id(self, sub: ReminderSubscription) -> str | None:
        return str(sub.content_id) if sub.content_id else None

    def get_offsets(self, sub: ReminderSubscription) -> list[dict]:
        return [{"amount": o.amount, "unit": o.unit} for o in sub.offsets.all()]

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
        subs = subs.order_by("due_date", "created_at")
        return Response({"items": ReminderSerializer(subs, many=True).data})

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
            sub = create_subscription(
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
        except ReminderError as exc:
            return _bad(str(exc))

        return Response(
            ReminderSerializer(sub).data, status=status.HTTP_201_CREATED
        )


class ReminderDetailView(APIView):
    """DELETE (cancel + remove) a reminder the user owns or manages."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        sub = ReminderSubscription.objects.filter(pk=pk).first()
        if sub is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if sub.target_user_id:
            if sub.target_user_id != request.user.id:
                return _bad("Not your reminder.", 403)
        elif not user_can_edit_lab_profile(request.user, sub.target_lab):
            return _bad("Only a lab PI or admin can remove a lab reminder.", 403)
        sub.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _bad(detail: str, code: int = status.HTTP_400_BAD_REQUEST) -> Response:
    return Response({"detail": detail}, status=code)
