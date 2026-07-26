"""The lab digest finally reaches the channel labs have been configuring all along.

The load-bearing assertion is idempotency: one post per lab per day, and re-running
the daily pipeline produces no second post.
"""

from __future__ import annotations

from datetime import date

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import Lab
from apps.content.lab_digest import (
    compile_lab_digest,
    eligible_labs,
    queue_lab_digest,
)
from apps.content.models import ContentItem, RelevanceScore
from apps.integrations.models import DiscordGuildLink, DiscordOutboxMessage
from apps.integrations.tests.base import (
    clear_discord_cache,
    discord_test_settings,
    grant_bot_server,
)

TODAY = date(2026, 7, 16)


@pytest.fixture(autouse=True)
def _discord_settings():
    with discord_test_settings:
        clear_discord_cache()
        yield
        clear_discord_cache()


def _lab(slug="neuro", *, addon=True, channel="updates-chan", state=None):
    lab = Lab.objects.create(name=f"Lab {slug}", slug=slug)
    if addon:
        grant_bot_server(lab)
    DiscordGuildLink.objects.create(
        lab=lab,
        guild_id=f"g-{slug}",
        state=state or DiscordGuildLink.State.ACTIVE,
        updates_channel_id=channel,
    )
    return lab


def _scored(lab, *, title, cluster="", category=ContentItem.Type.PAPER, percent=80):
    item = ContentItem.objects.create(
        type=category,
        source="pivot",
        external_id=f"{title}-{cluster}",
        metadata={"title": title},
    )
    RelevanceScore.objects.create(
        content=item,
        target_lab=lab,
        score=0.9,
        signals={
            "suggested": True,
            "match_percent": percent,
            "cluster_label": cluster,
            "cluster_id": cluster.lower().replace(" ", "-") if cluster else "",
            "area": category,
            "run_at": "2026-07-16T00:00:00Z",
        },
    )
    return item


# --------------------------------------------------------------------------- #
# Eligibility — every condition checked at delivery, not trusted from setup
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_a_configured_entitled_lab_is_eligible(db) -> None:
    lab = _lab()
    assert eligible_labs([lab]) == [lab]


@pytest.mark.django_db
def test_a_lapsed_addon_goes_quiet(db) -> None:
    """The check has to happen at delivery, or it never happens at all."""
    lab = _lab(addon=False)
    assert eligible_labs([lab]) == []


@pytest.mark.django_db
def test_a_blank_channel_is_a_silent_opt_out(db) -> None:
    """A lab that turned this off should not hear about it every morning."""
    lab = _lab(channel="")
    assert eligible_labs([lab]) == []


@pytest.mark.django_db
def test_a_kicked_guild_is_not_posted_to(db) -> None:
    lab = _lab(state=DiscordGuildLink.State.KICKED)
    assert eligible_labs([lab]) == []


# --------------------------------------------------------------------------- #
# Content
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_the_digest_groups_by_research_theme(db) -> None:
    lab = _lab()
    _scored(lab, title="Segmentation nets", cluster="Medical AI")
    _scored(lab, title="Imaging call", cluster="Medical AI",
            category=ContentItem.Type.GRANT)
    _scored(lab, title="Soft actuators", cluster="Robotics")

    digest = compile_lab_digest(lab, on=TODAY)

    labels = [t.label for t in digest.themes]
    assert set(labels) == {"Medical AI", "Robotics"}
    # Busiest theme first: a channel post is skimmed, so the lab's main focus leads.
    assert labels[0] == "Medical AI"
    assert digest.total == 3


@pytest.mark.django_db
def test_unattributed_items_are_still_reported(db) -> None:
    """They must not vanish just because they carry no theme."""
    lab = _lab()
    _scored(lab, title="Themed", cluster="Medical AI")
    _scored(lab, title="Themeless", cluster="")

    digest = compile_lab_digest(lab, on=TODAY)

    assert digest.total == 2
    assert [i["title"] for i in digest.ungrouped] == ["Themeless"]


@pytest.mark.django_db
def test_a_quiet_day_posts_nothing(db) -> None:
    """A daily 'I found nothing' trains people to ignore the channel."""
    lab = _lab()

    row, created = queue_lab_digest(lab, on=TODAY)

    assert created is False
    assert DiscordOutboxMessage.objects.count() == 0


# --------------------------------------------------------------------------- #
# Idempotency — the guarantee introducing a queue is most likely to break
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_one_post_per_lab_per_day(db) -> None:
    lab = _lab()
    _scored(lab, title="Something", cluster="Medical AI")

    _row, first = queue_lab_digest(lab, on=TODAY)
    _row, second = queue_lab_digest(lab, on=TODAY)
    _row, third = queue_lab_digest(lab, on=TODAY)

    assert first is True
    assert second is False and third is False
    assert DiscordOutboxMessage.objects.count() == 1


@pytest.mark.django_db
def test_the_next_day_is_a_new_post(db) -> None:
    lab = _lab()
    _scored(lab, title="Something", cluster="Medical AI")

    queue_lab_digest(lab, on=TODAY)
    _row, created = queue_lab_digest(lab, on=date(2026, 7, 17))

    assert created is True
    assert DiscordOutboxMessage.objects.count() == 2


@pytest.mark.django_db
def test_two_labs_do_not_share_a_key(db) -> None:
    a, b = _lab("alpha"), _lab("beta")
    _scored(a, title="A item", cluster="Medical AI")
    _scored(b, title="B item", cluster="Robotics")

    queue_lab_digest(a, on=TODAY)
    queue_lab_digest(b, on=TODAY)

    assert DiscordOutboxMessage.objects.count() == 2


# --------------------------------------------------------------------------- #
# The post itself
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_the_post_goes_to_the_updates_channel_and_pings_nobody(db) -> None:
    """It is an update, not a summons."""
    lab = _lab()
    _scored(lab, title="Something", cluster="Medical AI")

    queue_lab_digest(lab, on=TODAY)

    row = DiscordOutboxMessage.objects.get()
    assert row.channel_id == "updates-chan"
    assert row.lab_id == lab.id
    assert not row.content  # no mention line at all
    assert row.embed["title"].startswith("Lab neuro")


@pytest.mark.django_db
def test_the_post_stays_inside_discords_embed_limits(db) -> None:
    """Bounded by construction — at most eight themes of three items."""
    lab = _lab()
    for theme in range(12):
        for n in range(6):
            _scored(lab, title=f"Item {theme}-{n}", cluster=f"Theme {theme}")

    digest = compile_lab_digest(lab, on=TODAY)
    queue_lab_digest(lab, on=TODAY, digest=digest)
    row = DiscordOutboxMessage.objects.get()

    assert len(digest.themes) <= 8
    assert all(len(t.items) <= 3 for t in digest.themes)
    assert len(row.embed["fields"]) <= 25
    assert len(str(row.embed)) < 6000


@pytest.mark.django_db
def test_the_digest_reads_the_same_scores_as_the_labs_feed(db) -> None:
    """It must not become a second source of truth."""
    lab = _lab()
    User.objects.create_user("member")
    _scored(lab, title="Shown", cluster="Medical AI", percent=90)
    # An unsuggested row is not in the lab's feed, so it is not in the digest.
    item = ContentItem.objects.create(
        type=ContentItem.Type.PAPER, source="pivot", external_id="hidden",
        metadata={"title": "Hidden"},
    )
    RelevanceScore.objects.create(
        content=item, target_lab=lab, score=0.1,
        signals={"suggested": False, "match_percent": 10, "area": "paper"},
    )

    digest = compile_lab_digest(lab, on=TODAY)

    titles = [i["title"] for t in digest.themes for i in t.items]
    assert "Shown" in titles
    assert "Hidden" not in titles
