"""Per-plan project caps — the counting + enforcement layer.

:mod:`apps.billing.entitlements` publishes the cap *numbers* per scope; this
module counts a scope's **active (non-archived)** projects and answers whether
another one may be created or unarchived. It lives in ``research`` so ``billing``
stays free of a research import.

A project is a scored target (each active project runs the daily retrieve → fuse
→ LLM-fit pipeline), so the cap is a compute budget: archiving frees a slot, and
a downgrade never deletes anything — the first ``cap`` active projects (oldest
first) stay in budget and the rest read as "over cap" (see :func:`in_cap_ids`).
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.billing.entitlements import (
    department_project_cap,
    lab_project_cap,
    personal_project_cap,
)

from .models import Project


@dataclass(frozen=True)
class ScopeCap:
    """The cap and current active count for one project scope."""

    scope: str  # "user" | "lab" | "department"
    cap: int | None  # None = unlimited
    active: int

    @property
    def has_headroom(self) -> bool:
        return self.cap is None or self.active < self.cap

    @property
    def remaining(self) -> int | None:
        return None if self.cap is None else max(0, self.cap - self.active)


def _active_count(**scope_filter) -> int:
    return Project.objects.active().filter(**scope_filter).count()


def personal_scope_cap(user) -> ScopeCap:
    return ScopeCap(
        "user", personal_project_cap(user), _active_count(scope_user=user)
    )


def lab_scope_cap(lab) -> ScopeCap:
    return ScopeCap("lab", lab_project_cap(lab), _active_count(scope_lab=lab))


def department_scope_cap(department) -> ScopeCap:
    return ScopeCap(
        "department",
        department_project_cap(department),
        _active_count(scope_department=department),
    )


def in_cap_ids(scope_field: str, owner_id, cap: int | None) -> set:
    """The ids of the active projects that fit inside ``cap`` for one owner.

    Oldest-first by ``created_at`` so a downgrade keeps the projects a team has
    had longest and only the newest excess falls out of budget. Used both to
    decide which projects the daily fan-out scores and to flag "over cap" rows in
    the read API. ``cap`` of 0 returns an empty set (org no longer entitled);
    ``None`` (unlimited) returns every active project.
    """
    if cap is not None and cap <= 0:
        return set()
    ids = (
        Project.objects.active()
        .filter(**{scope_field: owner_id})
        .order_by("created_at", "id")
        .values_list("id", flat=True)
    )
    if cap is not None:
        ids = ids[:cap]
    return set(ids)
