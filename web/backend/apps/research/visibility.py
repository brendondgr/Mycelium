"""Who may see a project, whose project it is, and where it may be mentioned.

A project carries one scope, ``Project.visibility``, and this module is the only
place that reads it. It answers three questions that used to be answered in a
dozen places, each slightly differently:

1. **Can this person see the project exists?** :func:`can_see` (and its queryset
   form :func:`visible_q`, behind ``Project.objects.visible_to``): a member, the
   personal owner, anyone inside the scope, or an overseer.
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


def visible_q(user) -> Q | None:
    """The filter for projects ``user`` can see, or ``None`` for nobody."""
    if not getattr(user, "is_authenticated", False):
        return None
    s = _user_scopes(user)
    member_of = ProjectMember.objects.filter(user=user).values("project_id")
    query = (
        Q(id__in=member_of)
        | Q(scope_user=user)
        # Oversight: the lab's PI / owner / admins, and department heads over a
        # lab that shows its department everything, or over a department project.
        | Q(scope_lab_id__in=s["head_labs"] | s["overseen_labs"])
        | Q(scope_department_id__in=s["head_depts"])
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
    """Whether ``user`` may open ``project``."""
    query = visible_q(user)
    if query is None:
        return False
    return Project.objects.filter(query, pk=project.pk).exists()


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


def may_surface(project: Project, place: str) -> bool:
    """Whether a place of width ``place`` may mention ``project``.

    Phase 3 builds ``place`` from where Mylo is speaking (the server-width rule);
    until then callers pass the width of their own surface.
    """
    if place not in WIDTHS:
        return False
    return WIDTHS.index(audience(project)) >= WIDTHS.index(place)


def output_width(project: Project) -> str:
    """The widest Mylo-chat audience (``person`` / ``project`` / ``lab`` /
    ``department``) a project may be shown to, from its scope.

    The agent has no ``public`` width until Phase 3 adds one, so a wider scope
    is held to the widest width the agent knows for the project's home. A
    personal project stays with its person.
    """
    if project.scope_user_id is not None:
        return "person"
    width = audience(project)
    if width == "member":
        return "project"
    if project.scope_department_id is not None:
        return "department"
    if width == "lab":
        return "lab"
    return "department" if project.scope_lab.department_id else "lab"


def lab_surface_q(prefix: str = "") -> Q:
    """Filter (on a project, or through ``prefix`` on a relation to one) for a
    scope wide enough for the owning lab's shared surfaces."""
    return Q(**{f"{prefix}visibility__in": LAB_WIDE})


def lab_surface_projects(labs):
    """Projects of ``labs`` (one lab, or ids) that the lab's own surfaces —
    overview, daily post, PDF, weekly, alerts, announcement teams — may name."""
    return lab_projects(labs).filter(lab_surface_q())


def lab_held_back(lab):
    """Projects of ``lab`` its shared surfaces leave out (narrower than lab)."""
    return lab_projects(lab).exclude(lab_surface_q())


def lab_projects(labs):
    """Every project of ``labs`` (one lab, or an iterable of ids), whatever its
    scope. For counting, scoring and editing — never for showing to a lab."""
    if hasattr(labs, "pk"):
        return Project.objects.filter(scope_lab=labs)
    return Project.objects.filter(scope_lab_id__in=labs)


def department_surface_projects(department):
    """Projects a department's own surfaces may name: its own and its labs',
    scoped to the department or wider."""
    return Project.objects.filter(
        Q(scope_department=department) | Q(scope_lab__department=department),
        visibility__in=DEPARTMENT_WIDE,
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
