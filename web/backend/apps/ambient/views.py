"""HTTP for the ambient app: a project editor's view of attribution.

Thin by design — who may see and change what is decided in
:mod:`.editing`, where it can be read in one place.
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
