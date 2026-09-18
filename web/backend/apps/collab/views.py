"""The collaboration API: slot feedback (CN-03), consent and preview (CN-04)."""

from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.content.models import ContentItem

from . import consent
from .models import Audience, CollaborationSetting, OpenTo, SlotFeedback
from .preview import preview


class SlotFeedbackInput(serializers.Serializer):
    kind = serializers.ChoiceField(choices=SlotFeedback.Kind.choices)
    slot_text = serializers.CharField(max_length=200, required=False, allow_blank=True)
    note = serializers.CharField(max_length=300, required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["kind"] == SlotFeedback.Kind.MISSED_ONE and not attrs.get("note"):
            raise serializers.ValidationError({"note": "Say what the call asks for."})
        if attrs["kind"] != SlotFeedback.Kind.MISSED_ONE and not attrs.get("slot_text"):
            raise serializers.ValidationError({"slot_text": "Name the slot."})
        return attrs


class SlotFeedbackView(APIView):
    """``POST /api/collab/calls/<content_id>/slot-feedback/`` — one correction.

    Append-only: a change of mind is a second row. Any signed-in reader may say
    a call's slot is wrong; the labels are what plan CN-08 measures slot quality
    with, and the call itself is public.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, content_id):
        call = ContentItem.objects.filter(pk=content_id, type="grant").first()
        if call is None:
            return Response(
                {"detail": "No such call."}, status=status.HTTP_404_NOT_FOUND
            )
        payload = SlotFeedbackInput(data=request.data)
        payload.is_valid(raise_exception=True)
        row = SlotFeedback.objects.create(
            user=request.user,
            content=call,
            kind=payload.validated_data["kind"],
            slot_text=payload.validated_data.get("slot_text", ""),
            note=payload.validated_data.get("note", ""),
        )
        return Response(
            {"id": row.pk, "kind": row.kind}, status=status.HTTP_201_CREATED
        )


class CollaborationSettingInput(serializers.Serializer):
    open = serializers.BooleanField()
    audience = serializers.ChoiceField(choices=Audience.choices)
    open_to = serializers.ListField(
        child=serializers.ChoiceField(choices=OpenTo.choices), required=False
    )
    renew = serializers.BooleanField(required=False, default=False)


def _setting_payload(user) -> dict:
    setting = CollaborationSetting.objects.filter(user=user).first()
    place = consent.place_of(user)
    affiliation = getattr(user, "verified_affiliation", None) if place else None
    return {
        "open": bool(setting and setting.is_open()),
        "audience": setting.audience if setting else Audience.INSTITUTION,
        "open_to": list(setting.open_to) if setting else [],
        "expires_at": (
            setting.expires_at.isoformat()
            if setting and setting.is_open() and setting.expires_at
            else None
        ),
        "verified": place is not None,
        "institution": affiliation.institution if affiliation else "",
        "country": affiliation.country if affiliation else "",
        "allowed_audiences": consent.allowed_audiences(place),
    }


class CollaborationSettingView(APIView):
    """``GET`` / ``PUT /api/collab/settings/`` — the person's own setting.

    Off unless they turn it on; turning it on starts a fresh six-month period.
    The response never includes how often, or by whom, they were found.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(_setting_payload(request.user))

    def put(self, request):
        payload = CollaborationSettingInput(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        try:
            consent.update(
                request.user,
                open=data["open"],
                audience=data["audience"],
                open_to=data.get("open_to") or [],
                renew=data.get("renew", False),
            )
        except consent.ConsentRefused as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_setting_payload(request.user))


class CollaborationPreviewView(APIView):
    """``GET /api/collab/preview/`` — exactly what a seeker would see about you."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(preview(request.user))
