"""Write the synthetic world into the sandbox database, as the app's own rows.

Everything goes through the same models production uses — users and their
profiles, labs and memberships, projects and their stated state, imported
works — so the pipeline under test cannot tell the sandbox from the real thing.
A reset flushes the whole sandbox database first; it is only ever called after
:func:`.bootstrap.assert_sandboxed`.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import AuthorWork, Lab, LabMembership, LabProfile
from apps.research.models import Project, ProjectState

from . import world as world_mod
from .bootstrap import assert_sandboxed

FIELD_NAMES = {key: name for key, _, name in world_mod.FIELDS}
FIELD_IDS = {key: field_id for key, field_id, _ in world_mod.FIELDS}


def openalex_id(person_key: str) -> str:
    return f"ASB{person_key.upper()}"


def reset() -> None:
    assert_sandboxed()
    call_command("flush", interactive=False, verbosity=0)


@transaction.atomic
def seed(world: world_mod.World, corpus: dict[str, dict]) -> dict:
    assert_sandboxed()
    User = get_user_model()
    now = timezone.now()
    users: dict[str, object] = {}
    for person in world.people:
        first, last = person.name.split(" ", 1)
        user = User.objects.create_user(
            person.key, person.email, "sandbox", first_name=first, last_name=last
        )
        profile = user.profile
        profile.is_verified = True
        profile.openalex_id = openalex_id(person.key)
        profile.institution = person.institution
        profile.interests = {
            "version": 2,
            "areas": person.declared_areas,
            "keywords": person.declared_keywords,
            "skills": person.declared_skills,
        }
        profile.save()
        users[person.key] = user

    works = 0
    for person in world.people:
        for paper in person.papers:
            text = corpus.get(paper.key) or {}
            AuthorWork.objects.create(
                user=users[person.key],
                source="openalex",
                source_id=f"SB-{paper.key}",
                title=text.get("title") or paper.problem.capitalize(),
                abstract=text.get("abstract") or "",
                year=paper.year,
                coauthor_ids=[openalex_id(key) for key in person.coauthors],
                openalex_field_id=FIELD_IDS[paper.field],
                field_checked_at=now,
            )
            works += 1

    labs: dict[str, Lab] = {}
    for spec in world.labs:
        lab = Lab.objects.create(name=spec.name, slug=f"sandbox-{spec.key}")
        for index, member in enumerate(spec.members):
            LabMembership.objects.create(
                user=users[member],
                lab=lab,
                role=LabMembership.Role.OWNER
                if index == 0
                else LabMembership.Role.MEMBER,
                is_lead=index == 0,
            )
        lab_profile = LabProfile.objects.get(lab=lab)
        lab_profile.areas = spec.areas
        lab_profile.interests = {"version": 2, "areas": spec.areas}
        lab_profile.save()
        labs[spec.key] = lab

    for spec in world.projects:
        project = Project.objects.create(
            name=spec.name,
            scope_lab=labs[spec.lab],
            goals={"interests": {"areas": [FIELD_NAMES[world_of(world, spec).field]]}},
        )
        project.members.add(*[users[key] for key in spec.members])
        ProjectState.objects.create(
            project=project,
            slow={"problem": spec.problem, "method": spec.methods, "data": spec.data},
            fast={"needs": {"expertise": spec.needs}},
        )
    return {
        "people": len(users),
        "works": works,
        "labs": len(labs),
        "projects": len(world.projects),
    }


def world_of(world: world_mod.World, project: world_mod.ProjectSpec):
    return next(lab for lab in world.labs if lab.key == project.lab)
