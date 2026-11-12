"""Who may do what to a project. Shared by the project views and the Mylo
agent's permission gate, so the two can never disagree."""

from __future__ import annotations

from apps.accounts.permissions import (
    user_can_edit_dept_profile,
    user_can_edit_lab_profile,
)

from .models import Project


def user_can_edit_project(user, project: Project) -> bool:
    """Who may edit a project's fundamentals, membership, and archive state.

    The personal owner edits their own project; a lab's owner, admin, or lead PI
    edits that lab's projects — the same authority that creates them
    (:func:`user_can_edit_lab_profile`). It used to be owner/admin only here, which
    left a PI holding edit controls the API then refused. A department's owner or
    admin edits that department's projects — the same authority that creates them
    (:func:`user_can_edit_dept_profile`); without it a department project was
    stranded the moment it was made.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if project.scope_user_id is not None:
        return project.scope_user_id == user.id
    if project.scope_lab_id is not None:
        return user_can_edit_lab_profile(user, project.scope_lab)
    if project.scope_department_id is not None:
        return user_can_edit_dept_profile(user, project.scope_department)
    return False
