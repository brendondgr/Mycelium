"""``/mylo populate``: fill a server's forums with the target's best open items.

It tops each forum up to ``count`` (so a second run posts nothing), keeps every
earlier decision (held back, deleted by hand), lets the editor skip, spends at most
``2 × count`` editor calls per kind, and refuses until announcements are on and
seeded — the seed is what stops the next nightly run announcing the backlog.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from apps.accounts.models import Lab
from apps.integrations.testing import add_route, bind
from django.utils import timezone

from tools.delivery import announce_populate
from tools.delivery.models import Announcement, AnnouncementPost, AnnouncementSettings
from tools.recommendation.models import RelevanceScore
from tools.retrieval.models import ContentItem

TODAY = timezone.localdate()


@pytest.fixture
def on(settings, fake):
    settings.OPPORTUNITY_ANNOUNCEMENTS_ENABLED = True
    settings.BILLING_ENFORCE_ENTITLEMENTS = False
    return fake


def _lab(*, enabled=True, seeded=True):
    lab = Lab.objects.create(name="Reef Lab", slug="reef")
    AnnouncementSettings.objects.create(
        target_lab=lab,
        enabled=enabled,
        seeded_at=timezone.now() if seeded else None,
        grants=True,
        fellowships=False,
        conferences=False,
    )
    binding = bind(lab=lab, guild_id="g1")
    add_route(binding, "grants", "forum-g1", forum_tag_ids={"Already open": "t-open"})
    return lab, binding


def _grants(lab, n):
    items = []
    for i in range(n):
        due = (TODAY + timedelta(days=40 + i)).isoformat()
        item = ContentItem.objects.create(
            type=ContentItem.Type.GRANT,
            source="open-collector",
            external_id=f"pop-{i}",
            source_url=f"https://example.org/{i}",
            metadata={
                "title": f"Call {i}",
                "status": "open",
                "funder": "NSF",
                "deadline_date": due,
                "prune_after": due,
            },
        )
        RelevanceScore.objects.create(
            content=item,
            target_lab=lab,
            score=1 / (i + 1),
            signals={
                "suggested": True,
                "cluster_slates": {
                    "c1": {
                        "label": "Ocean",
                        "rank": i + 1,
                        "of": 10,
                        "entered_on": TODAY.isoformat(),
                        "is_new": True,
                    }
                },
            },
        )
        items.append(item)
    return items


def _threads(fake) -> list[str]:
    return [
        b["name"]
        for m, p, b in fake.calls
        if m == "POST" and p == "/channels/forum-g1/threads"
    ]


@pytest.mark.django_db
def test_it_tops_each_forum_up_to_the_count_and_a_second_run_posts_nothing(on):
    lab, binding = _lab()
    _grants(lab, 8)

    status, payload = announce_populate.populate(binding, 3, complete=None)

    assert status == "ok"
    assert _threads(on) == ["Call 0", "Call 1", "Call 2"]
    posted = Announcement.objects.filter(state=Announcement.State.POSTED)
    assert {a.origin for a in posted} == {Announcement.Origin.MANUAL}
    assert {a.label for a in posted} == {Announcement.Label.ALREADY_OPEN}
    assert "posted **3**" in payload["message"]

    on.calls.clear()
    announce_populate.populate(binding, 3, complete=None)
    assert _threads(on) == []

    announce_populate.populate(binding, 5, complete=None)
    assert _threads(on) == ["Call 3", "Call 4"]  # asking for more tops up


@pytest.mark.django_db
def test_earlier_decisions_are_kept(on):
    lab, binding = _lab()
    items = _grants(lab, 5)
    Announcement.objects.create(
        target_lab=lab,
        content=items[0],
        category="grant",
        state=Announcement.State.SKIPPED,
        snapshot={},
    )
    deleted = Announcement.objects.create(
        target_lab=lab,
        content=items[1],
        category="grant",
        state=Announcement.State.POSTED,
        snapshot={"title": "Call 1"},
    )
    AnnouncementPost.objects.create(
        announcement=deleted,
        binding=binding,
        channel_id="forum-g1",
        thread_id="t1",
        deleted_at=timezone.now(),
    )
    Announcement.objects.create(
        target_lab=lab,
        content=items[2],
        category="grant",
        state=Announcement.State.SEEDED_SEEN,
        snapshot={},
    )

    announce_populate.populate(binding, 2, complete=None)

    # Held back and deleted by hand stay out; passed over at activation comes in.
    assert _threads(on) == ["Call 2", "Call 3"]


@pytest.mark.django_db
def test_an_editor_skip_moves_on_and_the_budget_bounds_model_calls(on):
    lab, binding = _lab()
    _grants(lab, 10)
    calls = []

    def skip_all(prompt):
        calls.append(prompt)
        return json.dumps({"announce": False, "skip_reason": "Weak fit"})

    status, payload = announce_populate.populate(binding, 2, complete=skip_all)

    assert status == "ok" and _threads(on) == []
    assert len(calls) == 4  # 2 × count
    assert Announcement.objects.filter(state=Announcement.State.SKIPPED).count() == 4
    assert "every open one Mylo would post" in payload["message"]


@pytest.mark.django_db
def test_a_target_already_posted_elsewhere_is_posted_here_too(on):
    lab, binding = _lab()
    (item,) = _grants(lab, 1)
    other = bind(lab=lab, guild_id="g2")
    add_route(other, "grants", "forum-g2")
    ann = Announcement.objects.create(
        target_lab=lab,
        content=item,
        category="grant",
        state=Announcement.State.POSTED,
        snapshot={"title": "Call 0"},
        write_up={
            "announce": True,
            "headline": "Call 0",
            "why_it_matters": "Fits.",
            "who_should_look": [],
            "next_step": "Read it.",
        },
    )
    AnnouncementPost.objects.create(
        announcement=ann, binding=other, channel_id="forum-g2", thread_id="t2"
    )

    announce_populate.populate(binding, 1, complete=None)

    assert _threads(on) == ["Call 0"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("enabled", "seeded", "status"), [(False, True, "not_on"), (True, False, "not_on")]
)
def test_it_refuses_until_announcements_are_on_and_seeded(on, enabled, seeded, status):
    lab, binding = _lab(enabled=enabled, seeded=seeded)
    _grants(lab, 3)
    assert announce_populate.populate(binding, 3, complete=None)[0] == status
    assert _threads(on) == []


@pytest.mark.django_db
def test_it_refuses_when_the_instance_has_announcements_off(on, settings):
    settings.OPPORTUNITY_ANNOUNCEMENTS_ENABLED = False
    lab, binding = _lab()
    assert announce_populate.populate(binding, 3, complete=None)[0] == "switched_off"


@pytest.mark.django_db
def test_a_kind_with_no_forum_here_is_reported(on):
    lab, binding = _lab()
    AnnouncementSettings.objects.filter(target_lab=lab).update(conferences=True)

    _status, payload = announce_populate.populate(binding, 2, complete=None)

    assert "**Conferences:** no forum set up here." in payload["message"]


@pytest.mark.django_db
def test_the_count_is_clamped():
    assert announce_populate.MAX_COUNT == 10
    lab, binding = _lab(enabled=False)
    # Refused before anything runs, whatever count is asked for.
    assert announce_populate.populate(binding, 99, complete=None)[0] in (
        "switched_off",
        "not_on",
    )
