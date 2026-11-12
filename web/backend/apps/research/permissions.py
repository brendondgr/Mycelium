"""Who may do what to a project. Shared by the project views and the Mylo
agent's permission gate, so the two can never disagree."""

from __future__ import annotations

from apps.accounts.permissions import (
    user_can_edit_dept_profile,
    user_can_edit_lab_profile,
)

from .models import Project, ProjectMember

#: Member roles that carry edit authority on a project.
EDIT_ROLES = (ProjectMember.Role.OWNER, ProjectMember.Role.EDITOR)


def user_can_edit_project(user, project: Project) -> bool:
    """Who may edit a project's fundamentals, membership, and archive state.

    The personal owner edits their own project; a lab's owner, admin, or lead PI
    edits that lab's projects — the same authority that creates them
    (:func:`user_can_edit_lab_profile`). It used to be owner/admin only here, which
    left a PI holding edit controls the API then refused. A department's owner or
    admin edits that department's projects — the same authority that creates them
    (:func:`user_can_edit_dept_profile`); without it a department project was
    stranded the moment it was made.

    A member holding the ``owner`` or ``editor`` role edits the project too,
    whatever its scope.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if project.scope_user_id is not None and project.scope_user_id == user.id:
        return True
    if ProjectMember.objects.filter(
        project=project, user=user, role__in=EDIT_ROLES
    ).exists():
        return True
    return user_manages_project_scope(user, project)


def user_manages_project_scope(user, project: Project) -> bool:
    """The scope's own managers: a lab's owner, admin or PI for a lab project,
    a department's owner or admin for a department project. They hold a
    project's owner authority whether or not it has an owner row, and may take
    ownership (plan "Oversight")."""
    if not getattr(user, "is_authenticated", False):
        return False
    if project.scope_user_id is not None:
        return False
    if project.scope_lab_id is not None:
        return user_can_edit_lab_profile(user, project.scope_lab)
    if project.scope_department_id is not None:
        return user_can_edit_dept_profile(user, project.scope_department)
    return False


def user_can_change_visibility(user, project: Project) -> bool:
    """Only the owner changes a project's scope: its owner-role member, a
    personal project's own user, or the scope's managers acting as owner."""
    if not getattr(user, "is_authenticated", False):
        return False
    if project.scope_user_id is not None:
        return project.scope_user_id == user.id
    if ProjectMember.objects.filter(
        project=project, user=user, role=ProjectMember.Role.OWNER
    ).exists():
        return True
    return user_manages_project_scope(user, project)
