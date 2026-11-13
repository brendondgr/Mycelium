"""A lab or a department, seen the same way by every shared surface.

A department works like a lab (settings plan, "A department works like a lab"):
the same feeds, the same daily briefing, the same Discord post and PDF, the same
Monday weekly. Those functions were written for a lab and are generalised to take
either — not forked — and this is the one place the two differ: which column a
row is stored under, what the org is called, where its server posts, and which
projects its shared surfaces may cover.

:func:`org` wraps a ``Lab`` or a ``Department`` (or an ``Org`` already) so a
caller written against a lab keeps working unchanged when handed a department.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Org:
    """One lab or one department."""

    kind: str  # "lab" | "department"
    obj: Any

    # -- identity --------------------------------------------------------
    @property
    def is_lab(self) -> bool:
        return self.kind == "lab"

    @property
    def name(self) -> str:
        return self.obj.name

    @property
    def key(self) -> str:
        """A readable, stable identifier: a lab's slug, a department's id."""
        return self.obj.slug if self.is_lab else str(self.obj.pk)

    @property
    def file_key(self) -> str:
        """What a file for this org is named after: a lab's slug, a
        department's name as a slug (its id says nothing to a reader)."""
        from django.utils.text import slugify

        if self.is_lab:
            return self.obj.slug
        return slugify(self.name) or str(self.obj.pk)

    @property
    def id(self):
        return self.obj.pk

    # -- storage keys ----------------------------------------------------
    @property
    def owner(self) -> dict:
        """The ``DailyBriefing`` key: ``{"lab": …}`` or ``{"department": …}``."""
        return {self.kind: self.obj}

    @property
    def target_filter(self) -> dict:
        """The ``RelevanceScore`` key: ``{"target_lab": …}`` or
        ``{"target_department": …}``."""
        return {f"target_{self.kind}": self.obj}

    @property
    def alert_filter(self) -> dict | None:
        """Project alerts are stored per person or per lab; a department has none."""
        return {"target_lab": self.obj} if self.is_lab else None

    @property
    def saves_filter(self) -> dict:
        """What the org itself saved. A department keeps no saves of its own, so
        nothing a member bookmarked is ever published as the department's."""
        return {"target_lab": self.obj} if self.is_lab else {}

    # -- research --------------------------------------------------------
    def match_target(self):
        from tools.recommendation.targets import target_for_department, target_for_lab

        return (target_for_lab if self.is_lab else target_for_department)(self.obj)

    @property
    def watch(self):
        """The lab's watch row; a department has none (defaults apply)."""
        return getattr(self.obj, "watch", None) if self.is_lab else None

    def post_width(self, purpose: str = "updates") -> str:
        """The audience width of the server this org's scheduled posts land in
        (``apps.research.visibility``): a lab's own server is ``lab``, a server
        that also holds its department or other labs is wider; a department's is
        never narrower than ``department``. With no server, the org's own width."""
        from apps.integrations.services import resolve

        if self.is_lab:
            return resolve.lab_post_width(self.obj, purpose)
        return resolve.target_widest_width(department=self.obj)

    @property
    def web_width(self) -> str:
        """The width of this org's own web surfaces."""
        return "lab" if self.is_lab else "department"

    def shared_projects(self, width: str | None = None) -> list:
        """The active projects this org's shared surfaces may cover in a place
        of ``width`` (default: the org's own web surfaces)."""
        from tools.delivery.briefing import report_projects_for_org

        return report_projects_for_org(self, width=width)

    def hidden_projects(self) -> int:
        from tools.delivery.briefing import hidden_org_projects

        return hidden_org_projects(self)

    def member_ids(self) -> list[int]:
        """Everyone the org's feed can name as interested: a lab's members; a
        department's direct members and its labs' members."""
        from apps.accounts.models import DeptMembership, LabMembership

        if self.is_lab:
            return list(
                LabMembership.objects.filter(lab=self.obj).values_list(
                    "user_id", flat=True
                )
            )
        direct = DeptMembership.objects.filter(department=self.obj).values_list(
            "user_id", flat=True
        )
        via_labs = LabMembership.objects.filter(
            lab__department=self.obj
        ).values_list("user_id", flat=True)
        return sorted({*direct, *via_labs})

    # -- plan ------------------------------------------------------------
    def has_feature(self, feature: str) -> bool:
        from apps.billing.entitlements import department_has_feature, lab_has_feature

        check = lab_has_feature if self.is_lab else department_has_feature
        return check(self.obj, feature)

    # -- Discord ---------------------------------------------------------
    def bindings(self) -> list:
        from apps.integrations.services import resolve

        if self.is_lab:
            return resolve.bindings_for_lab(self.obj)
        return resolve.bindings_for_department(self.obj)

    def primary_server(self, purpose: str | None = None):
        from apps.integrations.services import resolve

        if self.is_lab:
            return resolve.primary_server_for_lab(self.obj, purpose)
        return resolve.primary_server_for_department(self.obj, purpose)

    def updates_channel(self) -> str:
        from apps.integrations.services import resolve

        if self.is_lab:
            return resolve.get_updates_channel_for_lab(self.obj)
        return resolve.get_updates_channel_for_department(self.obj)

    @property
    def outbox_lab(self):
        """The outbox row's ``lab`` column; a department's posts leave it empty."""
        return self.obj if self.is_lab else None


def org(value) -> Org:
    """Wrap a ``Lab`` or a ``Department`` (an ``Org`` passes through)."""
    if isinstance(value, Org):
        return value
    from apps.accounts.models import Department, Lab

    if isinstance(value, Lab):
        return Org("lab", value)
    if isinstance(value, Department):
        return Org("department", value)
    raise TypeError(f"not a lab or a department: {value!r}")


def org_from_filter(target_filter: dict) -> Org | None:
    """The org a ``target_*`` filter names, or ``None`` for a person or project."""
    if target_filter.get("target_lab") is not None:
        return Org("lab", target_filter["target_lab"])
    if target_filter.get("target_department") is not None:
        return Org("department", target_filter["target_department"])
    return None


def is_org_filter(target_filter: dict) -> bool:
    """Whether a ``target_*`` filter names a shared (lab or department) surface."""
    return org_from_filter(target_filter) is not None
