"""Mylo chat in Discord answers for everyone in the server, not just the binding.

The reply's audience comes from everything bound in the server
(``resolve.server_width``): a lab's channel in its department's server is read
by the department, so a ``lab`` project is not named there; a server holding
labs of different departments is ``public``. And the audience check reads a
project's scope, not only which org owns it.
"""

from __future__ import annotations

import pytest
from apps.integrations.services import resolve
from apps.integrations.testing import bind
from apps.integrations.tests.base import clear_discord_cache, discord_test_settings
from apps.research.models import Project
from django.test import override_settings

from tools.agent import permissions, registry
from tools.agent.caller import Audience, Caller, Scope
from tools.agent.functions import common
from tools.agent.surfaces.discord import _scope_and_audience

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _discord():
    # A fresh copy: the shared object cannot be entered twice at once.
    with override_settings(**discord_test_settings.options):
        clear_discord_cache()
        yield
        clear_discord_cache()


def _project(world, scope, **kw):
    return Project.objects.create(
        scope_lab=kw.pop("lab", world.lab), name=f"P {scope}", visibility=scope, **kw
    )


def _shown(project, audience) -> bool:
    """Both halves of the gate's audience test, as ``decide`` applies them."""
    info = common.project_info(project)
    return permissions.width_rank(info.output) >= permissions.width_rank(
        audience.width
    ) and permissions.within_audience(info, audience)


def test_the_audience_is_the_servers_width(world):
    bind(lab=world.lab, guild_id="g-own", updates="own")
    scope, audience = _scope_and_audience(resolve.place_for("g-own", "own"))
    assert (scope.kind, audience.width, audience.obj) == ("lab", "lab", world.lab)

    bind(lab=world.lab, guild_id="g-dept", updates="lab-room")
    bind(department=world.dept, guild_id="g-dept")
    scope, audience = _scope_and_audience(resolve.place_for("g-dept", "lab-room"))
    assert scope.obj == world.lab
    assert (audience.width, audience.obj) == ("department", world.dept)

    bind(lab=world.lab, guild_id="g-mixed", updates="mixed-room")
    bind(lab=world.other_lab, guild_id="g-mixed")
    scope, audience = _scope_and_audience(resolve.place_for("g-mixed", "mixed-room"))
    assert scope.obj == world.lab and audience.width == "public"


@pytest.mark.parametrize(
    ("scope", "lab_room", "dept_room", "public_room"),
    [
        ("invite_only", False, False, False),
        ("lab", True, False, False),
        ("department", True, True, False),
        ("public", True, True, True),
    ],
)
def test_a_project_is_named_only_where_its_scope_reaches(
    world, scope, lab_room, dept_room, public_room
):
    project = _project(world, scope)
    assert _shown(project, Audience("person")) is True
    assert _shown(project, Audience("lab", world.lab)) is lab_room
    assert _shown(project, Audience("department", world.dept)) is dept_room
    assert _shown(project, Audience("public")) is public_room


def test_scope_not_ownership_decides(world):
    """A ``lab`` project of the department's own lab is the department's org,
    but its scope keeps it out of the department's room."""
    project = _project(world, "lab")
    info = common.project_info(project)
    assert (
        permissions.within_audience(info, Audience("department", world.dept)) is False
    )
    # A public project of another lab may be named in this lab's room.
    elsewhere = _project(world, "public", lab=world.other_lab)
    assert _shown(elsewhere, Audience("lab", world.lab)) is True


def test_a_lab_project_is_refused_in_the_departments_server(world):
    from tools.agent.tests.conftest import thread_for

    project = _project(world, "lab")
    thread = thread_for(world.owner, "lab", world.lab)
    caller = Caller(
        user=world.owner,
        surface="discord",
        scope=Scope("lab", world.lab),
        audience=Audience("department", world.dept),
        thread_id=thread.pk,
    )
    fn = registry.registry().get("projects_get")
    decision = permissions.decide(caller, fn, {"project": f"project:{project.pk}"})
    assert (decision.layer, decision.code) == (9, "audience")

    wide = _project(world, "department")
    decision = permissions.decide(caller, fn, {"project": f"project:{wide.pk}"})
    assert decision.allowed, decision


def test_public_is_an_agent_width():
    from tools._framework.agentspec import WIDTHS

    assert (
        WIDTHS.index("department") < WIDTHS.index("public") < WIDTHS.index("instance")
    )
