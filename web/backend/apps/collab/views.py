"""The collaboration API: slot feedback (CN-03), consent and preview (CN-04),
and the search (CN-05)."""

from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.content.models import ContentItem

from . import consent
from .models import (
    Audience,
    CollaborationSetting,
    Lane,
    MatchFeedback,
    OpenTo,
    SearchLog,
    SlotFacet,
    SlotFeedback,
)
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


class SlotInput(serializers.Serializer):
    facet = serializers.ChoiceField(choices=SlotFacet.choices)
    text = serializers.CharField(max_length=90)
    required = serializers.BooleanField(required=False, default=False)


class SearchInput(serializers.Serializer):
    entry = serializers.ChoiceField(choices=["call", "project", "manual"])
    content_id = serializers.UUIDField(required=False)
    project_id = serializers.UUIDField(required=False)
    text = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    slots = SlotInput(many=True, required=False)
    lanes = serializers.ListField(
        child=serializers.ChoiceField(choices=Lane.choices), required=False
    )
    scope = serializers.ChoiceField(choices=Audience.choices, required=False)


class SearchView(APIView):
    """``POST /api/collab/search/`` — find collaborators for a need.

    Runs only when a seeker asks. The query comes pre-filled from a call or a
    project, or from the seeker's own words, and may be edited (``slots``)
    before it runs. Behind ``COLLAB_SEARCH_ENABLED``.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from django.conf import settings

        from apps.research.models import Project

        from . import matcher

        if not settings.COLLAB_SEARCH_ENABLED:
            return Response(
                {"detail": "Collaborator search is not available yet."},
                status=status.HTTP_404_NOT_FOUND,
            )
        payload = SearchInput(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        options = {}
        if data.get("lanes"):
            options["lanes"] = tuple(data["lanes"])
        if data.get("scope"):
            options["scope"] = data["scope"]
        try:
            if data["entry"] == "call":
                call = ContentItem.objects.filter(
                    pk=data.get("content_id"), type="grant"
                ).first()
                if call is None:
                    return Response({"detail": "No such call."}, status=404)
                query = matcher.query_for_call(request.user, call, **options)
            elif data["entry"] == "project":
                project = Project.objects.filter(pk=data.get("project_id")).first()
                if project is None:
                    return Response({"detail": "No such project."}, status=404)
                query = matcher.query_for_project(request.user, project, **options)
            else:
                query = matcher.query_for_text(
                    request.user, data.get("text") or "", **options
                )
            if data.get("slots") is not None:
                query.slots = matcher._with_vectors(
                    [dict(slot) for slot in data["slots"]]
                )
            result = matcher.search(request.user, query)
        except matcher.SearchRefused as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response(
            {
                "slots": [
                    {k: v for k, v in slot.items() if k != "vector"}
                    for slot in query.slots
                ],
                **result.as_dict(),
            }
        )


class MatchFeedbackInput(serializers.Serializer):
    candidate = serializers.CharField(max_length=150)
    lane = serializers.ChoiceField(choices=Lane.choices)
    kind = serializers.ChoiceField(choices=MatchFeedback.Kind.choices)


class MatchFeedbackView(APIView):
    """``POST /api/collab/searches/<id>/feedback/`` — Save or Not relevant.

    Only for a person that search actually returned to this seeker; nothing is
    ever sent to the candidate.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, search_id):
        from django.contrib.auth import get_user_model

        log = SearchLog.objects.filter(pk=search_id, seeker=request.user).first()
        if log is None:
            return Response({"detail": "No such search."}, status=404)
        payload = MatchFeedbackInput(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        returned = {
            row["username"]
            for row in (log.cached.get("lanes") or {}).get(data["lane"], [])
        }
        if data["candidate"] not in returned:
            return Response({"detail": "Not a result of that search."}, status=400)
        candidate = get_user_model().objects.get(username=data["candidate"])
        row = MatchFeedback.objects.create(
            seeker=request.user,
            candidate=candidate,
            lane=data["lane"],
            kind=data["kind"],
            search=log,
        )
        return Response({"id": row.pk}, status=status.HTTP_201_CREATED)
