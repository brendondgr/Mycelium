"""Mylo in the public demo (apps/demo): one question per visitor, each
visitor's conversation their own, and nothing a visitor says kept."""

from __future__ import annotations

import pytest
from apps.demo import world as demo_world
from apps.demo.models import DemoQuestion, DemoWorld
from django.conf import settings
from django.core.management import call_command
from django.test import Client

pytestmark = pytest.mark.django_db

AGENT = "/api/demo/tools/agent"


@pytest.fixture
def demo(settings):
    settings.DEMO_ENABLED = True
    settings.DEMO_QUESTIONS_PER_VISITOR = 1
    settings.DEMO_QUESTIONS_PER_IP_PER_DAY = 3
    settings.DEMO_QUESTIONS_PER_DAY = 100
    settings.DEMO_QUESTION_MAX_CHARS = 500
    call_command("demo", "build", "--no-rank")
    demo_world.forget()
    yield DemoWorld.objects.select_related("viewer", "lab", "department").get()
    demo_world.forget()


@pytest.fixture
def no_turns(monkeypatch):
    """Sending starts no worker turn: the budget is what is under test."""
    from tools.agent import tasks

    monkeypatch.setattr(
        tasks.run_turn, "delay", lambda thread_id: type("R", (), {"id": "x"})()
    )


def _csrf_client() -> Client:
    c = Client(enforce_csrf_checks=True)
    c.get("/api/demo/auth/csrf/")
    return c


def _post(c: Client, path: str, data: dict):
    token = c.cookies[settings.CSRF_COOKIE_NAME].value
    return c.post(path, data, content_type="application/json", HTTP_X_CSRFTOKEN=token)


def _ask(c: Client, demo, text="What should we read this week?"):
    made = _post(c, f"{AGENT}/threads/", {"scope": "lab", "ref": demo.lab.slug})
    assert made.status_code == 201, made.content
    tid = made.json()["id"]
    return tid, _post(c, f"{AGENT}/threads/{tid}/messages/", {"text": text})


def test_one_question_per_visitor(demo, no_turns):
    c = _csrf_client()
    tid, sent = _ask(c, demo)
    assert sent.status_code == 202, sent.content
    assert DemoQuestion.objects.get().thread_id is not None
    _, again = _ask(c, demo)
    assert again.status_code == 429
    assert again.json()["code"] == "demo_question_used"
    assert c.get("/api/demo/auth/me/").json()["demo"]["questions_left"] == 0


def test_a_new_visitor_gets_their_own_question(demo, no_turns):
    first, second = _csrf_client(), _csrf_client()
    a, _ = _ask(first, demo)
    b, sent = _ask(second, demo)
    assert sent.status_code == 202
    # Each sees only their own conversation, though both are the demo viewer.
    assert [t["id"] for t in first.get(f"{AGENT}/threads/").json()["threads"]] == [a]
    assert second.get(f"{AGENT}/threads/{a}/").status_code == 404
    assert second.get(f"{AGENT}/threads/{a}/events/").status_code == 404


def test_the_address_and_day_caps(demo, no_turns, settings):
    settings.DEMO_QUESTIONS_PER_IP_PER_DAY = 1
    _ask(_csrf_client(), demo)
    _, refused = _ask(_csrf_client(), demo)
    assert refused.json()["code"] == "demo_closed_today"
    settings.DEMO_QUESTIONS_PER_DAY = 0
    _, off = _ask(_csrf_client(), demo)
    assert off.json()["code"] == "demo_chat_off"


def test_a_refused_send_refunds_the_question(demo, no_turns):
    c = _csrf_client()
    _, too_long = _ask(c, demo, text="x" * 501)
    assert too_long.status_code == 400
    _, empty = _ask(c, demo, text="   ")
    assert empty.status_code == 400
    assert not DemoQuestion.objects.exists()
    _, sent = _ask(c, demo)
    assert sent.status_code == 202


def test_demo_threads_are_never_learned_from(demo):
    from tools.agent import learning, memory_after
    from tools.agent.models import AgentThread

    thread = AgentThread.objects.create(
        user=demo.viewer, demo_visitor="v1", last_activity_at="2000-01-01T00:00Z"
    )
    assert thread not in list(learning.due_threads())
    called = []
    memory_after.title_and_purpose = lambda *a, **k: called.append(a)
    memory_after.after_turn(None, thread, None)
    assert called == []
    # Outside the demo, the demo viewer's thread list is empty.
    from tools.agent import service

    assert service.list_threads(demo.viewer) == []
