"""A Discord server's width is decided by everything bound in it (plan "Surfaces").

The rule behind leak 6: a lab bound into its department's server is read by the
department there, so what may be named in it is the department's, whichever
binding a post travels on.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import Department, Lab
from apps.integrations.services import resolve
from apps.integrations.testing import add_route, bind
from apps.research import visibility
from apps.research.models import Project


@pytest.fixture
def org(db):
    class World:
        pass

    o = World()
    head = User.objects.create_user("head", password="x")
    o.dept = Department.objects.create(owner=head, name="Biology")
    o.other_dept = Department.objects.create(owner=head, name="Physics")
    o.lab = Lab.objects.create(name="Reef", slug="reef", department=o.dept)
    o.sibling = Lab.objects.create(name="Kelp", slug="kelp", department=o.dept)
    o.foreign = Lab.objects.create(
        name="Optics", slug="optics", department=o.other_dept
    )
    o.loner = Lab.objects.create(name="Desert", slug="desert")
    o.loner2 = Lab.objects.create(name="Tundra", slug="tundra")
    return o


def test_one_lab_alone_is_a_lab_server(org):
    bind(lab=org.lab, guild_id="g1")
    assert resolve.server_width("g1") == "lab"


def test_a_lab_with_its_department_is_a_department_server(org):
    bind(lab=org.lab, guild_id="g1")
    bind(department=org.dept, guild_id="g1")
    assert resolve.server_width("g1") == "department"


def test_labs_of_one_department_are_a_department_server(org):
    bind(lab=org.lab, guild_id="g1")
    bind(lab=org.sibling, guild_id="g1")
    assert resolve.server_width("g1") == "department"


def test_a_department_alone_is_a_department_server(org):
    bind(department=org.dept, guild_id="g1")
    assert resolve.server_width("g1") == "department"


@pytest.mark.parametrize(
    "pair",
    [("lab", "foreign"), ("loner", "loner2"), ("lab", "loner")],
)
def test_labs_of_different_departments_or_none_are_public(org, pair):
    bind(lab=getattr(org, pair[0]), guild_id="g1")
    bind(lab=getattr(org, pair[1]), guild_id="g1")
    assert resolve.server_width("g1") == "public"


def test_a_pending_binding_already_widens_the_room(org):
    bind(lab=org.lab, guild_id="g1")
    bind(
        department=org.dept, guild_id="g1", state="pending_setup", guild_state="active"
    )
    assert resolve.server_width("g1") == "department"


def test_the_place_carries_the_server_width_not_the_bindings(org):
    lab_binding = bind(lab=org.lab, guild_id="g1", updates="lab-news")
    bind(department=org.dept, guild_id="g1")
    place = resolve.place_for("g1", "lab-news")
    assert place.binding == lab_binding
    assert place.width == "department"
    assert resolve.place_for("", "dm").width == "member"


def test_a_lab_posts_to_its_own_server_before_its_departments(org):
    """A lab project reaches the lab's own server if there is one."""
    in_dept = bind(lab=org.lab, guild_id="g-dept", updates="dept-room")
    bind(department=org.dept, guild_id="g-dept")
    assert resolve.lab_post_width(org.lab) == "department"
    own = bind(lab=org.lab, guild_id="g-own")
    add_route(own, "updates", "own-room")
    assert in_dept.activated_at <= own.activated_at
    assert resolve.get_updates_channel_for_lab(org.lab) == "own-room"
    assert resolve.lab_post_width(org.lab) == "lab"


def test_a_lab_with_no_server_is_lab_width(org):
    assert resolve.lab_post_width(org.lab) == "lab"
    assert resolve.target_widest_width(department=org.dept) == "department"


def test_target_widest_width_is_the_widest_live_server(org):
    bind(lab=org.lab, guild_id="g-own")
    bind(lab=org.lab, guild_id="g-mixed")
    bind(lab=org.foreign, guild_id="g-mixed")
    assert resolve.target_widest_width(lab=org.lab) == "public"


@pytest.mark.parametrize(
    ("scope", "allowed"),
    [
        ("invite_only", {"member"}),
        ("lab", {"member", "lab"}),
        ("department", {"member", "lab", "department"}),
        ("public", {"member", "lab", "department", "public"}),
    ],
)
def test_may_surface_by_place(org, scope, allowed):
    project = Project.objects.create(scope_lab=org.lab, name="P", visibility=scope)
    for width in visibility.WIDTHS:
        assert visibility.may_surface(project, width) is (width in allowed)
    bind(lab=org.lab, guild_id="g1", updates="room")
    bind(department=org.dept, guild_id="g1")
    place = resolve.place_for("g1", "room")
    assert visibility.may_surface(project, place) is ("department" in allowed)


def test_lab_surfaces_narrow_with_the_place(org):
    for scope in ("invite_only", "lab", "department", "public"):
        Project.objects.create(scope_lab=org.lab, name=scope, visibility=scope)

    def names(width):
        return set(
            visibility.lab_surface_projects(org.lab, width).values_list(
                "name", flat=True
            )
        )

    assert names("lab") == {"lab", "department", "public"}
    assert names("department") == {"department", "public"}
    assert names("public") == {"public"}
    # A lab surface is never narrower than the lab.
    assert names("member") == names("lab")
    assert set(
        visibility.department_surface_projects(org.dept).values_list("name", flat=True)
    ) == {"department", "public"}


def test_output_width_gains_public(org):
    def width(**kw):
        return visibility.output_width(Project.objects.create(name="x", **kw))

    assert width(scope_lab=org.lab, visibility="public") == "public"
    assert width(scope_lab=org.lab, visibility="department") == "department"
    assert width(scope_lab=org.lab, visibility="lab") == "lab"
    assert width(scope_lab=org.lab) == "project"
    owner = User.objects.create_user("solo", password="x")
    assert width(scope_user=owner) == "person"
    assert width(scope_user=owner, visibility="public") == "public"
