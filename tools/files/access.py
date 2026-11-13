"""Who may add, see and delete a stored file.

* see: the uploader always; for an org- or project-owned file everyone who can
  see the owner; for a personal file nobody else;
* add: to yourself; to a project you can edit; to a lab or department where
  you are at least ``member``;
* delete: the uploader, or an owner or admin of the owning lab or department,
  or an editor of the owning project.
"""

from __future__ import annotations

from .models import OWNER_KINDS


def get_owner(kind: str, owner_id):
    from apps.accounts.models import Department, Lab
    from apps.research.models import Project
    from django.contrib.auth.models import User

    model = {
        "user": User,
        "lab": Lab,
        "department": Department,
        "project": Project,
    }.get(kind)
    if model is None:
        return None
    try:
        if kind == "lab" and not str(owner_id).isdigit():
            return Lab.objects.filter(slug=str(owner_id)).first()
        return model.objects.filter(pk=owner_id).first()
    except Exception:  # a malformed id is simply not found
        return None


def _lab_role(user, lab):
    from apps.accounts.models import LabMembership

    row = LabMembership.objects.filter(user=user, lab=lab).first()
    if row is None:
        return None
    # A lead PI holds every right an admin does (settings plan, decision 13).
    if row.is_lead and row.role not in ("owner", "admin"):
        return "admin"
    return row.role


def _dept_role(user, dept):
    from apps.accounts.models import DeptMembership
    from apps.accounts.permissions import user_has_department_access

    if dept.owner_id == user.id:
        return "owner"
    row = DeptMembership.objects.filter(user=user, department=dept).first()
    if row:
        return row.role
    return "member" if user_has_department_access(user, dept) else None


def can_see_owner(user, kind: str, owner) -> bool:
    if owner is None:
        return False
    if kind == "user":
        return owner.pk == user.pk
    if kind == "lab":
        return _lab_role(user, owner) is not None
    if kind == "department":
        return _dept_role(user, owner) is not None
    if kind == "project":
        return not owner.is_archived and owner.is_visible_to(user)
    return False


def can_add(user, kind: str, owner) -> bool:
    from apps.research.permissions import user_can_edit_project

    if owner is None:
        return False
    if kind == "user":
        return owner.pk == user.pk
    if kind == "lab":
        return _lab_role(user, owner) in ("member", "admin", "owner")
    if kind == "department":
        return _dept_role(user, owner) in ("member", "admin", "owner")
    if kind == "project":
        return not owner.is_archived and user_can_edit_project(user, owner)
    return False


def can_see(user, stored) -> bool:
    if stored.deleted_at is not None:
        return False
    if stored.uploaded_by_id == user.pk:
        return True
    kind = stored.owner_kind
    if kind == "user":
        return stored.owner_user_id == user.pk
    return can_see_owner(user, kind, stored.owner)


def can_delete(user, stored) -> bool:
    from apps.research.permissions import user_can_edit_project

    if stored.uploaded_by_id == user.pk:
        return True
    kind = stored.owner_kind
    if kind == "user":
        return stored.owner_user_id == user.pk
    if kind == "lab":
        return _lab_role(user, stored.owner) in ("admin", "owner")
    if kind == "department":
        return _dept_role(user, stored.owner) in ("admin", "owner")
    if kind == "project":
        return user_can_edit_project(user, stored.owner)
    return False


def visible_q(user):
    """:func:`can_see` as one SQL condition, so listing files never loads every
    file on the instance to test each in Python."""
    from apps.accounts.models import DeptMembership, LabMembership
    from apps.research.models import Project
    from django.db.models import Q

    if not getattr(user, "is_authenticated", False):
        return Q(pk__in=[])
    labs = LabMembership.objects.filter(user=user)
    return (
        Q(uploaded_by=user)
        | Q(owner_user=user)
        | Q(owner_lab__in=labs.values("lab_id"))
        # a department: its owner, a direct member, or a member of one of its labs
        | Q(owner_department__owner=user)
        | Q(
            owner_department__in=DeptMembership.objects.filter(user=user).values(
                "department_id"
            )
        )
        | Q(
            owner_department__in=labs.filter(lab__department__isnull=False).values(
                "lab__department_id"
            )
        )
        | Q(
            owner_project__in=Project.objects.visible_to(user)
            .filter(is_archived=False)
            .values("pk")
        )
    )


def visible_queryset(user, *, kind: str | None = None, owner=None, q: str = ""):
    """The files ``user`` may see (optionally of one owner, or whose name
    contains ``q``), filtered in the database."""
    from .models import StoredFile

    rows = StoredFile.objects.filter(deleted_at__isnull=True).filter(visible_q(user))
    if kind and owner is not None:
        rows = rows.filter(**{OWNER_KINDS[kind]: owner})
    if q:
        rows = rows.filter(filename__icontains=q)
    return list(rows.select_related("owner_project", "owner_lab", "owner_department"))


def output_width(stored) -> str:
    """The widest audience a file may be shown to (the agent's audience rule)."""
    kind = stored.owner_kind
    if kind == "user":
        return "person"
    if kind == "project":
        project = stored.owner
        if project.scope_user_id is not None:
            return "person"
        return (
            "lab"
            if project.share_in_lab_reports and project.scope_lab_id
            else "project"
        )
    return kind
