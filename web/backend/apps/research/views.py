from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListCreateAPIView

from apps.accounts.models import Lab
from apps.accounts.permissions import user_can_manage_lab
from apps.accounts.services import record_audit_event

from .models import Project
from .serializers import ProjectCreateSerializer, ProjectSerializer


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
