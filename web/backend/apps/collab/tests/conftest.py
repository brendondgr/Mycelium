"""Fixtures shared by the collaboration tests (the knowledge core's fakes)."""

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import Lab, LabMembership
from apps.collab.models import RequirementSlots
from apps.content import embeddings
from apps.content.models import ContentItem
from apps.knowledge import service
from apps.knowledge.tests.fakes import FakeEmbedder


@pytest.fixture
def embedder():
    fake = FakeEmbedder()
    embeddings.set_embedder(fake)
    yield fake
    embeddings.reset_embedder()


def _person(username, **interests):
    user = User.objects.create_user(username, f"{username}@example.org", "pw")
    user.profile.interests = interests
    user.profile.save()
    service.project_declared(user)
    return user


@pytest.fixture
def world(db, embedder):
    embedder.near("satellite remote sensing", "remote sensing of reefs")
    lab = Lab.objects.create(name="Reef", slug="reef-coverage")
    ada = _person("ada", areas=["Remote sensing of reefs"])
    bo = _person("bo", areas=["Coral reef ecology"], skills=["field surveys"])
    for index, member in enumerate((ada, bo)):
        LabMembership.objects.create(user=member, lab=lab, is_lead=index == 0)
    call = ContentItem.objects.create(type="grant", source="grants", external_id="G1")
    slots = [
        {"facet": "method", "text": "satellite remote sensing", "required": True},
        {"facet": "problem", "text": "coral reef ecology", "required": False},
        {"facet": "method", "text": "environmental health", "required": True},
        {"facet": "role", "text": "local marine park authority", "required": True},
    ]
    for slot in slots:
        if slot["facet"] != "role":
            slot["vector"] = embedder.vector(slot["text"])
    RequirementSlots.objects.create(
        content=call,
        slots=slots,
        status=RequirementSlots.Status.OK,
        prompt_version="s1",
        source_fingerprint="x",
    )
    return lab, ada, bo, call
