from rest_framework import serializers

from apps.accounts.interests import validate_interests
from apps.content.targets import (
    project_interests,
    project_watch_categories,
    project_watch_topics,
)
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


def apply_focus(goals: dict, focus: dict) -> dict:
    """Merge a ``focus`` payload into a project's ``goals`` JSON (non-destructive).

    ``focus`` = ``{areas, keywords, statement, clusters?, watch_topics?}`` — the
    purpose-built research surface that drives a project's recommendations. It is
    merged into ``goals.interests`` / ``goals.watch_topics`` without disturbing the
    other free-form ``goals`` keys (status, progress, description, …). When
    ``clusters`` are present they are validated as a partition of ``areas`` through
    the shared v2 interests contract, so a project's clusters obey the exact same
    rules as a user or lab profile; a clusterless focus stays a valid flat v1
    surface. Returns the updated goals dict (the same object, mutated + returned).
    """
    focus = focus or {}
    areas = _clean_list(focus.get("areas"))
    keywords = _clean_list(focus.get("keywords"))
    statement = str(focus.get("statement") or "").strip()
    interests: dict = {"areas": areas, "keywords": keywords, "statement": statement}

    clusters = focus.get("clusters")
    if clusters:
        # Reuse the profile contract's partition validation (raises a DRF 400 on a
        # bad partition). We only keep the normalized ``clusters`` back — areas /
        # keywords / statement are already cleaned above.
        validated = validate_interests(
            {
                "areas": areas,
                "keywords": keywords,
                "statement": statement,
                "clusters": clusters,
            }
        )
        interests["clusters"] = validated["clusters"]

    goals = dict(goals if isinstance(goals, dict) else {})
    goals["interests"] = interests
    if "watch_topics" in focus:
        goals["watch_topics"] = _clean_list(focus.get("watch_topics"))
    return goals


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
    watch_categories = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    is_member = serializers.SerializerMethodField()
    is_over_cap = serializers.SerializerMethodField()
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
            "watch_categories",
            "member_count",
            "is_member",
            "is_archived",
            "is_over_cap",
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
        Carries the v2 ``clusters`` when the project has organized its areas.
        """
        ints = project_interests(project)
        return {
            "areas": ints["areas"],
            "keywords": ints["keywords"],
            "statement": ints["statement"],
            "clusters": ints.get("clusters", []),
            "watch_topics": project_watch_topics(project),
        }

    def get_watch_categories(self, project: Project) -> list[str]:
        """Which recommendation areas this project runs (default: all four)."""
        return project_watch_categories(project)

    def get_member_count(self, project: Project) -> int:
        return project.members.count()

    def get_is_member(self, project: Project) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        return any(m.id == user.id for m in project.members.all())

    def get_is_over_cap(self, project: Project) -> bool:
        """Whether this active project sits beyond the owner's plan cap.

        An over-cap project (after a downgrade) keeps its stored recommendations
        but is skipped by scoring. The list view supplies ``over_cap_ids`` in
        context; without it (e.g. a single-project read) we report False.
        """
        if project.is_archived:
            return False
        over = self.context.get("over_cap_ids")
        return over is not None and project.id in over


class ProjectCreateSerializer(serializers.ModelSerializer):
    """Create a project scoped to a lab, a department, or the caller (personal).

    ``lab`` / ``department`` are write-only slug conveniences; the view resolves
    the scope after a manage-permission check and a plan-cap check, falling back
    to a personal project scoped to the caller when neither is given. ``focus`` is
    the guided-creation research surface (areas / keywords / statement / clusters /
    watch_topics) that Mylo composes from the project's plain-language purpose; it
    is merged into ``goals`` by the view via :func:`apply_focus`.
    """

    lab = serializers.SlugField(write_only=True, required=False, allow_blank=True)
    # Departments are UUID-keyed (no slug); accept the id as a string.
    department = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    focus = serializers.DictField(write_only=True, required=False)

    class Meta:
        model = Project
        fields = ["id", "name", "goals", "lab", "department", "focus"]
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
    watch_categories = serializers.ListField(
        child=serializers.CharField(), required=False
    )

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("A project name cannot be blank.")
        return value

    def validate_watch_categories(self, value) -> list[str]:
        allowed = {"papers", "grants", "fellowships", "conferences"}
        out = [str(v).strip().lower() for v in value if str(v).strip()]
        bad = [v for v in out if v not in allowed]
        if bad:
            raise serializers.ValidationError(f"unknown categories: {', '.join(bad)}")
        # Preserve a stable order and dedupe.
        return [c for c in ("papers", "grants", "fellowships", "conferences") if c in out]

    def update(self, instance: Project, validated: dict) -> Project:
        if "name" in validated:
            instance.name = validated["name"]
        if "focus" in validated:
            instance.goals = apply_focus(instance.goals, validated["focus"] or {})
        if "watch_categories" in validated:
            goals = dict(instance.goals if isinstance(instance.goals, dict) else {})
            goals["watch_categories"] = validated["watch_categories"]
            instance.goals = goals
        instance.save()
        return instance
