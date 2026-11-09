"""Reference kinds the agent owns: corpus items, projects, labs, departments
and people. Each resolver returns ``None`` both for a missing object and for
one the caller may not see."""

from __future__ import annotations

import uuid

from . import common


def _uuid(key: str):
    return uuid.UUID(str(key))


def resolve_item(caller, key):
    from tools.retrieval.read import ContentItem

    item = ContentItem.objects.filter(pk=_uuid(key)).first()
    return common.item_info(item) if item else None


def search_items(caller, q, limit):
    from tools.retrieval.read import run_search

    result = run_search(q, limit=limit)
    return [common.item_info(item) for item in result.items]


def resolve_project(caller, key):
    from apps.research.models import Project

    project = Project.objects.filter(pk=_uuid(key)).first()
    if project is None or project.is_archived or not project.is_visible_to(caller.user):
        return None
    return common.project_info(project)


def search_projects(caller, q, limit):
    from apps.research.models import Project

    rows = Project.objects.visible_to(caller.user).filter(
        is_archived=False, name__icontains=q
    )[:limit]
    return [common.project_info(p) for p in rows]


def resolve_lab(caller, key):
    from apps.accounts.models import Lab
    from apps.accounts.permissions import user_has_lab_access

    lab = Lab.objects.filter(slug=str(key)).first()
    if lab is None or not user_has_lab_access(caller.user, lab):
        return None
    return common.lab_info(lab)


def search_labs(caller, q, limit):
    from apps.accounts.models import Lab

    rows = Lab.objects.filter(memberships__user=caller.user, name__icontains=q)[:limit]
    return [common.lab_info(lab) for lab in rows]


def resolve_department(caller, key):
    from apps.accounts.models import Department
    from apps.accounts.permissions import user_has_department_access

    dept = Department.objects.filter(pk=_uuid(key)).first()
    if dept is None or not user_has_department_access(caller.user, dept):
        return None
    return common.department_info(dept)


def visible_people(user):
    """People this person may see: themselves, their labs' and departments'
    members, and their projects' members."""
    from apps.accounts.models import DeptMembership, LabMembership
    from apps.research.models import Project
    from django.contrib.auth.models import User
    from django.db.models import Q

    lab_ids = LabMembership.objects.filter(user=user).values_list("lab_id", flat=True)
    dept_ids = DeptMembership.objects.filter(user=user).values_list(
        "department_id", flat=True
    )
    project_ids = Project.objects.visible_to(user).values_list("id", flat=True)
    return User.objects.filter(
        Q(pk=user.pk)
        | Q(lab_memberships__lab_id__in=lab_ids)
        | Q(dept_memberships__department_id__in=dept_ids)
        | Q(project_memberships__project_id__in=project_ids)
    ).distinct()


def resolve_person(caller, key):
    person = visible_people(caller.user).filter(username=str(key)).first()
    return common.person_info(person, caller=caller) if person else None


def search_people(caller, q, limit):
    from django.db.models import Q

    rows = visible_people(caller.user).filter(
        Q(username__icontains=q)
        | Q(first_name__icontains=q)
        | Q(last_name__icontains=q)
    )[:limit]
    return [common.person_info(p, caller=caller) for p in rows]
