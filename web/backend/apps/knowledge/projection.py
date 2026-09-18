"""Declared edges: what people, labs and projects say about themselves, as edges.

The JSON a person or a project already maintains stays the source of truth.
This module mirrors it into the graph and nothing ever writes back the other
way — a profile is the person's own words, and ``state.py``'s invariant 9 (a
stated field is never auto-edited) is not touched.

What is mirrored ("any" means the wording may name a concept of any facet,
and a new one is minted as the facet shown):

| Source | Field | Relation | Facet |
|---|---|---|---|
| a person's profile | ``areas``, ``keywords`` | interested_in | any; mints as area |
| a person's profile | ``skills`` | can_do | any; mints as method |
| a lab's profile | ``areas`` (both copies), ``keywords`` | interested_in | as above |
| a lab's profile | ``skills`` | can_do | as above |
| a project's focus | ``areas``, ``keywords`` | works_on | any; mints as area |
| a project's state | ``problem`` | works_on | problem |
| a project's state | ``method`` | uses_method | method |
| a project's state | ``data`` | works_in_setting | setting |
| a project's state | ``needs.expertise`` | needs | any; mints as area |

Profiles are shared sources and link in the shared vocabulary; a project links
in its owner's private scope (principle 6 of the collaboration-network series).
A project-state field whose provenance is ``inferred`` is Mylo's proposal, not
the project's word, and is not mirrored until someone accepts it.

A projection is idempotent: on unchanged input it writes nothing. When the
embedder is down some wordings come back deferred, and then the projection
only adds — it never deletes an edge on a run that could not see everything.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Lab, LabProfile, Profile
from apps.research.models import Project, ProjectState

from . import linker
from .linker import LinkRequest
from .models import Concept, Edge, Facet, Relation, Scope, Tier

logger = logging.getLogger(__name__)

#: A private concept nothing points at is removed by the sweep once it has sat
#: unreferenced this long. The delay keeps the sweep from deleting a concept a
#: concurrent projection minted a moment before writing its edge.
ORPHAN_GRACE = timedelta(hours=1)


@dataclass(frozen=True)
class _Want:
    relation: str
    surface: str
    path: str
    facet: str | None = None
    default_facet: str = Facet.AREA


@dataclass
class Projected:
    """What one projection (or a sweep of many) did."""

    created: int = 0
    updated: int = 0
    deleted: int = 0
    deferred: int = 0
    skipped: int = 0
    subjects: int = 0
    orphans_removed: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def wrote(self) -> bool:
        return bool(self.created or self.updated or self.deleted)

    def add(self, other: Projected) -> None:
        for name in ("created", "updated", "deleted", "deferred", "skipped"):
            setattr(self, name, getattr(self, name) + getattr(other, name))
        self.subjects += other.subjects
        self.failures.extend(other.failures)

    def as_dict(self) -> dict:
        return {
            "subjects": self.subjects,
            "created": self.created,
            "updated": self.updated,
            "deleted": self.deleted,
            "deferred": self.deferred,
            "skipped": self.skipped,
            "orphans_removed": self.orphans_removed,
            "failures": len(self.failures),
        }


def _strings(value) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list | tuple):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _interest_wants(interests: dict, prefix: str) -> list[_Want]:
    interests = interests if isinstance(interests, dict) else {}
    wants: list[_Want] = []
    for key in ("areas", "keywords"):
        wants += [
            _Want(Relation.INTERESTED_IN, surface, f"{prefix}.{key}")
            for surface in _strings(interests.get(key))
        ]
    wants += [
        _Want(
            Relation.CAN_DO,
            surface,
            f"{prefix}.skills",
            default_facet=Facet.METHOD,
        )
        for surface in _strings(interests.get("skills"))
    ]
    return wants


def _profile_wants(profile: Profile) -> list[_Want]:
    return _interest_wants(profile.interests, "interests")


def _lab_wants(lab_profile: LabProfile) -> list[_Want]:
    wants = [
        _Want(Relation.INTERESTED_IN, surface, "lab.areas")
        for surface in _strings(lab_profile.areas)
    ]
    return wants + _interest_wants(lab_profile.interests, "interests")


def _project_focus(project: Project) -> dict:
    """The project's declared focus, read the way ``targets.project_interests`` does.

    Duplicated rather than imported: the knowledge core sits below the matching
    layer and must not depend on it.
    """
    goals = project.goals if isinstance(project.goals, dict) else {}
    explicit = goals.get("interests")
    if isinstance(explicit, dict):
        return {
            "areas": _strings(explicit.get("areas")),
            "keywords": _strings(explicit.get("keywords")),
        }
    return {
        "areas": _strings(goals.get("areas") or goals.get("topics")),
        "keywords": _strings(goals.get("keywords")),
    }


def _project_wants(project: Project) -> list[_Want]:
    focus = _project_focus(project)
    wants = [
        _Want(Relation.WORKS_ON, surface, f"focus.{key}")
        for key in ("areas", "keywords")
        for surface in focus[key]
    ]
    state = ProjectState.objects.filter(project=project).first()
    if state is None:
        return wants
    slow, fast = state.slow or {}, state.fast or {}
    provenance = state.provenance or {}

    def stated(name: str) -> bool:
        # A field with no recorded provenance is stated (state.normalise_provenance).
        return provenance.get(name, "stated") == "stated"

    if stated("problem"):
        wants += [
            _Want(Relation.WORKS_ON, surface, "state.problem", facet=Facet.PROBLEM)
            for surface in _strings(slow.get("problem"))
        ]
    if stated("method"):
        wants += [
            _Want(Relation.USES_METHOD, surface, "state.method", facet=Facet.METHOD)
            for surface in _strings(slow.get("method"))
        ]
    if stated("data"):
        wants += [
            _Want(Relation.WORKS_IN_SETTING, surface, "state.data", facet=Facet.SETTING)
            for surface in _strings(slow.get("data"))
        ]
    if stated("needs"):
        needs = fast.get("needs") if isinstance(fast.get("needs"), dict) else {}
        wants += [
            _Want(Relation.NEEDS, surface, "state.needs.expertise")
            for surface in _strings(needs.get("expertise"))
        ]
    return wants


def _project_scope(project: Project) -> tuple[str, object]:
    if project.scope_lab_id:
        return Scope.LAB, project.scope_lab
    if project.scope_department_id:
        return Scope.DEPARTMENT, project.scope_department
    return Scope.PERSONAL, project.scope_user


def _apply(
    subject: dict,
    wants: list[_Want],
    scope: str,
    owner,
    *,
    tier: str = Tier.DECLARED,
) -> Projected:
    """Make the subject's edges of one tier exactly ``wants``, as far as can be
    seen. Declared edges come from here; so do a work's demonstrated edges
    (:mod:`.demonstrated`), which follow the same rules."""
    result = Projected(subjects=1)
    links = linker.link_many(
        [
            LinkRequest(
                surface=want.surface,
                facet=want.facet,
                default_facet=want.default_facet,
                scope=scope,
                owner=owner,
            )
            for want in wants
        ]
    )

    desired: dict[tuple[str, int], dict] = {}
    for want, link in zip(wants, links, strict=True):
        if link.how == "deferred":
            result.deferred += 1
            continue
        if link.concept is None:
            result.skipped += 1
            continue
        entry = desired.setdefault(
            (want.relation, link.concept.pk),
            {"surface": linker.clean(want.surface), "evidence": []},
        )
        if want.path not in entry["evidence"]:
            entry["evidence"].append(want.path)

    with transaction.atomic():
        existing = {
            (edge.relation, edge.concept_id): edge
            for edge in Edge.objects.select_for_update().filter(tier=tier, **subject)
        }
        for key, spec in desired.items():
            evidence = sorted(spec["evidence"])
            edge = existing.get(key)
            if edge is None:
                Edge.objects.create(
                    relation=key[0],
                    concept_id=key[1],
                    tier=tier,
                    surface=spec["surface"],
                    evidence=evidence,
                    **subject,
                )
                result.created += 1
            elif edge.evidence != evidence or edge.surface != spec["surface"]:
                edge.evidence = evidence
                edge.surface = spec["surface"]
                edge.save(update_fields=["evidence", "surface", "updated_at"])
                result.updated += 1
        # Deleting on a run that could not link everything would delete the
        # edges of exactly the wordings it could not see.
        if not result.deferred:
            stale = [edge.pk for key, edge in existing.items() if key not in desired]
            if stale:
                result.deleted = Edge.objects.filter(pk__in=stale).delete()[0]
    return result


def project_user(user) -> Projected:
    profile = Profile.objects.filter(user=user).first()
    if profile is None:
        return Projected()
    return _apply({"user": user}, _profile_wants(profile), Scope.GLOBAL, None)


def project_lab(lab: Lab) -> Projected:
    lab_profile = LabProfile.objects.filter(lab=lab).first()
    wants = _lab_wants(lab_profile) if lab_profile else []
    return _apply({"lab": lab}, wants, Scope.GLOBAL, None)


def project_project(project: Project) -> Projected:
    scope, owner = _project_scope(project)
    if owner is None:  # pragma: no cover - the database forbids an ownerless project
        return Projected()
    return _apply({"project": project}, _project_wants(project), scope, owner)


def project_declared(subject) -> Projected:
    """Mirror one subject: a user or profile, a lab or lab profile, or a project."""
    User = get_user_model()
    if isinstance(subject, Profile):
        subject = subject.user
    if isinstance(subject, LabProfile):
        subject = subject.lab
    if isinstance(subject, ProjectState):
        subject = subject.project
    if isinstance(subject, User):
        return project_user(subject)
    if isinstance(subject, Lab):
        return project_lab(subject)
    if isinstance(subject, Project):
        return project_project(subject)
    raise TypeError(f"cannot project a {type(subject).__name__}")


#: What the save hook queues: a kind and a primary key, never an object.
KINDS = ("user", "lab", "project")


def project_by_key(kind: str, pk) -> Projected:
    """Project a subject named by kind and key; a vanished subject is a no-op."""
    model = {"user": get_user_model(), "lab": Lab, "project": Project}[kind]
    subject = model.objects.filter(pk=pk).first()
    if subject is None:
        return Projected()
    return project_declared(subject)


def prune_orphans(*, now=None) -> int:
    """Remove private concepts that nothing points at any more.

    A shared concept is vocabulary and stays. A private one exists only for its
    owner's edges; once its last edge is gone (a project deleted, a keyword
    removed), keeping it would keep that owner's wording for nothing.
    """
    cutoff = (now or timezone.now()) - ORPHAN_GRACE
    orphans = Concept.objects.exclude(scope=Scope.GLOBAL).filter(
        edges__isnull=True, merged_from__isnull=True, updated_at__lt=cutoff
    )
    return orphans.delete()[1].get("knowledge.Concept", 0)


def sweep() -> Projected:
    """Reconcile every subject, then prune orphans. Safe to run any time."""
    total = Projected()
    User = get_user_model()
    batches = (
        ("user", User.objects.filter(profile__isnull=False).order_by("pk")),
        ("lab", Lab.objects.order_by("pk")),
        ("project", Project.objects.order_by("pk")),
    )
    for kind, queryset in batches:
        for subject in queryset.iterator():
            try:
                total.add(project_declared(subject))
            except Exception:  # noqa: BLE001 - one bad row must not stop the sweep
                logger.exception("could not project %s %s", kind, subject.pk)
                total.failures.append(f"{kind}:{subject.pk}")
    total.orphans_removed = prune_orphans()
    return total
