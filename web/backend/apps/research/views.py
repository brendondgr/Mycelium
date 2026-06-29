from rest_framework.generics import ListAPIView

from .models import Project
from .serializers import ProjectSerializer


class ProjectListView(ListAPIView):
    """Projects the caller may see, under the lab/department cascade.

    Visibility is delegated to ``Project.objects.visible_to`` (members, personal
    owners, lab heads, and department heads). An optional ``?lab=<slug>`` filter
    narrows to a single lab's projects — the switcher's scope — and never widens
    visibility beyond what the caller could already see.
    """

    serializer_class = ProjectSerializer

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
