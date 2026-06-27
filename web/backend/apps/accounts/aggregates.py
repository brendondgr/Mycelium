"""Derived interest aggregates for labs and departments (brief Phase D).

A lab's (or department's) effective interest vector is *derived* — blended from
its members' profile embeddings and its scoped projects' embeddings — not stored
as redundant rows, mirroring how department effective membership is computed in
:mod:`apps.accounts.services`. The curated vector and this derived vector are
stored separately on the profile and blended at score time.

Vectors stay deferred until the scoring phase locks an embedding dimension, so
``derive_*_vector`` returns ``None`` while no contributing embedding exists. The
structural source-gathering (which profiles and projects contribute) is what is
wired and tested now.
"""

from __future__ import annotations

from collections.abc import Sequence

from django.db.models import Q

from .models import Department, Lab, LabMembership, Profile
from .services import effective_member_ids


def lab_profile_sources(lab: Lab) -> dict[str, list]:
    """Profile + project ids whose embeddings feed the lab's derived vector."""
    from apps.research.models import Project

    member_ids = LabMembership.objects.filter(lab=lab).values_list(
        "user_id", flat=True
    )
    profile_ids = list(
        Profile.objects.filter(user_id__in=member_ids).values_list("id", flat=True)
    )
    project_ids = list(
        Project.objects.filter(scope_lab=lab).values_list("id", flat=True)
    )
    return {"profiles": profile_ids, "projects": project_ids}


def dept_profile_sources(department: Department) -> dict[str, list]:
    """Profile + project ids feeding the department's derived vector.

    Uses the department's *effective* membership (direct members unioned with
    every lab's members) and projects scoped to the department or any lab under
    it.
    """
    from apps.research.models import Project

    member_ids = effective_member_ids(department)
    profile_ids = list(
        Profile.objects.filter(user_id__in=member_ids).values_list("id", flat=True)
    )
    project_ids = list(
        Project.objects.filter(
            Q(scope_department=department) | Q(scope_lab__department=department)
        ).values_list("id", flat=True)
    )
    return {"profiles": profile_ids, "projects": project_ids}


def blend_embeddings(vectors: Sequence) -> list[float] | None:
    """Mean-blend equal-dimension vectors; ``None`` if there are none.

    Dimension agreement is guaranteed once the scoring phase picks a model; until
    then there are no vectors to blend.
    """
    present = [v for v in vectors if v is not None]
    if not present:
        return None
    count = len(present)
    dim = len(present[0])
    return [sum(vec[i] for vec in present) / count for i in range(dim)]


def _gather_vectors(sources: dict[str, list]) -> list:
    from apps.research.models import Project

    profile_vectors = Profile.objects.filter(
        id__in=sources["profiles"], embedding__isnull=False
    ).values_list("embedding", flat=True)
    project_vectors = Project.objects.filter(
        id__in=sources["projects"], embedding__isnull=False
    ).values_list("embedding", flat=True)
    return [*profile_vectors, *project_vectors]


def derive_lab_vector(lab: Lab) -> list[float] | None:
    """Blend the lab's contributing embeddings into one derived vector."""
    return blend_embeddings(_gather_vectors(lab_profile_sources(lab)))


def derive_dept_vector(department: Department) -> list[float] | None:
    """Blend the department's contributing embeddings into one derived vector."""
    return blend_embeddings(_gather_vectors(dept_profile_sources(department)))
