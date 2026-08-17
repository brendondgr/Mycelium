"""The nightly commands must cover labs and projects, not just users.

``manual_all.py`` (the host timer that replaced the Celery Beat dailies) runs the
*management commands*, not the tasks. When those commands only passed ``users`` to
the batch functions, every lab was briefed and digested each night but never
**scored** — so a lab feed froze at whatever the last on-demand refit wrote and the
daily report honestly read "250 papers, 0 new" forever.

These assert the wiring only: the batch engines are monkeypatched, so the tests run
on SQLite without the pgvector RAG path.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from apps.billing.models import Subscription, Tier
from apps.billing.services import activate_lab_subscription, create_lab_workspace
from apps.content.pipeline import BatchResult
from apps.research.models import Project


@pytest.fixture
def scored():
    """Collect the ``(users, labs, projects)`` each command hands to its batch."""
    return {}


@pytest.fixture
def lab_setup(db):
    """One entitled user plus an active lab with one in-cap project."""
    user = User.objects.create_user(username="spore", password="p")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    founder = User.objects.create_user(username="founder", password="p")
    lab = create_lab_workspace(founder, "Rivera Lab").lab
    activate_lab_subscription(lab)  # labs start INACTIVE (L1)
    project = Project.objects.create(scope_lab=lab, name="P1")
    return user, lab, project


def _capture(monkeypatch, module: str, name: str, sink: dict, result):
    def fake(users, *, labs=(), projects=(), **kwargs):
        sink["users"] = list(users)
        sink["labs"] = list(labs)
        sink["projects"] = list(projects)
        return result

    monkeypatch.setattr(f"{module}.{name}", fake)


@pytest.mark.django_db
def test_daily_suggestions_command_scores_labs_and_projects(
    monkeypatch, lab_setup, scored
) -> None:
    user, lab, project = lab_setup
    _capture(
        monkeypatch,
        "apps.content.management.commands.run_daily_suggestions",
        "run_daily_batch",
        scored,
        BatchResult(),
    )
    call_command("run_daily_suggestions", "--no-llm", "--no-embed")

    assert user in scored["users"]
    assert lab in scored["labs"]
    assert project in scored["projects"]


@pytest.mark.django_db
def test_daily_opportunities_command_matches_labs_and_projects(
    monkeypatch, lab_setup, scored
) -> None:
    from apps.content.opportunities import OppBatchResult

    user, lab, project = lab_setup
    _capture(
        monkeypatch,
        "apps.content.management.commands.run_daily_opportunities",
        "run_daily_opportunities_batch",
        scored,
        OppBatchResult(ingest={}, results=[]),
    )
    call_command("run_daily_opportunities", "--no-prune", "--no-llm")

    assert user in scored["users"]
    assert lab in scored["labs"]
    assert project in scored["projects"]


@pytest.mark.django_db
def test_targeted_suggestions_run_stays_user_scoped(
    monkeypatch, lab_setup, scored
) -> None:
    """``--user`` is the targeted path: no institutional targets come along."""
    user, _lab, _project = lab_setup
    _capture(
        monkeypatch,
        "apps.content.management.commands.run_daily_suggestions",
        "run_daily_batch",
        scored,
        BatchResult(),
    )
    call_command("run_daily_suggestions", "--user", user.username, "--no-llm")

    assert scored["users"] == [user]
    assert scored["labs"] == []
    assert scored["projects"] == []
