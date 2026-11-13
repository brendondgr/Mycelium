from rest_framework import serializers
from tools.recommendation.targets import (
    project_interests,
    project_watch_categories,
    project_watch_topics,
)

from apps.accounts.interests import validate_interests
from apps.core.people import display_name, initials

from . import visibility as rules
from .models import (
    Project,
    ProjectInvitation,
    ProjectJoinRequest,
    ProjectMember,
    Visibility,
)
from .permissions import (
    EDIT_ROLES,
    user_can_change_visibility,
    user_can_invite_outside,
    user_can_request_to_join,
    user_manages_project_scope,
)


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


class ProjectInvitationSerializer(serializers.ModelSerializer):
    """One project invitation, for both the sender's roster and the invitee's feed."""

    project_id = serializers.CharField(source="project.id", read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True)
    scope_name = serializers.SerializerMethodField()
    invitee = serializers.SerializerMethodField()
    inviter = serializers.SerializerMethodField()

    class Meta:
        model = ProjectInvitation
        fields = [
            "id",
            "project_id",
            "project_name",
            "scope_name",
            "invitee",
            "inviter",
            "message",
            "status",
            "created_at",
        ]

    def get_scope_name(self, invitation: ProjectInvitation) -> str:
        """Where the project lives — the lab's name, or "Personal"."""
        project = invitation.project
        if project.scope_lab_id:
            return project.scope_lab.name
        if project.scope_department_id:
            return project.scope_department.name
        return "Personal"

    def get_invitee(self, invitation: ProjectInvitation) -> dict:
        return _person(invitation.invitee)

    def get_inviter(self, invitation: ProjectInvitation) -> dict | None:
        return _person(invitation.inviter) if invitation.inviter_id else None


def _person(user) -> dict:
    return {
        "username": user.get_username(),
        "name": display_name(user),
        "initials": initials(user),
    }


#: Alias bounds. See ``ProjectUpdateSerializer.validate_aliases``.
ALIAS_MIN = 3
ALIAS_MAX = 60
ALIAS_LIMIT = 20


class ProjectSerializer(serializers.ModelSerializer):
    """Read-only project summary for the dashboard.

    ``status`` and ``progress`` are optional display hints the model does not
    carry as columns: they are read out of the free-form ``goals`` JSON when an
    author has set them, and are ``null`` otherwise so the UI can omit them
    rather than invent a value.
    """

    scope = serializers.CharField(read_only=True)
    scope_name = serializers.SerializerMethodField()
    scope_slug = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    focus = serializers.SerializerMethodField()
    watch_categories = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    is_member = serializers.SerializerMethodField()
    is_over_cap = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_manage_members = serializers.SerializerMethodField()
    my_role = serializers.SerializerMethodField()
    is_participant = serializers.SerializerMethodField()
    can_change_visibility = serializers.SerializerMethodField()
    allowed_visibilities = serializers.SerializerMethodField()
    can_invite_outside = serializers.SerializerMethodField()
    can_request = serializers.SerializerMethodField()
    members = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id",
            "name",
            "scope",
            "scope_name",
            "scope_slug",
            "goals",
            "description",
            "status",
            "progress",
            "focus",
            "watch_categories",
            "member_count",
            "is_member",
            "is_archived",
            "visibility",
            "my_role",
            "is_participant",
            "is_over_cap",
            "can_edit",
            "can_manage_members",
            "can_change_visibility",
            "allowed_visibilities",
            "can_invite_outside",
            "can_request",
            "members",
            "aliases",
            "updated_at",
        ]

    def get_scope_name(self, project: Project) -> str:
        if project.scope == "lab" and project.scope_lab_id:
            return project.scope_lab.name
        if project.scope == "department" and project.scope_department_id:
            return project.scope_department.name
        return "Personal"

    def get_scope_slug(self, project: Project) -> str | None:
        """The owning lab's slug — how the UI links a project back to its lab.

        ``null`` for a personal project and for a department (which is UUID-keyed,
        not slugged), so a caller can tell "this belongs to a lab" from the payload
        alone rather than inferring it from the active workspace.
        """
        if project.scope == "lab" and project.scope_lab_id:
            return project.scope_lab.slug
        return None

    def get_description(self, project: Project):
        """The project's human description, or ``None`` when it has none.

        Read in the same order the matcher reads a statement: the explicit
        ``goals.description`` / ``goals.goal``, then the focus statement a
        Mylo-composed project stores under ``goals.interests.statement`` — so a
        project created through the wizard reads as described rather than blank.
        """
        goals = project.goals if isinstance(project.goals, dict) else {}
        for value in (goals.get("description"), goals.get("goal")):
            if isinstance(value, str) and value.strip():
                return value.strip()
        statement = project_interests(project)["statement"]
        return statement or None

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

    def _caller(self):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        return user

    def get_can_edit(self, project: Project) -> bool:
        """Whether the caller may edit this project (mirrors ``_user_can_edit``).

        Reported on the row so the UI shows the Edit affordance from the project
        itself rather than guessing from whichever workspace happens to be active —
        the guess was wrong whenever a lab project was opened from personal scope.

        The per-lab answer is memoized on the serializer: a list of a lab's twenty
        projects asks the same membership question twenty times otherwise.
        """
        user = self._caller()
        if user is None:
            return False
        if project.scope_user_id is not None and project.scope_user_id == user.id:
            return True
        if self.get_my_role(project) in EDIT_ROLES:
            return True
        if project.scope_lab_id is not None:
            key = ("lab", project.scope_lab_id)
        elif project.scope_department_id is not None:
            key = ("department", project.scope_department_id)
        else:
            return False
        cache = getattr(self, "_editable_scopes", None)
        if cache is None:
            cache = {}
            self._editable_scopes = cache
        if key not in cache:
            # Only the scope's managers are the same across a lab's projects;
            # a role is per project and was checked above.
            cache[key] = user_manages_project_scope(user, project)
        return cache[key]

    def get_my_role(self, project: Project) -> str | None:
        """The caller's role on the project (``owner`` / ``editor`` /
        ``member``), or ``null`` when they are not a member. Read from the
        prefetched memberships when the view supplied them."""
        user = self._caller()
        if user is None:
            return None
        cache = getattr(project, "_prefetched_objects_cache", {})
        if "memberships" in cache:
            for row in cache["memberships"]:
                if row.user_id == user.id:
                    return row.role
            return None
        return rules.member_role(user, project)

    def get_can_manage_members(self, project: Project) -> bool:
        """Whether the caller may add or remove this project's members.

        Same authority as editing: a personal project's owner, a lab project's
        owner / admin / PI, or a department project's owner / admin. A lab
        manager adds lab members directly; anyone else joins through an
        invitation.
        """
        return self.get_can_edit(project)

    def get_is_participant(self, project: Project) -> bool:
        """Whether this is one of the caller's projects (a member, or the
        personal owner). An overseer who can open it is not a participant, so
        the app keeps it out of "My projects"."""
        user = self._caller()
        if user is None:
            return False
        if project.scope_user_id is not None and project.scope_user_id == user.id:
            return True
        return self.get_my_role(project) is not None

    def get_can_change_visibility(self, project: Project) -> bool:
        user = self._caller()
        return user is not None and user_can_change_visibility(user, project)

    def get_allowed_visibilities(self, project: Project) -> list[str]:
        return list(rules.allowed_visibilities(project))

    def get_can_invite_outside(self, project: Project) -> bool:
        user = self._caller()
        return user is not None and user_can_invite_outside(user, project)

    def get_can_request(self, project: Project) -> bool:
        """Whether the caller may ask to join (and has no open request)."""
        user = self._caller()
        if user is None or not user_can_request_to_join(user, project):
            return False
        return not ProjectJoinRequest.objects.filter(
            project=project, user=user, state=ProjectJoinRequest.State.PENDING
        ).exists()

    def get_members(self, project: Project) -> list[dict]:
        """The roster: each person with their role, and ``outside`` when they
        are not in the project's lab (or department) — an outside collaborator,
        who sees this one project and nothing else of the lab."""
        cache = getattr(project, "_prefetched_objects_cache", {})
        if "memberships" in cache:
            rows = list(cache["memberships"])
        else:
            rows = list(project.memberships.select_related("user"))
        home = rules.scope_people_ids(project)
        rows.sort(key=lambda row: row.user.get_username())
        return [
            {
                **_person(row.user),
                "role": row.role,
                "outside": home is not None and row.user_id not in home,
            }
            for row in rows
        ]


class ProjectNameOnlySerializer(serializers.Serializer):
    """What a department head sees of a project in a lab set to *Names only*:
    name, owner, member count and scope — never goals, state, feed, files or
    the roster."""

    id = serializers.UUIDField()
    name = serializers.CharField()
    visibility = serializers.CharField()
    scope_name = serializers.SerializerMethodField()
    scope_slug = serializers.SerializerMethodField()
    owner = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    names_only = serializers.SerializerMethodField()

    def get_scope_name(self, project: Project) -> str:
        return project.scope_lab.name if project.scope_lab_id else ""

    def get_scope_slug(self, project: Project) -> str | None:
        return project.scope_lab.slug if project.scope_lab_id else None

    def get_owner(self, project: Project) -> dict | None:
        owner = rules.owner_of(project)
        return _person(owner) if owner is not None else None

    def get_member_count(self, project: Project) -> int:
        return ProjectMember.objects.filter(project=project).count()

    def get_names_only(self, project: Project) -> bool:
        return True


#: How long a directory row's focus line may run.
FOCUS_LINE_MAX = 160


def focus_line(project: Project) -> str:
    """One line saying what the project is about: its description, else its
    focus statement, else its areas — cut to :data:`FOCUS_LINE_MAX`."""
    goals = project.goals if isinstance(project.goals, dict) else {}
    text = ""
    for value in (goals.get("description"), goals.get("goal")):
        if isinstance(value, str) and value.strip():
            text = value
            break
    if not text:
        interests = project_interests(project)
        text = interests["statement"] or ", ".join(interests["areas"][:4])
    text = " ".join(str(text).split())
    if len(text) > FOCUS_LINE_MAX:
        text = text[: FOCUS_LINE_MAX - 1].rstrip() + "…"
    return text


class ProjectDirectorySerializer(serializers.Serializer):
    """A directory row: a project the caller can see exists but is not on.

    Name, a one-line focus, owner, member count and scope — never goals,
    state, feed, files or the roster. ``can_open`` is true for an overseer
    (who may open it without joining); ``can_request`` when the caller may ask
    to join; ``request_status`` is ``pending`` while their request is open.
    The view passes ``openable`` (ids) and ``pending`` (ids) in context.
    """

    id = serializers.UUIDField()
    name = serializers.CharField()
    visibility = serializers.CharField()
    scope = serializers.CharField()
    scope_name = serializers.SerializerMethodField()
    scope_slug = serializers.SerializerMethodField()
    focus = serializers.SerializerMethodField()
    owner = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    can_open = serializers.SerializerMethodField()
    can_request = serializers.SerializerMethodField()
    request_status = serializers.SerializerMethodField()

    def _rows(self, project: Project) -> list:
        cache = getattr(project, "_prefetched_objects_cache", {})
        if "memberships" in cache:
            return list(cache["memberships"])
        return list(project.memberships.select_related("user"))

    def get_scope_name(self, project: Project) -> str:
        if project.scope_lab_id:
            return project.scope_lab.name
        if project.scope_department_id:
            return project.scope_department.name
        return "Personal"

    def get_scope_slug(self, project: Project) -> str | None:
        return project.scope_lab.slug if project.scope_lab_id else None

    def get_focus(self, project: Project) -> str:
        return focus_line(project)

    def get_owner(self, project: Project) -> dict | None:
        for row in self._rows(project):
            if row.role == ProjectMember.Role.OWNER:
                return _person(row.user)
        if project.scope_user_id is not None:
            return _person(project.scope_user)
        return None

    def get_member_count(self, project: Project) -> int:
        return len(self._rows(project))

    def get_can_open(self, project: Project) -> bool:
        return project.id in self.context.get("openable", set())

    def get_request_status(self, project: Project) -> str | None:
        if project.id in self.context.get("pending", set()):
            return ProjectJoinRequest.State.PENDING
        return None

    def get_can_request(self, project: Project) -> bool:
        if project.id in self.context.get("pending", set()):
            return False
        # Every directory row is one the caller can see and is not on, so the
        # scope and the archive flag are what is left to decide.
        return not project.is_archived and rules.admits_requests(project)


class ProjectJoinRequestSerializer(serializers.ModelSerializer):
    """One join request, for the deciders' list and the requester's own."""

    project_id = serializers.CharField(source="project.id", read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True)
    user = serializers.SerializerMethodField()
    decided_by = serializers.SerializerMethodField()

    class Meta:
        model = ProjectJoinRequest
        fields = [
            "id",
            "project_id",
            "project_name",
            "user",
            "note",
            "state",
            "decided_by",
            "decided_at",
            "created_at",
        ]

    def get_user(self, row: ProjectJoinRequest) -> dict:
        return _person(row.user)

    def get_decided_by(self, row: ProjectJoinRequest) -> dict | None:
        return _person(row.decided_by) if row.decided_by_id else None


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
    #: The project's scope. Checked against what the resolved scope may take
    #: (``visibility.allowed_visibilities``) by the view; ``invite_only`` when
    #: omitted.
    visibility = serializers.ChoiceField(
        choices=Visibility.choices, required=False, write_only=True
    )

    class Meta:
        model = Project
        fields = ["id", "name", "goals", "lab", "department", "focus", "visibility"]
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
    """Edit a project's fundamentals: name, description, status, progress, focus.

    ``focus`` is a purpose-built write field — ``{areas, keywords, statement,
    watch_topics}`` — that is merged into ``goals.interests`` / ``goals.watch_topics``
    without disturbing other free-form ``goals`` keys. This is what gives a project
    the specific topic its daily recommendations run against.

    ``description`` / ``status`` / ``progress`` are the display fields the project
    page shows in its header; the model does not carry them as columns, so each is
    written into the free-form ``goals`` JSON under its own key. Sending ``null``
    (or an empty string, for the text fields) clears one rather than storing a
    blank, so the page falls back to "not set" instead of rendering an empty pill.

    ``visibility`` is a real column rather than a ``goals`` key: it is a
    permission-shaped decision every surface filters on, and a JSON key cannot be
    filtered on cheaply or trusted to exist. Only the owner may change it (the
    view checks), and only to a scope the project can take.
    """

    name = serializers.CharField(required=False)
    description = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    status = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    progress = serializers.IntegerField(
        required=False, allow_null=True, min_value=0, max_value=100
    )
    focus = serializers.DictField(required=False)
    watch_categories = serializers.ListField(
        child=serializers.CharField(), required=False
    )
    #: The project's one scope (``apps.research.visibility``).
    visibility = serializers.ChoiceField(choices=Visibility.choices, required=False)
    #: Other names people use for this project in conversation. Read by ambient
    #: attribution, where a name or alias is the strongest single signal.
    aliases = serializers.ListField(
        child=serializers.CharField(allow_blank=True), required=False
    )

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("A project name cannot be blank.")
        return value

    def validate_aliases(self, value) -> list[str]:
        """Short, distinct, and not the project's own name.

        Three characters at least, because anything shorter ("ML", "IO") occurs
        by accident in ordinary conversation and would attribute messages to
        this project that were never about it. Duplicates collapse ignoring
        case, blanks drop, and the list is capped so an alias field cannot
        become a keyword dump.
        """
        out: list[str] = []
        seen: set[str] = set()
        for raw in value:
            alias = " ".join(str(raw).split())
            if not alias:
                continue
            if len(alias) < ALIAS_MIN or len(alias) > ALIAS_MAX:
                raise serializers.ValidationError(
                    f"Each alias must be {ALIAS_MIN}–{ALIAS_MAX} characters: "
                    f"{alias!r}."
                )
            key = alias.casefold()
            if key not in seen:
                seen.add(key)
                out.append(alias)
        if len(out) > ALIAS_LIMIT:
            raise serializers.ValidationError(
                f"At most {ALIAS_LIMIT} aliases per project."
            )
        return out

    def validate_visibility(self, value: str) -> str:
        project = self.instance
        if project is not None and value not in rules.allowed_visibilities(project):
            raise serializers.ValidationError(
                f"A {project.scope} project cannot be scoped to {value!r}."
            )
        return value

    def validate_watch_categories(self, value) -> list[str]:
        allowed = {"papers", "grants", "fellowships", "conferences"}
        out = [str(v).strip().lower() for v in value if str(v).strip()]
        bad = [v for v in out if v not in allowed]
        if bad:
            raise serializers.ValidationError(f"unknown categories: {', '.join(bad)}")
        # Preserve a stable order and dedupe.
        order = ("papers", "grants", "fellowships", "conferences")
        return [c for c in order if c in out]

    def update(self, instance: Project, validated: dict) -> Project:
        if "name" in validated:
            instance.name = validated["name"]
        if "focus" in validated:
            instance.goals = apply_focus(instance.goals, validated["focus"] or {})

        goals = dict(instance.goals if isinstance(instance.goals, dict) else {})
        for field in ("description", "status"):
            if field in validated:
                text = (validated[field] or "").strip()
                if text:
                    goals[field] = text
                else:
                    goals.pop(field, None)
        if "progress" in validated:
            if validated["progress"] is None:
                goals.pop("progress", None)
            else:
                goals["progress"] = validated["progress"]
        if "watch_categories" in validated:
            goals["watch_categories"] = validated["watch_categories"]
        instance.goals = goals
        if "visibility" in validated:
            instance.visibility = validated["visibility"]
        if "aliases" in validated:
            name = instance.name.casefold()
            instance.aliases = [
                alias for alias in validated["aliases"] if alias.casefold() != name
            ]

        instance.save()
        return instance
