"""HTTP for the ambient app.

A project editor's view of attribution (Plan 03), and a person's own questions
from Mylo (Plan 06). Thin by design — who may see and change what is decided
in :mod:`.editing` and :mod:`.dialogue`, where it can be read in one place.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from . import editing


def _editable_project(request: Request, pk):
    from apps.research.models import Project

    project = get_object_or_404(
        Project.objects.select_related("scope_lab", "scope_user"), pk=pk
    )
    if not editing.can_edit(request.user, project):
        raise PermissionDenied("Only this project's editors can see its attributions.")
    return project


class ProjectConversationView(APIView):
    """``GET`` — recent attributions, heard channels, and correction targets."""

    def get(self, request: Request, pk) -> Response:
        project = _editable_project(request, pk)
        return Response(editing.conversation(project, request.user))


class ProjectChannelHintView(APIView):
    """``POST {place_id, on}`` — point a channel at this project, or stop."""

    def post(self, request: Request, pk) -> Response:
        project = _editable_project(request, pk)
        place_id = str(request.data.get("place_id") or "").strip()
        if not place_id:
            raise ValidationError({"place_id": "Choose a channel."})
        on = request.data.get("on", True)
        on = on if isinstance(on, bool) else str(on).lower() in {"1", "true", "yes"}
        try:
            payload = editing.set_hint(project, request.user, place_id, on=on)
        except editing.Refused as refusal:
            raise ValidationError({"detail": str(refusal)}) from refusal
        from apps.accounts.services import record_audit_event

        record_audit_event(
            actor=request.user,
            action="ambient.channel_hint.set" if on else "ambient.channel_hint.clear",
            target_type="project",
            target_id=str(project.pk),
            metadata={"place_id": place_id},
        )
        return Response(payload)


class AttributionCorrectView(APIView):
    """``POST {project: <id>|null}`` — "this was about a different project"."""

    def post(self, request: Request, ref_id: int) -> Response:
        from apps.research.models import Project

        raw = request.data.get("project")
        target = None
        if raw not in (None, ""):
            target = Project.objects.filter(pk=str(raw)).first()
            if target is None:
                raise ValidationError({"project": "No such project."})
        try:
            result = editing.correct(int(ref_id), request.user, target)
        except editing.Refused as refusal:
            raise PermissionDenied(str(refusal)) from refusal
        from apps.accounts.services import record_audit_event

        record_audit_event(
            actor=request.user,
            action="ambient.attribution.correct",
            target_type="ambient_raw_message_ref",
            target_id=str(result.ref.pk),
            metadata={"to_project": str(target.pk) if target else None},
        )
        return Response(
            {
                "id": result.ref.pk,
                "project": str(target.pk) if target else None,
                "observations_updated": result.observations,
            },
            status=status.HTTP_200_OK,
        )


def _suggestion_row(suggestion) -> dict:
    from . import dialogue

    return {
        "id": suggestion.pk,
        "kind": suggestion.kind,
        "topic": suggestion.topic,
        "question": dialogue.question_text(suggestion),
        "explanation": suggestion.explanation,
        "choices": suggestion.choices,
        "project": (
            {"id": str(suggestion.project_id), "name": suggestion.project.name}
            if suggestion.project_id
            else None
        ),
        "state": suggestion.state,
        "asked_at": suggestion.asked_at,
        "expires_at": suggestion.expires_at,
    }


class SuggestionListView(APIView):
    """``GET`` — the questions Mylo has for me, strongest first (Plan 06)."""

    def get(self, request: Request) -> Response:
        from . import dialogue

        return Response(
            {
                "suggestions": [
                    _suggestion_row(s) for s in dialogue.open_for(request.user)
                ]
            }
        )


class SuggestionAnswerView(APIView):
    """``POST {choice, correction?}`` — answer one of my questions on the web.

    The first answer wins, whichever surface it came from; a second one is
    told where the first was given (``409``).
    """

    def post(self, request: Request, pk: int) -> Response:
        from . import dialogue
        from .models import PendingSuggestion

        suggestion = get_object_or_404(PendingSuggestion, pk=pk, user=request.user)
        choice = str(request.data.get("choice") or "")
        if not choice:
            raise ValidationError({"choice": ["Choose one of the offered answers."]})
        correction = str(request.data.get("correction") or "")[:200]
        verdict = (
            PendingSuggestion.Verdict.CORRECTED
            if correction
            and dialogue.verdict_for(choice) == PendingSuggestion.Verdict.CONFIRMED
            else ""
        )
        taken, line = dialogue.answer(
            suggestion,
            choice=choice,
            verdict=verdict,
            correction=correction,
            surface=PendingSuggestion.Surface.WEB,
            by=request.user,
        )
        suggestion.refresh_from_db()
        return Response(
            {
                "taken": taken,
                "message": line,
                "suggestion": _suggestion_row(suggestion),
            },
            status=status.HTTP_200_OK if taken else status.HTTP_409_CONFLICT,
        )
