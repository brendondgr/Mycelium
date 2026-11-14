"""The demo lab's activity comes from its own feed (apps/demo/seed.py).

Tool models are looked up by name, not imported: the platform's import list
(tools/_framework/platform_imports.txt) only shrinks.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import Client
from django.utils import timezone

from apps.demo import world as demo_world
from apps.demo.models import DemoWorld
from apps.research.models import Project

pytestmark = pytest.mark.django_db

Item = apps.get_model("content", "ContentItem")
Deadline = apps.get_model("content", "ContentDeadline")
Score = apps.get_model("recommendation", "RelevanceScore")


@pytest.fixture
def demo(settings):
    settings.DEMO_ENABLED = True
    settings.FANOUT_COSINE_FLOOR = 0.35
    call_command("demo", "build", "--no-rank")
    demo_world.forget()
    yield DemoWorld.objects.select_related("viewer", "lab").get()
    demo_world.forget()


def _item(kind, title, *, due_in=None, vector=None):
    meta = {"title": title} if kind != "conference" else {"name": title}
    item = Item.objects.create(
        type=kind,
        source="test",
        external_id=title,
        source_url=f"https://example.org/{abs(hash(title))}",
        metadata=meta,
        embedding=vector,
    )
    if due_in is not None:
        Deadline.objects.create(
            content=item,
            kind="application" if kind != "conference" else "event",
            due_date=timezone.localdate() + timedelta(days=due_in),
            is_next=True,
            confidence="confirmed",
        )
    return item


def _score(item, score, verdict=None, **target):
    signals = {"suggested": True, "verdict": verdict} if verdict else {}
    Score.objects.create(content=item, score=score, signals=signals, **target)


def _feed(built):
    viewer, lab = built.viewer, built.lab
    project = Project.objects.filter(scope_lab=lab, members=viewer).order_by("name")[0]
    profile = viewer.profile
    profile.embedding = [1.0, 0.0, 0.0]
    profile.save(update_fields=["embedding"])
    paper = _item("paper", "Forecasting heatwaves", vector=[1.0, 0.0, 0.0])
    comment = _item("paper", "Comment on egusphere-1", vector=[1.0, 0.0, 0.0])
    closed = _item("grant", "Closed grant", due_in=-3)
    soon = _item("grant", "Grant closing in a week", due_in=7)
    later = _item("grant", "Grant closing in two months", due_in=60)
    speculative = _item("grant", "Speculative grant", due_in=50)
    unjudged = _item("grant", "Unjudged grant", due_in=55)
    fellowship = _item("fellowship", "Open fellowship", due_in=40)
    meeting = _item("conference", "Ocean meeting", due_in=90)
    # The model's judgement leads the score: a skip is never saved, and a read
    # beats a higher-scored item it did not judge.
    for item, score, verdict in (
        (paper, 0.9, "read"),
        (closed, 0.95, "read"),
        (speculative, 0.99, "skip"),
        (unjudged, 0.9, None),
        (later, 0.8, "read"),
        (fellowship, 0.7, "read"),
        (meeting, 0.6, "skim"),
    ):
        _score(item, score, verdict, target_user=viewer)
    for item, score, verdict in (
        (soon, 0.99, "read"),
        (speculative, 0.98, "skip"),
        (later, 0.8, "read"),
        (meeting, 0.7, "skim"),
    ):
        _score(item, score, verdict, target_lab=lab)
    _score(comment, 0.99, target_project=project)
    _score(paper, 0.9, target_project=project)
    return {"paper": paper, "comment": comment, "project": project}


def test_the_demo_pages_fill_from_its_own_feed(demo):
    feed = _feed(demo)
    call_command("demo", "seed")
    viewer, lab = demo.viewer, demo.lab
    c = Client()

    mine = c.get("/api/demo/saves/").json()["items"]
    # the closed grant and the skip are passed over, the read beats the unjudged
    # grant, a PI gets no fellowship; the lab's saves are a teammate's, not hers
    assert sorted(i["title"] for i in mine) == [
        "Forecasting heatwaves",
        "Grant closing in two months",
        "Ocean meeting",
    ]
    lab_saves = c.get(f"/api/demo/labs/{lab.slug}/saves/").json()["items"]
    # a call closing within three weeks is not saved for a reminder
    assert sorted(i["title"] for i in lab_saves) == [
        "Grant closing in two months",
        "Ocean meeting",
    ]
    reminders = [
        r
        for r in c.get("/api/demo/reminders/").json()["items"]
        if r.get("lab_slug") == lab.slug
    ]
    assert len(reminders) == 2 and {r["state"] for r in reminders} == {"active"}

    assert c.get("/api/demo/suggestions/").json()["count"] == 1
    assert viewer.member_suggestions.filter(
        content=feed["paper"], suggested=True
    ).exists()
    assert not viewer.member_suggestions.filter(content=feed["comment"]).exists()

    changes = c.get("/api/demo/ambient/changes/").json()["changes"]
    assert {ch["topic"] for ch in changes} >= {"Marine heatwave early warning"}


def test_seeding_again_replaces_rather_than_adds(demo):
    _feed(demo)
    call_command("demo", "seed")
    call_command("demo", "seed")
    assert demo.viewer.saved_opportunities.filter(target_lab=None).count() == 3
    assert demo.lab.saved_opportunities.count() == 2


def test_the_nightly_stage_is_quiet_without_a_world(settings):
    settings.DEMO_ENABLED = True
    call_command("demo", "seed")  # no world: nothing to do, no error


def test_the_understanding_fixture_refuses_a_real_account(demo):
    get_user_model().objects.create_user(
        username="real", email="real@example.edu", password="x"
    )
    with pytest.raises(CommandError, match="not a fixture account"):
        call_command("seed_understanding", '{"user": "real"}')
