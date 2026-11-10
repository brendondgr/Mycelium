"""The public demo (apps/demo) in the nightly run: its people, lab and projects
are ranked and briefed while the demo is served, and left out while it is off."""

from __future__ import annotations

import pytest
from apps.demo import world as demo_world
from apps.demo.models import DemoWorld
from django.core.management import call_command

from tools.recommendation.tasks import select_targets, select_users

pytestmark = pytest.mark.django_db


@pytest.fixture
def built(settings):
    settings.DEMO_ENABLED = True
    call_command("demo", "build", "--no-rank")
    demo_world.forget()
    yield DemoWorld.objects.select_related("lab", "department").get()
    demo_world.forget()


def _demo_people(users) -> set[str]:
    return {u.username for u in users if demo_world.is_demo_user(u)}


def test_on_the_nightly_ranks_the_demo_world(built):
    labs, projects = select_targets(None)
    assert len(_demo_people(select_users(None))) == 6
    assert built.lab.id in {lab.id for lab in labs}
    assert {p.name for p in projects if p.scope_lab_id == built.lab.id} == {
        "Marine heatwave early warning",
        "Plastic pathways",
    }


def test_off_the_nightly_leaves_it_out(built, settings):
    settings.DEMO_ENABLED = False
    labs, projects = select_targets(None)
    assert _demo_people(select_users(None)) == set()
    assert _demo_people(select_users(["demo.mara"])) == set()
    assert built.lab.id not in {lab.id for lab in labs}
    assert not [p for p in projects if p.scope_lab_id == built.lab.id]
