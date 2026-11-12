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
    return row.role if row else None


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


def visible_queryset(user, *, kind: str | None = None, owner=None):
    from .models import StoredFile

    rows = StoredFile.objects.filter(deleted_at__isnull=True)
    if kind and owner is not None:
        rows = rows.filter(**{OWNER_KINDS[kind]: owner})
    return [
        f
        for f in rows.select_related("owner_project", "owner_lab", "owner_department")
        if can_see(user, f)
    ]


def output_width(stored) -> str:
    """The widest audience a file may be shown to (the agent's audience rule)."""
    kind = stored.owner_kind
    if kind == "user":
        return "person"
    if kind == "project":
        from apps.research import visibility

        return visibility.output_width(stored.owner)
    return kind
