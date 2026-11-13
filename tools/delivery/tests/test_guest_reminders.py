"""Remind me without a Mycelium account.

Anyone in the server a post was made in may set a reminder for themselves: the
guest gate still rate-limits, still checks the post's binding sits in this server,
and still needs the plan to cover it. A guest's reminder is a nudge keyed on their
Discord id, by DM or as a thread tag, it follows a moved date, and it carries a
Stop reminding me button. Nothing else opens up: Interested and Not for us still
need a member.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from apps.integrations.models import DiscordOutboxMessage

from tools.delivery import announcement_actions, discord_announcements
from tools.delivery.models import AnnouncementNudge, AnnouncementReaction
from tools.delivery.tests.test_discord_announcements import (
    TODAY,
    _announce,
    _grant,
    _member,
    _setup,
)

GUEST = "424242"


@pytest.fixture
def entitled(monkeypatch):
    monkeypatch.setattr(
        "apps.integrations.services.gate._lab_entitled", lambda lab, f: (True, "")
    )


def _post(days=40):
    target, _ = _setup()
    ann, _ = _announce(target, _grant(TODAY + timedelta(days=days)))
    return target, ann, ann.posts.get()


@pytest.mark.django_db
def test_a_guest_sets_a_dm_reminder_that_arrives_and_can_be_stopped(
    fake, entitled
) -> None:
    _target, ann, post = _post(days=30)

    status, payload = announcement_actions.remind_options(GUEST, post.id, "g1")
    assert status == "ok" and payload["options"], payload
    status, payload = announcement_actions.remind_set(
        GUEST, post.id, ["2w"], "dm", "g1"
    )
    assert status == "ok", payload
    assert "No Mycelium account needed" in payload["message"]
    nudge = AnnouncementNudge.objects.get(discord_user_id=GUEST)
    assert nudge.user is None and nudge.delivery == AnnouncementNudge.Delivery.DM

    assert discord_announcements.send_due_nudges(TODAY) == 0  # not due yet
    day = TODAY + timedelta(days=16)
    assert discord_announcements.send_due_nudges(day) == 1
    assert discord_announcements.send_due_nudges(day) == 0  # never twice
    dm = DiscordOutboxMessage.objects.get(kind="announcement_nudge")
    assert dm.recipient_user is None and dm.recipient_discord_id == GUEST
    discord_announcements.flush()
    opened = [b for m, p, b in fake.calls if p == "/users/@me/channels"]
    assert opened and opened[-1]["recipient_id"] == GUEST
    sent = [b for m, p, b in fake.calls if p == "/channels/dm-chan/messages"]
    buttons = sent[-1]["components"][0]["components"]
    assert buttons[-1]["custom_id"] == f"ann:{post.id}:unremind"
    # No reaction rows: those need a Mycelium user.
    assert not AnnouncementReaction.objects.filter(announcement=ann).exists()

    status, payload = announcement_actions.unremind(GUEST, post.id)
    assert status == "ok" and "No more reminders" in payload["message"]
    assert not AnnouncementNudge.objects.get(pk=nudge.pk).active


@pytest.mark.django_db
def test_a_guest_thread_reminder_tags_exactly_them(fake, entitled) -> None:
    _target, _ann, post = _post(days=30)
    announcement_actions.remind_set(GUEST, post.id, ["2w"], "thread", "g1")

    assert discord_announcements.send_due_nudges(TODAY + timedelta(days=16)) == 1

    row = DiscordOutboxMessage.objects.get(kind="announcement_nudge")
    assert row.channel_id == post.thread_id
    assert f"<@{GUEST}>" in row.content
    assert row.allowed_mentions == {"users": [GUEST]}


@pytest.mark.django_db
def test_a_member_of_another_lab_is_a_guest_here(fake, entitled) -> None:
    """Linked to Mycelium but not in this lab: reminders yes, as a guest."""
    target, _ann, post = _post()
    from apps.accounts.models import Lab

    other = Lab.objects.create(name="Other", slug="other")
    _member(other, "outsider", "515151")

    status, _ = announcement_actions.remind_set("515151", post.id, ["1w"], "dm", "g1")

    assert status == "ok"
    nudge = AnnouncementNudge.objects.get(discord_user_id="515151")
    assert nudge.user is None


@pytest.mark.django_db
def test_the_guest_gate_still_checks_the_server_and_the_plan(fake) -> None:
    _target, _ann, post = _post()

    # The lab's plan does not cover Mylo in Discord: no reminder.
    status, payload = announcement_actions.remind_set(
        GUEST, post.id, ["1w"], "dm", "g1"
    )
    assert status == "not_entitled", payload
    assert not AnnouncementNudge.objects.exists()


@pytest.mark.django_db
def test_a_click_from_another_server_is_refused(fake, entitled) -> None:
    _target, _ann, post = _post()

    status, _ = announcement_actions.remind_set(GUEST, post.id, ["1w"], "dm", "g9")
    no_guild, _ = announcement_actions.remind_set(GUEST, post.id, ["1w"], "dm", "")

    assert (status, no_guild) == ("forbidden", "forbidden")
    assert not AnnouncementNudge.objects.exists()


@pytest.mark.django_db
def test_interested_still_needs_a_member_and_points_guests_to_remind_me(
    fake, entitled
) -> None:
    _target, ann, post = _post()

    status, payload = announcement_actions.interested(GUEST, post.id, "g1")

    assert status == "not_linked"
    assert "Remind me" in payload["message"]
    assert not AnnouncementReaction.objects.filter(announcement=ann).exists()


@pytest.mark.django_db
def test_stop_reminding_me_touches_only_your_own(fake, entitled) -> None:
    _target, _ann, post = _post()
    announcement_actions.remind_set(GUEST, post.id, ["1w"], "dm", "g1")
    announcement_actions.remind_set("737373", post.id, ["1w"], "dm", "g1")

    announcement_actions.unremind(GUEST, post.id)

    active = AnnouncementNudge.objects.filter(active=True)
    assert [n.discord_user_id for n in active] == ["737373"]
