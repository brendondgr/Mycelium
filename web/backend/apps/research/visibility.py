"""Who may see a project, whose project it is, and where it may be mentioned.

A project carries one scope, ``Project.visibility``, and this module is the only
place that reads it. It answers three questions that used to be answered in a
dozen places, each slightly differently:

1. **Can this person see the project exists?** :func:`can_see` (queryset form
   :func:`visible_q`): a member, the personal owner, anyone inside the scope, or
   an overseer. Knowing it exists is a directory row, not the project: only a
   member, the personal owner or an overseer may **open** it (:func:`can_open`,
   queryset form :func:`open_q`, behind ``Project.objects.visible_to``), which
   is what every route returning a full project row checks.
2. **Is it one of this person's projects?** :func:`is_participant`: only a member
   or the personal owner. Visibility and oversight never put a project in
   someone's project list, personal report or attention shares.
3. **May this surface mention it?** :func:`may_surface`: only when the surface's
   audience is no wider than :func:`audience`.

Oversight: a lab's PI, owner and admins see every project of the lab whatever
its scope. A department's owner and admins see every department project, and
every project of each of its labs whose PI left *What the department sees* on
**Everything**; a lab set to **Names only** shows them only the reduced row
(:func:`names_only_for`). Seeing is not belonging, and oversight never widens
where Mylo may mention a project.

Nothing outside this module filters projects on ``visibility`` or queries a
lab's projects with a raw ``scope_lab=`` filter; ``test_visibility_guard``
enforces that.
"""

from __future__ import annotations

from django.db.models import Q

from .models import HEAD_ROLES, Project, ProjectMember, Visibility

INVITE_ONLY = Visibility.INVITE_ONLY
LAB = Visibility.LAB
DEPARTMENT = Visibility.DEPARTMENT
PUBLIC = Visibility.PUBLIC

#: Scopes whose audience includes every member of the owning lab.
LAB_WIDE = (LAB, DEPARTMENT, PUBLIC)
#: Scopes whose audience includes the department.
DEPARTMENT_WIDE = (DEPARTMENT, PUBLIC)

#: Audience widths, narrowest first. A place has one; a project's audience is
#: the widest place it may appear in.
WIDTHS = ("member", "lab", "department", "public")
_AUDIENCE = {
    INVITE_ONLY: "member",
    LAB: "lab",
    DEPARTMENT: "department",
    PUBLIC: "public",
}


# -- question 1: can this person see it ----------------------------------------


def _user_scopes(user) -> dict:
    """The ids that decide what ``user`` sees: labs they belong to, labs they
    head, departments they are in, departments they head, and whether they are
    a verified account."""
    from apps.accounts.models import Department, DeptMembership, Lab, LabMembership
    from apps.accounts.permissions import user_email_verified

    lab_rows = list(
        LabMembership.objects.filter(user=user).values_list(
            "lab_id", "role", "is_lead", "lab__department_id"
        )
    )
    member_labs = {lab_id for lab_id, _, _, _ in lab_rows}
    head_labs = {
        lab_id for lab_id, role, lead, _ in lab_rows if lead or role in HEAD_ROLES
    }
    head_depts = set(
        Department.objects.filter(owner=user).values_list("id", flat=True)
    ) | set(
        DeptMembership.objects.filter(user=user, role__in=HEAD_ROLES).values_list(
            "department_id", flat=True
        )
    )
    # Effective department membership: direct members, the owner, and the
    # members of every lab in the department.
    member_depts = (
        head_depts
        | set(
            DeptMembership.objects.filter(user=user).values_list(
                "department_id", flat=True
            )
        )
        | {dept for _, _, _, dept in lab_rows if dept is not None}
    )
    overseen_labs = set(
        Lab.objects.filter(
            department_id__in=head_depts,
            department_sees=Lab.DepartmentSees.EVERYTHING,
        ).values_list("id", flat=True)
    )
    return {
        "member_labs": member_labs,
        "head_labs": head_labs,
        "head_depts": head_depts,
        "member_depts": member_depts,
        "overseen_labs": overseen_labs,
        "verified": user_email_verified(user),
    }


def _open_q(user, s: dict) -> Q:
    """Members, the personal owner, and the overseers."""
    member_of = ProjectMember.objects.filter(user=user).values("project_id")
    return (
        Q(id__in=member_of)
        | Q(scope_user=user)
        # Oversight: the lab's PI / owner / admins, and department heads over a
        # lab that shows its department everything, or over a department project.
        | Q(scope_lab_id__in=s["head_labs"] | s["overseen_labs"])
        | Q(scope_department_id__in=s["head_depts"])
    )


def open_q(user) -> Q | None:
    """The filter for projects ``user`` may **open** — the full row, goals,
    roster, feed and files: a member, the personal owner, or an overseer.
    ``None`` for nobody. This is what ``Project.objects.visible_to`` returns.

    Being inside a project's scope is not enough to open it: the scope's people
    see the project *exists* (:func:`visible_q`), which Phase 2's directory
    shows as a reduced row (name, focus, owner, member count) with a request to
    join. Otherwise a ``public`` project would land, goals and files included,
    in every verified account's project list."""
    if not getattr(user, "is_authenticated", False):
        return None
    return _open_q(user, _user_scopes(user))


def visible_q(user) -> Q | None:
    """The filter for projects ``user`` can see **exist**: everything they may
    open, plus every project whose scope includes them. ``None`` for nobody.
    For directory rows only — never a reason to return a full project row."""
    if not getattr(user, "is_authenticated", False):
        return None
    s = _user_scopes(user)
    query = (
        _open_q(user, s)
        # Scope: the lab's members, the department's effective members.
        | Q(scope_lab_id__in=s["member_labs"], visibility__in=LAB_WIDE)
        | Q(
            scope_lab__department_id__in=s["member_depts"],
            visibility__in=DEPARTMENT_WIDE,
        )
        | Q(
            scope_department_id__in=s["member_depts"],
            visibility__in=DEPARTMENT_WIDE,
        )
    )
    if s["verified"]:
        query |= Q(visibility=PUBLIC)
    return query


def can_see(user, project: Project) -> bool:
    """Whether ``user`` may know ``project`` exists (a directory row)."""
    query = visible_q(user)
    if query is None:
        return False
    return Project.objects.filter(query, pk=project.pk).exists()


def can_open(user, project: Project) -> bool:
    """Whether ``user`` may open ``project`` (the full row)."""
    query = open_q(user)
    if query is None:
        return False
    return Project.objects.filter(query, pk=project.pk).exists()


def openable_ids(user, ids) -> set:
    """The ids among ``ids`` that ``user`` may open (one query)."""
    query = open_q(user)
    if query is None:
        return set()
    return set(
        Project.objects.filter(query, id__in=list(ids)).values_list("id", flat=True)
    )


def admits_requests(project: Project) -> bool:
    """Whether the project's scope lets someone ask to join it. An
    ``invite_only`` project is joined by invitation only."""
    return project.visibility != INVITE_ONLY


# -- the directory -------------------------------------------------------------


def directory(user, *, lab=None, department=None):
    """Projects ``user`` can see exist but is not on: the directory ("Projects
    in this lab" / "…in this department" / everything public on the instance).

    Built on :func:`visible_q`, so an ``invite_only`` project shows only to its
    overseers, never to an ordinary member of the lab. A directory row is the
    reduced one (name, focus line, owner, member count) — never goals, state,
    feed, files or roster. Projects the caller is on are their own list
    ("My projects"), not the directory; archived projects are left out.
    """
    query = visible_q(user)
    if query is None:
        return Project.objects.none()
    qs = Project.objects.filter(query, is_archived=False)
    if lab is not None:
        qs = qs.filter(scope_lab=lab)
    elif department is not None:
        qs = qs.filter(
            Q(scope_department=department) | Q(scope_lab__department=department)
        )
    mine = ProjectMember.objects.filter(user=user).values("project_id")
    return qs.exclude(id__in=mine).exclude(scope_user=user).distinct()


def scope_people_ids(project: Project) -> set | None:
    """The user ids who belong to the project's home: the lab's members for a
    lab project, the department's effective members for a department project.
    ``None`` for a personal project, which has no home to be outside of.

    A project member not in this set is an **outside collaborator**: they see
    that one project and gain nothing else in the lab."""
    from apps.accounts.models import LabMembership
    from apps.accounts.services import effective_member_ids

    if project.scope_lab_id is not None:
        return set(
            LabMembership.objects.filter(lab_id=project.scope_lab_id).values_list(
                "user_id", flat=True
            )
        )
    if project.scope_department_id is not None:
        department = project.scope_department
        return set(effective_member_ids(department)) | {department.owner_id}
    return None


def visible_in_lab(user, lab):
    """The projects of ``lab`` that ``user`` may open."""
    return Project.objects.visible_to(user).filter(scope_lab=lab)


def visible_in_lab_slug(queryset, slug: str):
    """Narrow an already-visible queryset to one lab's projects, by slug."""
    return queryset.filter(scope_lab__slug=slug)


# -- question 2: is it one of this person's projects ---------------------------


def is_participant(user, project: Project) -> bool:
    """A member or the personal owner — never an overseer or a scope reader."""
    if not getattr(user, "is_authenticated", False):
        return False
    if project.scope_user_id is not None and project.scope_user_id == user.id:
        return True
    return ProjectMember.objects.filter(project=project, user=user).exists()


def member_role(user, project: Project) -> str | None:
    """``user``'s :class:`ProjectMember` role on ``project``, or ``None``."""
    if not getattr(user, "is_authenticated", False):
        return None
    return (
        ProjectMember.objects.filter(project=project, user=user)
        .values_list("role", flat=True)
        .first()
    )


# -- question 3: may this surface mention it -----------------------------------


def audience(project: Project) -> str:
    """The widest place ``project`` may be mentioned in (one of :data:`WIDTHS`)."""
    return _AUDIENCE.get(project.visibility, "member")


def place_width(place) -> str:
    """The width of ``place``: a width string, or anything carrying ``.width``
    (``apps.integrations.services.resolve.Place``, built with the server-width
    rule), or an agent audience width (``person`` … ``instance``)."""
    width = getattr(place, "width", place)
    return _AGENT_PLACE.get(width, width)


#: The agent's audience widths, as place widths.
_AGENT_PLACE = {
    "person": "member",
    "project": "member",
    "instance": "public",
}


def may_surface(project: Project, place) -> bool:
    """Whether a place of width ``place`` may mention ``project``: only when the
    project's audience is at least as wide as the place.

    ``place`` is a width (:data:`WIDTHS`) or a ``resolve.Place``. A Discord
    server's width is decided by everything bound in it
    (``resolve.server_width``), never by which binding a post travels on. An
    unknown width allows nothing.
    """
    width = place_width(place)
    if width not in WIDTHS:
        return False
    return WIDTHS.index(audience(project)) >= WIDTHS.index(width)


def scopes_for_width(width: str) -> tuple[str, ...]:
    """The scopes a place of ``width`` may name (an unknown width: none)."""
    width = place_width(width)
    if width not in WIDTHS:
        return ()
    rank = WIDTHS.index(width)
    return tuple(
        scope for scope, aud in _AUDIENCE.items() if WIDTHS.index(aud) >= rank
    )


def output_width(project: Project) -> str:
    """The widest Mylo-chat audience (``person`` / ``project`` / ``lab`` /
    ``department`` / ``public``) a project may be shown to, from its scope.

    A personal project stays with its person unless it is ``public``. A
    department-scoped lab project is ``department``; a lab project in a lab
    with no department cannot be ``department`` (the scope picker does not
    offer it), and is held to ``lab`` if it ever is.
    """
    width = audience(project)
    if width == "public":
        return "public"
    if project.scope_user_id is not None:
        return "person"
    if width == "member":
        return "project"
    if width == "lab":
        return "lab" if project.scope_lab_id is not None else "project"
    if project.scope_department_id is not None:
        return "department"
    return "department" if project.scope_lab.department_id else "lab"


def surface_q(width: str = "lab", prefix: str = "") -> Q:
    """Filter (on a project, or through ``prefix`` on a relation to one) for a
    scope a place of ``width`` may name."""
    return Q(**{f"{prefix}visibility__in": scopes_for_width(width)})


def lab_surface_q(prefix: str = "") -> Q:
    """Filter (on a project, or through ``prefix`` on a relation to one) for a
    scope wide enough for the owning lab's shared surfaces."""
    return surface_q("lab", prefix)


def lab_surface_projects(labs, width: str = "lab"):
    """Projects of ``labs`` (one lab, or ids) that the lab's own surfaces —
    overview, daily post, PDF, weekly, alerts, announcement teams — may name.

    ``width`` is the place's: ``lab`` for the lab's web surfaces and its own
    server, wider when the post lands in a server holding more than the lab
    (``resolve.lab_post_width``). Never narrower than ``lab``: a lab surface is
    read by the whole lab."""
    if width not in WIDTHS or WIDTHS.index(width) < WIDTHS.index("lab"):
        width = "lab"
    return lab_projects(labs).filter(surface_q(width))


def lab_held_back(lab, width: str = "lab"):
    """Projects of ``lab`` its shared surfaces of ``width`` leave out."""
    if width not in WIDTHS or WIDTHS.index(width) < WIDTHS.index("lab"):
        width = "lab"
    return lab_projects(lab).exclude(surface_q(width))


def lab_projects(labs):
    """Every project of ``labs`` (one lab, or an iterable of ids), whatever its
    scope. For counting, scoring and editing — never for showing to a lab."""
    if hasattr(labs, "pk"):
        return Project.objects.filter(scope_lab=labs)
    return Project.objects.filter(scope_lab_id__in=labs)


def too_narrow_for(width: str, *, lab_id=None, department_id=None):
    """Projects of a lab (or of a department and its labs) that a place of
    ``width`` may **not** name — what a check of that place looks for."""
    if lab_id is not None:
        owned = Q(scope_lab_id=lab_id)
    else:
        owned = Q(scope_department_id=department_id) | Q(
            scope_lab__department_id=department_id
        )
    return Project.objects.filter(owned).exclude(surface_q(width))


def department_surface_projects(department, width: str = "department"):
    """Projects a department's own surfaces may name: its own and its labs',
    scoped to the department or wider (``public`` only, for a ``public``
    place)."""
    if width not in WIDTHS or WIDTHS.index(width) < WIDTHS.index("department"):
        width = "department"
    return Project.objects.filter(
        Q(scope_department=department) | Q(scope_lab__department=department),
        surface_q(width),
    )


def allowed_visibilities(project: Project) -> tuple[str, ...]:
    """The scopes this project may take."""
    if project.scope_lab_id is not None:
        if project.scope_lab.department_id is not None:
            return (INVITE_ONLY, LAB, DEPARTMENT, PUBLIC)
        return (INVITE_ONLY, LAB, PUBLIC)
    if project.scope_department_id is not None:
        return (INVITE_ONLY, DEPARTMENT, PUBLIC)
    return (INVITE_ONLY, PUBLIC)


# -- oversight: names only -----------------------------------------------------


def names_only_for(user, department):
    """Projects of ``department``'s labs whose names ``user`` (a head of it) may
    see but not open: the labs set to *Names only*, minus anything their own
    scope already shows them."""
    from apps.accounts.models import Lab
    from apps.accounts.permissions import user_can_edit_dept_profile

    if not user_can_edit_dept_profile(user, department):
        return Project.objects.none()
    return Project.objects.filter(
        scope_lab__department=department,
        scope_lab__department_sees=Lab.DepartmentSees.NAMES_ONLY,
    ).exclude(id__in=Project.objects.visible_to(user).values("id"))


def department_projects_visible(user, department):
    """Projects of ``department`` and its labs that ``user`` may open."""
    return Project.objects.visible_to(user).filter(
        Q(scope_department=department) | Q(scope_lab__department=department)
    )


def owner_of(project: Project):
    """The project's owner: its owner-role member, else a personal project's
    user, else ``None`` (the lab's or department's managers act for it)."""
    row = (
        ProjectMember.objects.filter(project=project, role=ProjectMember.Role.OWNER)
        .select_related("user")
        .first()
    )
    if row is not None:
        return row.user
    return project.scope_user if project.scope_user_id is not None else None
