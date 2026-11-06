"""`/setup` across bindings: one binding behaves as before, several ask which one,
and each is configured — and authorized — against its own target."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import Department, DeptMembership, Lab, LabMembership
from apps.integrations.services import resolve
from apps.integrations.testing import bind

from .base import _LOCMEM, clear_discord_cache

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
from mylo import linking  # noqa: E402

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_discord_cache()
    yield
    clear_discord_cache()


@pytest.fixture(autouse=True)
def _entitled(settings):
    settings.CACHES = _LOCMEM
    settings.BILLING_ENFORCE_ENTITLEMENTS = False


def _manager(username: str, *, lab=None, department=None, snowflake: str):
    user = User.objects.create_user(username)
    resolve.bind_identity(user, snowflake, method=resolve.LINK_OAUTH)
    if lab is not None:
        LabMembership.objects.create(user=user, lab=lab, role=LabMembership.Role.OWNER)
    if department is not None:
        DeptMembership.objects.create(
            user=user, department=department, role=DeptMembership.Role.OWNER
        )
    return user


def _ok_preflight(*_a, **_k):
    return mock.Mock(ok=True)


def test_one_binding_opens_straight_to_its_menu() -> None:
    lab = Lab.objects.create(name="Reef", slug="reef")
    _manager("pi", lab=lab, snowflake="11")
    bind(lab=lab, guild_id="g1", deadlines="c-dead")

    status, payload = linking._setup_state_sync("11", "g1")

    assert status == "ok"
    assert payload["lab_name"] == "Reef"
    assert payload["deadlines_channel_id"] == "c-dead"


def test_several_bindings_ask_which_one() -> None:
    head = User.objects.create_user("head")
    dept = Department.objects.create(owner=head, name="EOAS")
    lab = Lab.objects.create(name="Reef", slug="reef", department=dept)
    _manager("pi", lab=lab, snowflake="11")
    bind(lab=lab, guild_id="g1")
    bind(department=dept, guild_id="g1")

    status, payload = linking._setup_state_sync("11", "g1")

    assert status == "choose"
    assert {b["kind"] for b in payload["bindings"]} == {"lab", "department"}


def test_a_lab_manager_cannot_configure_the_department_binding() -> None:
    head = User.objects.create_user("head")
    dept = Department.objects.create(owner=head, name="EOAS")
    lab = Lab.objects.create(name="Reef", slug="reef", department=dept)
    _manager("pi", lab=lab, snowflake="11")
    bind(lab=lab, guild_id="g1")
    dept_binding = bind(department=dept, guild_id="g1")

    status, _ = linking._setup_state_sync("11", "g1", dept_binding.id)

    assert status == "forbidden"


def test_each_binding_keeps_its_own_channels() -> None:
    head_user = User.objects.create_user("head-user")
    dept = Department.objects.create(owner=head_user, name="EOAS")
    lab = Lab.objects.create(name="Reef", slug="reef", department=dept)
    _manager("pi", lab=lab, snowflake="11")
    _manager("head", department=dept, snowflake="22")
    lab_binding = bind(lab=lab, guild_id="g1")
    dept_binding = bind(department=dept, guild_id="g1")

    with mock.patch(
        "apps.content.reminders_discord.preflight_channel", _ok_preflight
    ):
        lab_status, _ = linking._bind_setup_channel_sync(
            "11", "g1", "updates", "c-lab", lab_binding.id
        )
        dept_status, _ = linking._bind_setup_channel_sync(
            "22", "g1", "updates", "c-dept", dept_binding.id
        )

    assert (lab_status, dept_status) == ("ok", "ok")
    assert resolve.route_channel(lab_binding, "updates") == "c-lab"
    assert resolve.route_channel(dept_binding, "updates") == "c-dept"

    # Turning the department's updates off leaves the lab's alone.
    linking._bind_setup_channel_sync("22", "g1", "updates", "", dept_binding.id)
    assert resolve.route_channel(dept_binding, "updates") == ""
    assert resolve.route_channel(lab_binding, "updates") == "c-lab"


def test_a_binding_from_another_server_is_refused() -> None:
    lab = Lab.objects.create(name="Reef", slug="reef")
    _manager("pi", lab=lab, snowflake="11")
    bind(lab=lab, guild_id="g1")
    elsewhere = bind(lab=lab, guild_id="g2")

    status, _ = linking._setup_state_sync("11", "g1", elsewhere.id)

    assert status == "not_active"


def test_an_unactivated_server_says_so() -> None:
    status, payload = linking._setup_state_sync("11", "g-none")
    assert status == "not_active"
    assert "/activate-department" in payload["message"]
