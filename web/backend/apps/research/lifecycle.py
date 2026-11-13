"""Changing a project's scope, handing it over, and leaving (scoping plan, Phase 5).

* **Narrowing** takes effect on everything not yet sent: every stored row is
  re-checked at read (``apps.research.visibility``), so nothing here deletes
  history. Open announcement threads drop the project's team on their next
  update (``tools.delivery.discord_announcements``).
* **Widening** is the owner's alone and every member is told; it applies from
  the next run and nothing historical is back-posted.
* **Leaving a lab** ends membership in that lab's projects; an owner who leaves
  (or deletes their account) hands the project to an editor, else the lab's PI
  (the department head for a department project).
* **A lab leaving its department**: its ``department`` projects fall back to
  ``lab`` and their owners are told. Before leaving, a project may be
  **transferred** to the department — the owner offers, a department head
  accepts, and it becomes a department project with its members kept.

Every rule here is called from a signal or a view; nothing reads
``Project.visibility`` directly except through :mod:`.visibility`.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from . import visibility
from .models import Project, ProjectMember, ProjectTransfer

logger = logging.getLogger(__name__)


# -- telling people ------------------------------------------------------------


def tell(users, *, key: str, title: str, body: str = "") -> int:
    """Put one line on each user's bell. Best-effort: the change already stands."""
    from tools.delivery.models import Notification

    told = 0
    for user in {u.pk: u for u in users if u is not None}.values():
        try:
            _row, created = Notification.objects.get_or_create(
                dedupe_key=f"{key}:{user.pk}"[:200],
                defaults={
                    "user": user,
                    "kind": Notification.Kind.PROJECT_SCOPE,
                    "title": title[:500],
                    "body": body,
                },
            )
            told += int(created)
        except Exception:  # noqa: BLE001 - the bell is a courtesy
            logger.warning("project notification %s failed", key, exc_info=True)
    return told


def _members(project: Project) -> list:
    return [row.user for row in project.memberships.select_related("user")]


# -- changing scope ------------------------------------------------------------


def is_widening(old: str, new: str) -> bool:
    return visibility.WIDTHS.index(
        visibility.audience_of(new)
    ) > visibility.WIDTHS.index(visibility.audience_of(old))


def scope_changed(project: Project, old: str, *, actor=None) -> dict:
    """After the owner saved a new scope: on a widening, tell every member who
    newly sees it. Returns what was said."""
    # The save itself re-projects the concepts (``apps.knowledge.signals``).
    new = project.visibility
    if new == old:
        return {}
    if not is_widening(old, new):
        return {"widened": False}
    newly = visibility.newly_seen_by(project, old)
    told = tell(
        [u for u in _members(project) if actor is None or u.pk != actor.pk],
        key=f"project-scope:{project.pk}:{old}:{new}:{timezone.now():%Y%m%d%H%M}",
        title=f"{project.name} is now visible to {newly}",
        body=(
            f"Its owner widened who can see it. From the next run Mylo may "
            f"mention it to {newly}; nothing already sent is posted again."
        ),
    )
    return {"widened": True, "newly_visible_to": newly, "told": told}


# -- ownership -----------------------------------------------------------------


def successor(project: Project, *, leaving=None):
    """Who owns a project after its owner goes: an editor (the longest-serving),
    else the lab's PI, else the department's owner. ``None`` when nobody is left,
    and then the scope's managers hold the owner's authority, as they always
    did."""
    from apps.accounts.models import LabMembership

    exclude = {leaving.pk} if leaving is not None else set()
    editor = (
        project.memberships.filter(role=ProjectMember.Role.EDITOR)
        .exclude(user_id__in=exclude)
        .order_by("created_at", "pk")
        .select_related("user")
        .first()
    )
    if editor is not None:
        return editor.user
    if project.scope_lab_id is not None:
        pi = (
            LabMembership.objects.filter(lab_id=project.scope_lab_id)
            .exclude(user_id__in=exclude)
            .order_by("-is_lead", "pk")
            .filter(is_lead=True)
            .select_related("user")
            .first()
        ) or (
            LabMembership.objects.filter(
                lab_id=project.scope_lab_id, role=LabMembership.Role.OWNER
            )
            .exclude(user_id__in=exclude)
            .select_related("user")
            .first()
        )
        return pi.user if pi is not None else None
    if project.scope_department_id is not None:
        owner = project.scope_department.owner
        return owner if owner is not None and owner.pk not in exclude else None
    return None


def make_owner(
    project: Project, user, *, actor=None, reason: str, leaving=None
) -> None:
    """Give ``user`` the owner row (the old owner becomes an editor), audited,
    and tell the members."""
    from apps.accounts.services import record_audit_event

    with transaction.atomic():
        previous = list(
            project.memberships.select_for_update()
            .filter(role=ProjectMember.Role.OWNER)
            .exclude(user=user)
        )
        for row in previous:
            row.role = ProjectMember.Role.EDITOR
            row.save(update_fields=["role"])
        row, created = ProjectMember.objects.get_or_create(
            project=project, user=user, defaults={"role": ProjectMember.Role.OWNER}
        )
        if not created and row.role != ProjectMember.Role.OWNER:
            row.role = ProjectMember.Role.OWNER
            row.save(update_fields=["role"])
        record_audit_event(
            actor=actor,
            action="project.ownership",
            target_type="project",
            target_id=str(project.id),
            metadata={
                "to_user_id": user.pk,
                "from_user_ids": [r.user_id for r in previous],
                "reason": reason,
            },
        )
    tell(
        [m for m in _members(project) if leaving is None or m.pk != leaving.pk],
        key=f"project-owner:{project.pk}:{user.pk}:{timezone.now():%Y%m%d%H%M%S}",
        title=f"{project.name} has a new owner",
        body=f"{user.get_full_name() or user.get_username()} now owns it ({reason}).",
    )


def hand_over_if_owner(project: Project, leaving, *, actor=None) -> bool:
    """When ``leaving`` owns ``project``, pass it on (:func:`successor`)."""
    if not ProjectMember.objects.filter(
        project=project, user=leaving, role=ProjectMember.Role.OWNER
    ).exists():
        return False
    heir = successor(project, leaving=leaving)
    if heir is None:
        return False
    make_owner(
        project, heir, actor=actor, reason="the previous owner left", leaving=leaving
    )
    return True


# -- leaving -------------------------------------------------------------------


def end_lab_project_memberships(lab_id, user, *, actor=None) -> int:
    """Leaving (or being removed from) a lab ends membership in its projects.
    The project's owner may invite them back as an outside collaborator."""
    ended = 0
    for project in (
        visibility.lab_projects([lab_id]).filter(memberships__user=user).distinct()
    ):
        hand_over_if_owner(project, user, actor=actor)
        ended += ProjectMember.objects.filter(project=project, user=user).delete()[0]
    return ended


def account_leaving(user) -> int:
    """Before an account is deleted: hand over every project it owns."""
    handed = 0
    for project in Project.objects.filter(
        memberships__user=user, memberships__role=ProjectMember.Role.OWNER
    ).distinct():
        handed += int(hand_over_if_owner(project, user))
    return handed


# -- a lab leaving its department ----------------------------------------------


def lab_left_department(lab, old_department_id, *, actor=None) -> int:
    """A lab left (or changed) its department: its ``department`` projects fall
    back to ``lab`` and their owners are told; open transfer offers to the old
    department lapse."""
    from apps.accounts.services import record_audit_event

    ProjectTransfer.objects.filter(
        project__in=visibility.lab_projects(lab),
        department_id=old_department_id,
        state=ProjectTransfer.State.PENDING,
    ).update(state=ProjectTransfer.State.LAPSED, decided_at=timezone.now())
    fallen = list(visibility.department_scoped_lab_projects(lab))
    for project in fallen:
        project.visibility = visibility.LAB
        project.save(update_fields=["visibility", "updated_at"])
        record_audit_event(
            actor=actor,
            action="project.visibility",
            target_type="project",
            target_id=str(project.id),
            metadata={
                "from": visibility.DEPARTMENT,
                "to": visibility.LAB,
                "reason": "lab left its department",
            },
        )
        owner = visibility.owner_of(project)
        tell(
            [owner],
            key=f"project-fallback:{project.pk}:{old_department_id}",
            title=f"{project.name} is now visible to {lab.name} only",
            body=(
                "Its lab left the department, so the department no longer sees "
                "it and Mylo no longer mentions it there."
            ),
        )
    return len(fallen)


def offer_transfer(project: Project, actor) -> ProjectTransfer:
    """The owner offers a lab project to the lab's department."""
    department_id = project.scope_lab.department_id if project.scope_lab_id else None
    if department_id is None:
        raise ValueError("Only a lab project in a department can be transferred.")
    row, _created = ProjectTransfer.objects.get_or_create(
        project=project,
        state=ProjectTransfer.State.PENDING,
        defaults={"department_id": department_id, "offered_by": actor},
    )
    return row


def accept_transfer(transfer: ProjectTransfer, actor) -> Project:
    """A department head accepts: the project becomes the department's, its
    members kept. A ``lab`` scope has no meaning there, so it becomes
    ``invite_only`` (never wider than the owner chose)."""
    from apps.accounts.services import record_audit_event

    project = transfer.project
    with transaction.atomic():
        old_lab = project.scope_lab_id
        project.scope_lab = None
        project.scope_department_id = transfer.department_id
        if project.visibility == visibility.LAB:
            project.visibility = visibility.INVITE_ONLY
        project.save(
            update_fields=["scope_lab", "scope_department", "visibility", "updated_at"]
        )
        transfer.state = ProjectTransfer.State.ACCEPTED
        transfer.decided_by = actor
        transfer.decided_at = timezone.now()
        transfer.save(update_fields=["state", "decided_by", "decided_at"])
        record_audit_event(
            actor=actor,
            action="project.transfer",
            target_type="project",
            target_id=str(project.id),
            metadata={
                "from_lab": str(old_lab),
                "to_department": str(transfer.department_id),
            },
        )
    tell(
        _members(project),
        key=f"project-transfer:{transfer.pk}",
        title=f"{project.name} now belongs to the department",
        body="Its members are kept; the lab no longer holds it.",
    )
    return project
