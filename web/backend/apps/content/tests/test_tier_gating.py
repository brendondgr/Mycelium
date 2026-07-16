"""Pipeline-time tier enforcement (P4): who runs, which areas, and the LLM gate.

These exercise the entitlement *gates* without the pgvector RAG path — the
recommend / refit engines are monkeypatched, so the tests assert wiring (who is
selected, which areas apply, which ``complete`` seam each target gets) and run on
SQLite.
"""

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import WatchPreference
from apps.billing.models import Subscription, Tier
from apps.billing.services import create_lab_workspace
from apps.content.opportunities import areas_for
from apps.content.tasks import select_targets, select_users

ALL_AREAS = ("grants", "conferences", "fellowships")


def _spore(username: str) -> User:
    user = User.objects.create_user(username=username, password="p")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    return user


@pytest.mark.django_db
def test_free_user_excluded_from_select_users() -> None:
    User.objects.create_user(username="free", password="p")
    _spore("spore")
    selected = {u.username for u in select_users(None)}
    assert "spore" in selected
    assert "free" not in selected


@pytest.mark.django_db
def test_targeted_run_still_filters_free() -> None:
    User.objects.create_user(username="free", password="p")
    assert select_users(["free"]) == []


@pytest.mark.django_db
def test_areas_for_free_user_is_empty_tuple() -> None:
    free = User.objects.create_user(username="free", password="p")
    assert areas_for(free, ALL_AREAS) == ()


@pytest.mark.django_db
def test_areas_for_spore_user_is_full() -> None:
    assert areas_for(_spore("spore"), ALL_AREAS) == ALL_AREAS


@pytest.mark.django_db
def test_canceled_lab_drops_from_select_targets() -> None:
    from apps.research.models import Project

    founder = User.objects.create_user(username="founder", password="p")
    result = create_lab_workspace(founder, "Rivera Lab")
    lab = result.lab
    project = Project.objects.create(scope_lab=lab, name="P1")

    labs, projects = select_targets(None)
    assert lab in labs
    assert project in projects

    result.subscription.status = Subscription.Status.CANCELED
    result.subscription.save(update_fields=["status"])

    labs, projects = select_targets(None)
    assert lab not in labs
    assert project not in projects


@pytest.mark.django_db
def test_watch_topics_capped_on_read_after_downgrade() -> None:
    from apps.content.pipeline import _watch_topics

    user = User.objects.create_user(username="lapsed", password="p")
    sub = Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    WatchPreference.objects.create(user=user, topics=[f"t{n}" for n in range(8)])
    assert len(_watch_topics(user)) == 8  # Spore cap 10 → all honoured

    sub.status = Subscription.Status.CANCELED
    sub.save(update_fields=["status"])
    # Free cap 3 → only the first 3 honoured; stored topics untouched.
    assert _watch_topics(user) == ["t0", "t1", "t2"]
    assert WatchPreference.objects.get(user=user).topics == [f"t{n}" for n in range(8)]


@pytest.mark.django_db
def test_daily_batch_gates_llm_per_user(monkeypatch) -> None:
    from apps.content import pipeline

    free = User.objects.create_user(username="free", password="p")
    WatchPreference.objects.create(user=free, topics=["x"])
    spore = _spore("spore")
    WatchPreference.objects.create(user=spore, topics=["x"])

    recorded: dict = {}

    def fake_recommend(user, *, complete=None, **kwargs):
        recorded[user.username] = complete
        return pipeline.RunResult(user.username, "ok")

    monkeypatch.setattr(pipeline, "recommend_for_user", fake_recommend)

    def sentinel(_prompt):
        return "LLM-VERDICT"

    pipeline.run_daily_batch(
        [free, spore],
        search_fn=lambda *a, **k: [],
        embed=False,
        complete=sentinel,
    )

    # Spore keeps the real model; Free is forced onto the deterministic seam.
    assert recorded["spore"] is sentinel
    assert recorded["free"] is not sentinel
    assert recorded["free"]("anything") is None


@pytest.mark.django_db
def test_onboarding_match_free_user_forces_fallback(monkeypatch) -> None:
    from apps.content import onboarding_match

    free = User.objects.create_user(username="free", password="p")
    recorded: dict = {}

    def fake_refit(user, *, areas, persist, complete, **kwargs):
        recorded["complete"] = complete
        return SimpleNamespace(
            status="ok", areas={a: {"suggestions": 0} for a in areas}
        )

    monkeypatch.setattr(onboarding_match, "refit_user", fake_refit)

    def sentinel(_prompt):
        return "LLM"

    onboarding_match.onboarding_match_area(free, "grants", complete=sentinel)
    assert recorded["complete"] is not sentinel
    assert recorded["complete"]("x") is None


@pytest.mark.django_db
def test_onboarding_match_spore_user_keeps_llm(monkeypatch) -> None:
    from apps.content import onboarding_match

    spore = _spore("spore")
    recorded: dict = {}

    def fake_refit(user, *, areas, persist, complete, **kwargs):
        recorded["complete"] = complete
        return SimpleNamespace(status="ok", areas={a: {} for a in areas})

    monkeypatch.setattr(onboarding_match, "refit_user", fake_refit)

    def sentinel(_prompt):
        return "LLM"

    onboarding_match.onboarding_match_area(spore, "grants", complete=sentinel)
    assert recorded["complete"] is sentinel
