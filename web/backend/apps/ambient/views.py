"""HTTP for the ambient app.

A project editor's view of attribution (Plan 03), and a person's own questions
from Mylo (Plan 06). Thin by design — who may see and change what is decided
in :mod:`.editing` and :mod:`.dialogue`, where it can be read in one place.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
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


# -- the "Mylo & you" page (Plan 07) -------------------------------------------


def _change_row(change, viewer) -> dict:
    from . import review

    return {
        "id": change.pk,
        "kind": change.kind,
        "kind_label": change.get_kind_display(),
        "topic": change.topic,
        "project": (
            {"id": str(change.project_id), "name": change.project.name}
            if change.project_id
            else None
        ),
        "field": change.field,
        "old_value": change.old_value,
        "new_value": change.new_value,
        "surface": change.surface,
        "explanation": change.explanation,
        "visibility": change.visibility,
        "by": {
            "id": change.user_id,
            "name": change.user.get_full_name() or change.user.get_username(),
            "you": change.user_id == viewer.pk,
        },
        "created_at": change.created_at,
        "undone_at": change.undone_at,
        "undo_of": change.undo_of_id,
        "can_undo": change.undoable and review.may_undo(change, viewer),
    }


class ChangeListView(APIView):
    """``GET`` — what changed: my own changes, and the lab-visible changes to
    projects I am on, newest first."""

    def get(self, request: Request) -> Response:
        from . import review

        return Response(
            {
                "changes": [
                    _change_row(c, request.user)
                    for c in review.changes_for(request.user)
                ]
            }
        )


class ChangeUndoView(APIView):
    """``POST`` — undo one change. Never time-limited; logged as its own change."""

    def post(self, request: Request, pk: int) -> Response:
        from . import review
        from .models import AppliedChange

        change = get_object_or_404(AppliedChange, pk=pk)
        if not review.may_undo(change, request.user):
            raise PermissionDenied("You can't undo this change.")
        try:
            reversal = review.undo(change, by=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        change.refresh_from_db()
        return Response(
            {
                "change": _change_row(change, request.user),
                "undo": _change_row(reversal, request.user),
            }
        )


class UnderstandingView(APIView):
    """``GET`` — what Mylo knows about me: every edge, with where it came from."""

    def get(self, request: Request) -> Response:
        from . import review

        return Response(review.understanding_for(request.user))


class UnderstandingItemView(APIView):
    """``PATCH {label}`` — reword one thing Mylo understood (it becomes mine);
    ``DELETE`` — remove it."""

    def patch(self, request: Request, concept_id: int, relation: str) -> Response:
        from . import review

        label = str(request.data.get("label") or "")
        if not review.edit_understanding(request.user, concept_id, relation, label):
            raise ValidationError(
                {"label": ["Nothing to change, or nothing to call it."]}
            )
        return Response(review.understanding_for(request.user))

    def delete(self, request: Request, concept_id: int, relation: str) -> Response:
        from . import review

        if not review.delete_understanding(request.user, concept_id, relation):
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UnderstandingReopenView(APIView):
    """``POST`` — reopen something I declined or let fade: my own yes."""

    def post(self, request: Request, concept_id: int, relation: str) -> Response:
        from . import review

        change = review.reopen(request.user, concept_id, relation)
        if change is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response({"change": _change_row(change, request.user)})


class AmbientSettingsView(APIView):
    """``GET`` / ``PUT {listening_discord?, listening_slack?, questions_muted?,
    quiet_until?}``."""

    def get(self, request: Request) -> Response:
        from . import review

        return Response(review.settings_for(request.user))

    def put(self, request: Request) -> Response:
        from . import review

        allowed = {
            "listening_discord",
            "listening_slack",
            "listening_teams",
            "questions_muted",
            "quiet_until",
        }
        data = {k: v for k, v in request.data.items() if k in allowed}
        if "quiet_until" in data and data["quiet_until"]:
            from django.utils.dateparse import parse_date

            parsed = parse_date(str(data["quiet_until"]))
            if parsed is None:
                raise ValidationError({"quiet_until": ["A date, YYYY-MM-DD."]})
            data["quiet_until"] = parsed
        return Response(review.update_settings(request.user, data))


class ObservationsDeleteView(APIView):
    """``POST {confirm: true}`` — delete everything Mylo understood about me."""

    def post(self, request: Request) -> Response:
        from . import review

        if request.data.get("confirm") is not True:
            raise ValidationError({"confirm": ["Confirm with true to delete."]})
        retraction = review.delete_everything(request.user)
        return Response({"deleted_observations": len(retraction.observation_ids or [])})


class ProjectDevelopmentsView(APIView):
    """``GET`` — a project's development timeline, for anybody who can see the
    project; private developments only for the person who said them."""

    def get(self, request: Request, pk) -> Response:
        from apps.research.models import Project

        from . import review

        project = get_object_or_404(Project.objects.visible_to(request.user), pk=pk)
        return Response(
            {"developments": review.project_developments(project, request.user)}
        )


class LabChangesView(APIView):
    """``GET`` — a lab's "What changed": shared projects only, lab members only."""

    def get(self, request: Request, slug: str) -> Response:
        from apps.accounts.models import Lab, LabMembership

        from . import review

        lab = get_object_or_404(Lab, slug=slug)
        if not LabMembership.objects.filter(lab=lab, user=request.user).exists():
            raise PermissionDenied("Only this lab's members can see its changes.")
        return Response(
            {"changes": [_change_row(c, request.user) for c in review.lab_changes(lab)]}
        )


class TranscriptUploadView(APIView):
    """``POST`` a meeting transcript (Plan 11, steps 9–12).

    Multipart ``file`` (or a ``text`` field), ``title``, ``occurred_at`` (ISO),
    and ``project`` (id) or ``lab`` (slug). Without ``speakers`` (a JSON map of
    label → user id) nothing is ingested: the reply lists the labels and the
    members they may be mapped to, so the person can say who was who. With it,
    the transcript is read into the buffer and the reply is the counts.
    """

    # The API default is JSON only; this view takes a file upload.
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request: Request) -> Response:
        import json

        from django.conf import settings
        from django.utils.dateparse import parse_datetime

        from . import transcripts

        if not getattr(settings, "AMBIENT_TRANSCRIPTS_ENABLED", False):
            raise PermissionDenied("Meeting transcripts are not turned on here.")
        upload = request.FILES.get("file")
        if upload is not None:
            if upload.size > int(settings.AMBIENT_TRANSCRIPT_MAX_BYTES):
                raise ValidationError({"file": ["That transcript is too large."]})
            text = upload.read().decode("utf-8", errors="replace")
        else:
            text = str(request.data.get("text") or "")
        if not text.strip():
            raise ValidationError({"file": ["The transcript is empty."]})
        project, lab = _meeting_scope(request)
        found = transcripts.labels(text)
        raw = request.data.get("speakers")
        if not raw:
            members = transcripts.members_of(project=project, lab=lab)
            from django.contrib.auth.models import User

            return Response(
                {
                    "labels": found,
                    "members": [
                        {"id": u.pk, "name": u.get_full_name() or u.username}
                        for u in User.objects.filter(pk__in=members).order_by(
                            "username"
                        )
                    ],
                }
            )
        try:
            speakers = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"speakers": ["Not a JSON object."]}) from exc
        when = parse_datetime(str(request.data.get("occurred_at") or ""))
        if when is None:
            raise ValidationError(
                {"occurred_at": ["Give the meeting's date and time."]}
            )
        try:
            meeting = transcripts.ingest(
                request.user,
                title=str(request.data.get("title") or "Meeting")[:200],
                occurred_at=when,
                text=text,
                speakers={str(k): v for k, v in speakers.items()},
                project=project,
                lab=lab,
            )
        except transcripts.TranscriptRefused as exc:
            raise PermissionDenied(exc.reason) from exc
        return Response(
            {
                "meeting": meeting.pk,
                "turns": meeting.turns,
                "counts": meeting.counts,
                "participants": len(meeting.participant_ids),
            },
            status=status.HTTP_201_CREATED,
        )


def _meeting_scope(request):
    """The project or lab a transcript is for — one the caller belongs to.

    Checked before anything is read back: the preview answers with the scope's
    members (ids and names), so resolving a lab by slug alone handed any signed-in
    account the roster of any lab whose slug it could guess. A lab the caller is
    not in and a lab that does not exist get the same refusal.
    """
    from apps.accounts.models import Lab
    from apps.accounts.permissions import user_has_lab_access
    from apps.research.models import Project

    project_id = request.data.get("project")
    if project_id:
        project = (
            Project.objects.visible_to(request.user).filter(pk=project_id).first()
        )
        if project is None:
            raise PermissionDenied("You can't add a meeting to that project.")
        return project, None
    slug = str(request.data.get("lab") or "").strip()
    if not slug:
        raise ValidationError({"project": ["Choose a project or a lab."]})
    lab = Lab.objects.filter(slug=slug).first()
    if lab is None or not user_has_lab_access(request.user, lab):
        raise PermissionDenied("You can't add a meeting to that lab.")
    return None, lab
