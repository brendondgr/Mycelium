"""The public demo's door, world and Mylo budget (apps/demo)."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver

from apps.accounts.models import Lab
from apps.demo import world as demo_world
from apps.demo.middleware import ALWAYS_REFUSED, WRITE_ALLOWED, refusal_for
from apps.demo.models import DemoWorld

pytestmark = pytest.mark.django_db

AGENT = "/api/demo/tools/agent"


@pytest.fixture
def demo(settings):
    settings.DEMO_ENABLED = True
    settings.DEMO_QUESTIONS_PER_VISITOR = 1
    settings.DEMO_QUESTIONS_PER_IP_PER_DAY = 3
    settings.DEMO_QUESTIONS_PER_DAY = 100
    settings.DEMO_QUESTION_MAX_CHARS = 500
    settings.LLM_MODEL = "test-model"
    call_command("demo", "build", "--no-rank")
    demo_world.forget()
    yield DemoWorld.objects.select_related("viewer", "lab", "department").get()
    demo_world.forget()


def _csrf_client() -> Client:
    c = Client(enforce_csrf_checks=True)
    c.get("/api/demo/auth/csrf/")
    return c


def _post(c: Client, path: str, data: dict):
    from django.conf import settings

    token = c.cookies[settings.CSRF_COOKIE_NAME].value
    return c.post(path, data, content_type="application/json", HTTP_X_CSRFTOKEN=token)


# -- the switch -------------------------------------------------------------


def test_off_is_absent(settings):
    settings.DEMO_ENABLED = False
    demo_world.forget()
    assert Client().get("/api/demo/status/").status_code == 404
    assert Client().get("/api/demo/auth/me/").status_code == 404


def test_on_without_a_world_is_absent(settings):
    settings.DEMO_ENABLED = True
    demo_world.forget()
    assert Client().get("/api/demo/status/").status_code == 404


def test_status_names_the_entry(demo):
    body = Client().get("/api/demo/status/").json()
    assert body["enabled"] is True
    assert body["entry"] == f"/demo/overview?ws={demo.lab.slug}"
    assert body["questions_left"] == 1


# -- the world ----------------------------------------------------------------


def test_build_makes_an_undeliverable_unsigninable_world(demo):
    people = User.objects.filter(email__iendswith="@" + demo_world.DOMAIN)
    assert people.count() == 6
    assert not any(u.has_usable_password() for u in people)
    assert all(u.watch.topics for u in people)
    assert demo.viewer.lab_memberships.get(lab=demo.lab).role == "owner"
    assert demo.lab.department_id == demo.department_id


def test_build_is_rerunnable_and_delete_leaves_others(demo):
    other = User.objects.create_user("real", "real@example.edu", "pw")
    call_command("demo", "build", "--no-rank")
    assert DemoWorld.objects.count() == 1
    call_command("demo", "delete")
    assert not DemoWorld.objects.exists()
    assert not User.objects.filter(email__iendswith="@" + demo_world.DOMAIN).exists()
    assert not Lab.objects.filter(slug="coastal-ocean-lab").exists()
    assert User.objects.filter(pk=other.pk).exists()


# -- the door -----------------------------------------------------------------


def test_reads_are_the_viewers(demo):
    me = Client().get("/api/demo/auth/me/").json()
    assert me["id"] == demo.viewer.pk
    assert me["demo"]["lab"] == demo.lab.slug
    assert me["demo"]["questions_left"] == 1


def test_a_real_session_is_ignored_and_kept(demo, settings):
    real = User.objects.create_user("real", "real@example.edu", "pw")
    c = Client()
    c.force_login(real)
    name = settings.SESSION_COOKIE_NAME
    session_before = c.cookies[name].value
    response = c.get("/api/demo/auth/me/")
    assert response.json()["id"] == demo.viewer.pk
    assert name not in response.cookies  # neither rewritten nor deleted
    assert c.get("/api/auth/me/").json()["id"] == real.pk
    assert c.cookies[name].value == session_before


def test_an_authorization_header_cannot_sign_in_someone_else(demo):
    User.objects.create_user("real", "real@example.edu", "pw")
    import base64

    token = base64.b64encode(b"real:pw").decode()
    me = Client().get("/api/demo/auth/me/", HTTP_AUTHORIZATION=f"Basic {token}")
    assert me.json()["id"] == demo.viewer.pk


def test_a_missing_trailing_slash_still_resolves(demo):
    assert Client().get("/api/demo/auth/me").json()["id"] == demo.viewer.pk


def test_writes_are_refused(demo):
    c = _csrf_client()
    response = _post(c, "/api/demo/auth/account/", {"first_name": "X"})
    assert response.status_code == 403
    assert response.json()["code"] == "demo_read_only"
    assert _post(c, "/api/demo/auth/logout/", {}).status_code == 403
    assert Client().get("/api/demo/auth/login/").status_code == 403


def test_another_labs_data_stays_out_of_reach(demo):
    from apps.billing.services import create_lab_workspace

    owner = User.objects.create_user("owner", "owner@example.edu", "pw")
    lab = create_lab_workspace(owner, "Private Lab").lab
    response = Client().get(f"/api/demo/auth/labs/{lab.slug}/members/")
    assert response.status_code in (403, 404)


def _patterns(resolver, prefix=""):
    for p in resolver.url_patterns:
        if isinstance(p, URLResolver):
            yield from _patterns(p, prefix + str(p.pattern))
        elif isinstance(p, URLPattern):
            yield prefix + str(p.pattern)


def test_every_route_is_read_only_unless_allowed():
    """The sweep: a route added later is refused in the demo until it is
    deliberately allowed, and the allowlist names only Mylo's question routes."""
    routes = {r.rstrip("/") for r in _patterns(get_resolver()) if r.startswith("api/")}
    assert {route for _, route in WRITE_ALLOWED} <= routes
    for route in routes:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            if (method, route) in WRITE_ALLOWED:
                assert route.startswith("api/tools/agent/threads")
                continue
            assert refusal_for(method, route) is not None, (method, route)
        if not route.startswith(ALWAYS_REFUSED):
            assert refusal_for("GET", route) is None, route
