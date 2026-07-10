from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView, ListCreateAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Lab, LabMembership
from apps.accounts.permissions import (
    user_can_manage_lab,
    user_has_department_access,
    user_has_lab_access,
)
from apps.accounts.services import record_audit_event

from .models import Project, ProjectMember
from .serializers import (
    ProjectCreateSerializer,
    ProjectSerializer,
    ProjectUpdateSerializer,
)


class ProjectListView(ListCreateAPIView):
    """List the projects the caller may see, or create a new one.

    Visibility is delegated to ``Project.objects.visible_to`` (members, personal
    owners, lab heads, and department heads). An optional ``?lab=<slug>`` filter
    narrows to a single lab's projects — the switcher's scope — and never widens
    visibility beyond what the caller could already see.

    ``POST`` creates a project scoped to a lab (``lab`` slug, requires manage
    rights on that lab) or, with no lab, a personal project scoped to the caller.
    """

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProjectCreateSerializer
        return ProjectSerializer

    def get_queryset(self):
        qs = (
            Project.objects.visible_to(self.request.user)
            .select_related("scope_lab", "scope_department", "scope_user")
            .prefetch_related("members")
        )
        lab_slug = self.request.query_params.get("lab", "").strip()
        if lab_slug:
            qs = qs.filter(scope_lab__slug=lab_slug)
        return qs

    def perform_create(self, serializer: ProjectCreateSerializer) -> None:
        lab_slug = (serializer.validated_data.pop("lab", "") or "").strip()
        user = self.request.user
        if lab_slug:
            lab = get_object_or_404(Lab, slug=lab_slug)
            if not user_can_manage_lab(user, lab):
                raise PermissionDenied(
                    "Only a lab owner or admin can add projects to this lab."
                )
            project = serializer.save(scope_lab=lab)
            target = {"scope": "lab", "lab_id": str(lab.id)}
        else:
            project = serializer.save(scope_user=user)
            target = {"scope": "user"}
        record_audit_event(
            actor=user,
            action="project.create",
            target_type="project",
            target_id=str(project.id),
            metadata={"name": project.name, **target},
        )


class LabProjectsView(ListAPIView):
    """Every project of one lab, for any member of that lab.

    Unlike the personal project list (``visible_to``, which only shows a
    rank-and-file member the projects they already belong to), this lets any lab
    member browse *all* of the lab's projects so they can decide to join one.
    Each row carries ``is_member`` so the UI can offer Join vs Leave.
    """

    serializer_class = ProjectSerializer

    def get_queryset(self):
        lab = get_object_or_404(Lab, slug=self.kwargs["slug"])
        if not user_has_lab_access(self.request.user, lab):
            raise PermissionDenied("You do not have access to this lab.")
        return (
            Project.objects.filter(scope_lab=lab)
            .select_related("scope_lab")
            .prefetch_related("members")
        )


def _user_can_edit(user, project: Project) -> bool:
    """Who may edit a project's name / focus.

    The personal owner edits their own project; a lab owner/admin edits their lab's
    projects (mirroring who may create them). Department-scoped projects are not
    editable through this API yet.
    """
    if project.scope_user_id is not None:
        return project.scope_user_id == user.id
    if project.scope_lab_id is not None:
        return user_can_manage_lab(user, project.scope_lab)
    return False


class ProjectDetailView(APIView):
    """Read one project (any viewer) or edit its name / research focus (managers)."""

    def _get_visible(self, request, pk) -> Project:
        project = get_object_or_404(
            Project.objects.select_related(
                "scope_lab", "scope_department", "scope_user"
            ).prefetch_related("members"),
            pk=pk,
        )
        if not project.is_visible_to(request.user):
            raise PermissionDenied("You do not have access to this project.")
        return project

    def get(self, request: Request, pk) -> Response:
        project = self._get_visible(request, pk)
        return Response(ProjectSerializer(project, context={"request": request}).data)

    def patch(self, request: Request, pk) -> Response:
        project = self._get_visible(request, pk)
        if not _user_can_edit(request.user, project):
            raise PermissionDenied("You cannot edit this project.")
        serializer = ProjectUpdateSerializer(project, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        record_audit_event(
            actor=request.user,
            action="project.update",
            target_type="project",
            target_id=str(project.id),
            metadata={"name": project.name},
        )
        return Response(ProjectSerializer(project, context={"request": request}).data)


def _user_can_join(user, project: Project) -> bool:
    """A lab/department member may self-join that org's projects."""
    if project.scope_lab_id is not None:
        return user_has_lab_access(user, project.scope_lab)
    if project.scope_department_id is not None:
        return user_has_department_access(user, project.scope_department)
    return False  # personal projects have no self-join


class ProjectJoinView(APIView):
    """The caller joins a lab/department project they are eligible for."""

    def post(self, request: Request, pk) -> Response:
        project = get_object_or_404(
            Project.objects.select_related("scope_lab", "scope_department"), pk=pk
        )
        if not _user_can_join(request.user, project):
            raise PermissionDenied(
                "Only members of this project's lab or department can join it."
            )
        _, created = ProjectMember.objects.get_or_create(
            project=project, user=request.user
        )
        if created:
            record_audit_event(
                actor=request.user,
                action="project.join",
                target_type="project",
                target_id=str(project.id),
                metadata={"name": project.name},
            )
        return Response(
            ProjectSerializer(project, context={"request": request}).data
        )


class ProjectLeaveView(APIView):
    """The caller leaves a project they belong to."""

    def post(self, request: Request, pk) -> Response:
        project = get_object_or_404(Project, pk=pk)
        ProjectMember.objects.filter(project=project, user=request.user).delete()
        record_audit_event(
            actor=request.user,
            action="project.leave",
            target_type="project",
            target_id=str(project.id),
            metadata={"name": project.name},
        )
        return Response(
            ProjectSerializer(project, context={"request": request}).data
        )


class ProjectMembersView(APIView):
    """A lab manager adds another lab member to one of the lab's projects."""

    def post(self, request: Request, pk) -> Response:
        project = get_object_or_404(
            Project.objects.select_related("scope_lab"), pk=pk
        )
        if project.scope_lab_id is None:
            raise ValidationError("Members can only be added to lab projects.")
        if not user_can_manage_lab(request.user, project.scope_lab):
            raise PermissionDenied(
                "Only a lab owner or admin can add project members."
            )
        username = str(request.data.get("username", "")).strip()
        if not username:
            raise ValidationError({"username": ["A username is required."]})
        target = get_object_or_404(User, username=username)
        if not LabMembership.objects.filter(
            user=target, lab=project.scope_lab
        ).exists():
            raise ValidationError("That person is not a member of this lab.")
        ProjectMember.objects.get_or_create(project=project, user=target)
        return Response(
            ProjectSerializer(project, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )
