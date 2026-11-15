"""``GET api/admin/setup-status/``: the Getting started checklist's facts."""

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APIClient

from apps.core import llm_servers

URL = "/api/admin/setup-status/"
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fresh():
    llm_servers.reset()
    yield
    llm_servers.reset()


def _client(staff: bool) -> tuple[APIClient, User]:
    user = User.objects.create_user(
        username=f"admin{staff}", password="x", is_staff=staff
    )
    client = APIClient()
    client.force_authenticate(user)
    return client, user


def test_only_staff_may_read_it():
    assert APIClient().get(URL).status_code in (401, 403)
    client, _ = _client(False)
    assert client.get(URL).status_code == 403


@override_settings(LLM_ENABLED=False)
def test_a_fresh_instance_lists_what_is_left():
    client, _ = _client(True)
    body = client.get(URL).json()
    steps = body["steps"]
    assert steps["model"]["state"] == "skipped"
    assert steps["collection"]["state"] == "todo"
    assert steps["collection"]["total"] == 0
    assert steps["collection"]["command"] == "make nightly"
    assert steps["profile"]["state"] == "todo"
    assert steps["people"]["state"] == "todo"
    assert steps["discord"]["state"] == "optional"
    assert body["complete"] is False


@override_settings(LLM_ENABLED=False)
def test_the_admin_placeholder_interests_are_not_a_profile():
    """``create_admin`` seeds placeholder interests; that is not the admin
    filling in their profile, so the step stays to do."""
    from apps.accounts.management.commands.create_admin import ADMIN_INTERESTS

    client, user = _client(True)
    user.profile.interests = dict(ADMIN_INTERESTS)
    user.profile.save()
    assert client.get(URL).json()["steps"]["profile"]["state"] == "todo"


@override_settings(LLM_ENABLED=False)
def test_each_step_turns_done_from_the_data():
    client, user = _client(True)
    item = apps.get_model("content", "ContentItem")
    item.objects.create(type="paper", source="openalex", external_id="W1")
    user.profile.interests = {"keywords": ["proteomics"]}
    user.profile.save()
    User.objects.create_user(username="colleague", password="x")
    body = client.get(URL).json()
    steps = body["steps"]
    assert steps["collection"]["state"] == "done"
    assert steps["collection"]["counts"]["paper"] == 1
    assert steps["profile"]["state"] == "done"
    assert steps["people"]["state"] == "done"
    assert body["complete"] is True


def test_an_unnamed_model_is_still_to_do(settings):
    # The server table reads the model name from settings, not the environment.
    settings.LLM_ENABLED = True
    settings.LLM_MODEL = ""
    client, _ = _client(True)
    model = client.get(URL).json()["steps"]["model"]
    assert model["state"] == "todo"
