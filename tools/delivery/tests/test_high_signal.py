"""R7 — the high-signal gate: brutal floor, weekly cap, once-ever, shadow mode."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User

from tools.delivery.high_signal import (
    deliver_high_signal,
    high_signal_candidates,
    shadow_report,
)
from tools.delivery.models import Notification
from tools.recommendation.models import RelevanceScore
from tools.retrieval.models import ContentItem

TODAY = date(2026, 7, 16)


@pytest.fixture
def user(db):
    return User.objects.create_user("hs-user")


def _score(
    user, *, ext, match=95, is_new=True, source="llm", fresh=True, deadline_days=30
):
    item = ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="pivot",
        external_id=ext,
        metadata={"title": f"Grant {ext}", "website": "https://x.test"},
    )
    pinned = (TODAY + timedelta(days=3)) if fresh else (TODAY - timedelta(days=3))
    return RelevanceScore.objects.create(
        content=item,
        target_user=user,
        score=0.9,
        signals={
            "suggested": True,
            "is_new": is_new,
            "pinned_until": pinned.isoformat(),
            "source": source,
            "match_percent": match,
            "deadline_date": (TODAY + timedelta(days=deadline_days)).isoformat(),
            "reason": "Strong fit for your funding needs.",
        },
    )


@pytest.mark.django_db
def test_high_signal_candidate_passes_full_gate(user) -> None:
    _score(user, ext="g1")
    cands = high_signal_candidates(user, today=TODAY, floor=90)
    assert len(cands) == 1
    assert deliver_high_signal(user, today=TODAY, floor=90) == 1
    note = Notification.objects.get(kind=Notification.Kind.HIGH_SIGNAL)
    assert note.dedupe_key == f"high_signal:{user.id}:{cands[0].content_id}"


@pytest.mark.django_db
def test_high_signal_abstains_when_nothing_clears_floor(user) -> None:
    _score(user, ext="g1", match=80)  # below the 90 floor
    assert high_signal_candidates(user, today=TODAY, floor=90) == []
    assert deliver_high_signal(user, today=TODAY, floor=90) == 0
    assert Notification.objects.count() == 0


@pytest.mark.django_db
def test_gate_requires_llm_source(user) -> None:
    _score(user, ext="g1", source="fallback")
    assert high_signal_candidates(user, today=TODAY, floor=90) == []


@pytest.mark.django_db
def test_gate_requires_fresh_is_new(user) -> None:
    _score(user, ext="stale", fresh=False)  # is_new but pin expired
    assert high_signal_candidates(user, today=TODAY, floor=90) == []
    _score(user, ext="notnew", is_new=False)
    assert high_signal_candidates(user, today=TODAY, floor=90) == []


@pytest.mark.django_db
def test_gate_deadline_window(user) -> None:
    _score(user, ext="soon", deadline_days=3)  # < 7
    _score(user, ext="far", deadline_days=200)  # > 120
    _score(user, ext="ok", deadline_days=30)
    cands = high_signal_candidates(user, today=TODAY, floor=90)
    assert {c.content_id for c in cands} == {
        str(RelevanceScore.objects.get(content__external_id="ok").content_id)
    }


@pytest.mark.django_db
def test_high_signal_respects_weekly_cap(user) -> None:
    for i in range(4):
        _score(user, ext=f"g{i}", match=90 + i)  # all qualify
    delivered = deliver_high_signal(user, today=TODAY, floor=90, cap=2)
    assert delivered == 2
    assert Notification.objects.filter(kind=Notification.Kind.HIGH_SIGNAL).count() == 2


@pytest.mark.django_db
def test_high_signal_same_item_never_twice(user) -> None:
    _score(user, ext="g1")
    assert deliver_high_signal(user, today=TODAY, floor=90, cap=5) == 1
    # A later run finds the same item already alerted → nothing new.
    assert deliver_high_signal(user, today=TODAY, floor=90, cap=5) == 0
    assert Notification.objects.filter(kind=Notification.Kind.HIGH_SIGNAL).count() == 1


@pytest.mark.django_db
def test_shadow_report_counts_without_delivering(db) -> None:
    u1 = User.objects.create_user("u1")
    u2 = User.objects.create_user("u2")
    _score(u1, ext="a")
    _score(u1, ext="b")
    _score(u2, ext="c")
    report = shadow_report([u1, u2], today=TODAY, floor=90)
    assert report["users_with_candidates"] == 2
    assert report["total_candidates"] == 3
    assert report["max_per_user"] == 2
    assert Notification.objects.count() == 0  # shadow: nothing delivered


@pytest.mark.django_db
def test_shadow_report_abstains_at_high_floor(user) -> None:
    _score(user, ext="g1", match=91)
    report = shadow_report([user], today=TODAY, floor=95)  # nothing clears 95
    assert report["users_with_candidates"] == 0
    assert report["total_candidates"] == 0


@pytest.mark.django_db
def test_command_refuses_delivery_when_disabled(user, settings) -> None:
    from django.core.management import call_command

    _score(user, ext="g1")
    settings.HIGH_SIGNAL_DELIVERY_ENABLED = False
    call_command("high_signal_shadow", "--deliver", "--user", "hs-user")
    assert Notification.objects.count() == 0  # calibration-gated: nothing sent


@pytest.mark.django_db
def test_command_delivers_when_enabled(user, settings) -> None:
    from apps.billing.models import Subscription, Tier
    from django.core.management import call_command

    # High-signal delivery is a scheduled push, so it runs only for entitled users
    # (select_users gates on SCHEDULED_REPORTS) — entitle this one with Spore.
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    _score(user, ext="g1")
    settings.HIGH_SIGNAL_DELIVERY_ENABLED = True
    # Pin the command's clock to the fixtures' date; the freshness window is only
    # a few days wide, so without this the test rots the moment the real date moves.
    call_command(
        "high_signal_shadow",
        "--deliver",
        "--floor",
        "90",
        "--user",
        "hs-user",
        "--today",
        TODAY.isoformat(),
    )
    assert Notification.objects.filter(kind=Notification.Kind.HIGH_SIGNAL).count() == 1
