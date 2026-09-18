"""The collaboration API. Plan CN-03 adds one thing: feedback on a call's slots."""

from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.content.models import ContentItem

from .models import SlotFeedback


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
