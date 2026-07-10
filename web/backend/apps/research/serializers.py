from rest_framework import serializers

from apps.content.targets import project_interests, project_watch_topics
from apps.core.people import display_name, initials

from .models import Project


def _clean_list(value) -> list[str]:
    """Normalize a list-ish value: stringify, trim, drop blanks, dedupe (order-kept)."""
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = " ".join(str(item).split())
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


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
    focus = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    is_member = serializers.SerializerMethodField()
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
            "focus",
            "member_count",
            "is_member",
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

    def get_focus(self, project: Project) -> dict:
        """The project's research focus, normalized (drives its recommendations).

        Read through the same builder the matcher uses, so an older project whose
        focus only lives in legacy ``goals`` fields still reports a sensible shape.
        """
        ints = project_interests(project)
        return {
            "areas": ints["areas"],
            "keywords": ints["keywords"],
            "statement": ints["statement"],
            "watch_topics": project_watch_topics(project),
        }

    def get_member_count(self, project: Project) -> int:
        return project.members.count()

    def get_is_member(self, project: Project) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        return any(m.id == user.id for m in project.members.all())


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


class ProjectUpdateSerializer(serializers.Serializer):
    """Edit a project's name and research focus.

    ``focus`` is a purpose-built write field — ``{areas, keywords, statement,
    watch_topics}`` — that is merged into ``goals.interests`` / ``goals.watch_topics``
    without disturbing other free-form ``goals`` keys (status, progress, …). This is
    what gives a project the specific topic its daily recommendations run against.
    """

    name = serializers.CharField(required=False)
    focus = serializers.DictField(required=False)

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("A project name cannot be blank.")
        return value

    def update(self, instance: Project, validated: dict) -> Project:
        if "name" in validated:
            instance.name = validated["name"]
        if "focus" in validated:
            focus = validated["focus"] or {}
            goals = dict(instance.goals if isinstance(instance.goals, dict) else {})
            goals["interests"] = {
                "areas": _clean_list(focus.get("areas")),
                "keywords": _clean_list(focus.get("keywords")),
                "statement": str(focus.get("statement") or "").strip(),
            }
            if "watch_topics" in focus:
                goals["watch_topics"] = _clean_list(focus.get("watch_topics"))
            instance.goals = goals
        instance.save()
        return instance
