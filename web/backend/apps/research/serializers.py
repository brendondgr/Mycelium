from rest_framework import serializers

from apps.core.people import display_name, initials

from .models import Project


class ProjectMemberSerializer(serializers.Serializer):
    """A user as a project participant — read-only display fields only."""

    username = serializers.CharField()
    name = serializers.SerializerMethodField()
    initials = serializers.SerializerMethodField()

    def get_name(self, user) -> str:
        return display_name(user)

    def get_initials(self, user) -> str:
        return initials(user)


class ProjectSerializer(serializers.ModelSerializer):
    """Read-only project summary for the dashboard.

    ``status`` and ``progress`` are optional display hints the model does not
    carry as columns: they are read out of the free-form ``goals`` JSON when an
    author has set them, and are ``null`` otherwise so the UI can omit them
    rather than invent a value.
    """

    scope = serializers.CharField(read_only=True)
    scope_name = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    members = ProjectMemberSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "name",
            "scope",
            "scope_name",
            "goals",
            "status",
            "progress",
            "member_count",
            "members",
            "updated_at",
        ]

    def get_scope_name(self, project: Project) -> str:
        if project.scope == "lab" and project.scope_lab_id:
            return project.scope_lab.name
        if project.scope == "department" and project.scope_department_id:
            return project.scope_department.name
        return "Personal"

    def get_status(self, project: Project):
        goals = project.goals if isinstance(project.goals, dict) else {}
        value = goals.get("status")
        return value if isinstance(value, str) and value.strip() else None

    def get_progress(self, project: Project):
        goals = project.goals if isinstance(project.goals, dict) else {}
        value = goals.get("progress")
        return value if isinstance(value, (int, float)) else None

    def get_member_count(self, project: Project) -> int:
        return project.members.count()


class ProjectCreateSerializer(serializers.ModelSerializer):
    """Create a project scoped to a lab (``lab`` slug) or the caller (personal).

    ``lab`` is a write-only convenience field; the view resolves it to
    ``scope_lab`` after a manage-permission check, or falls back to a personal
    project scoped to the caller. Kept intentionally basic: name + optional goals.
    """

    lab = serializers.SlugField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Project
        fields = ["id", "name", "goals", "lab"]
        read_only_fields = ["id"]

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("A project name is required.")
        return value

    def validate_goals(self, value):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("goals must be an object.")
        return value
