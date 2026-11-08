"""Tagging roles, guild members, and @everyone from a lab alert.

Two things are being traded off here and both are tested. Widening mentions past
"a Mycelium user who is a member of this lab" is the point — a lab's Discord
holds collaborators and students with no Mycelium account, and the deadline is
about them too. But a raw snowflake is also exactly how Mylo could be pointed at
an unrelated server, and ``@everyone`` is the one target that cannot be
expressed as an id and so has to reopen the ``parse`` category that stops a
scraped conference title from pinging a whole guild.
"""

from __future__ import annotations

import pytest
from apps.integrations.services.discord_api import create_message

from tools.delivery.models import ReminderMention, ReminderSubscription
from tools.delivery.reminders_discord import _resolve_mentions, reminder_embed

pytestmark = pytest.mark.django_db


class _Rows(list):
    """Stands in for ``subscription.mentions`` — the queryset API used here."""

    def select_related(self, *_a):
        return self

    def all(self):
        return self


class _Sub:
    def __init__(self, rows):
        self.mentions = _Rows(rows)


def _row(kind, *, discord_id="", member=None, display_name=""):
    return ReminderMention(
        kind=kind, discord_id=discord_id, member=member, display_name=display_name
    )


# --- what gets pinged ------------------------------------------------------


def test_a_role_is_pinged_as_a_role_not_a_user():
    """``<@&id>`` and ``<@id>`` are different mentions; getting it wrong pings
    nobody and looks like a broken message."""
    targets = _resolve_mentions(
        _Sub([_row(ReminderMention.Kind.ROLE, discord_id="42", display_name="PIs")])
    )
    assert targets.role_ids == ["42"]
    assert targets.user_ids == []
    assert targets.line() == "<@&42>"
    assert targets.allowed_mentions()["roles"] == ["42"]


def test_a_guild_member_with_no_mycelium_account_is_still_pinged():
    """The reason raw ids are accepted at all: a collaborator in the lab's
    Discord who never signed up for Mycelium."""
    targets = _resolve_mentions(
        _Sub([_row(ReminderMention.Kind.USER, discord_id="7", display_name="Sam")])
    )
    assert targets.user_ids == ["7"]
    assert targets.plain_names == []
    assert targets.line() == "<@7>"


def test_everyone_is_a_parse_category_not_an_id():
    targets = _resolve_mentions(_Sub([_row(ReminderMention.Kind.EVERYONE)]))
    assert targets.everyone is True
    assert targets.line() == "@everyone"
    assert targets.allowed_mentions()["everyone"] is True


def test_mixed_targets_all_survive_into_one_line():
    targets = _resolve_mentions(
        _Sub(
            [
                _row(ReminderMention.Kind.EVERYONE),
                _row(ReminderMention.Kind.ROLE, discord_id="9"),
                _row(ReminderMention.Kind.USER, discord_id="3"),
            ]
        )
    )
    assert targets.line() == "@everyone <@&9> <@3>"


# --- what must never get pinged -------------------------------------------


def _sent(monkeypatch):
    """Capture the body ``create_message`` would send, without a network call."""
    captured = {}

    def fake_request(method, path, *, auth=None, json_body=None, **_kw):
        captured["body"] = json_body

        class _Resp:
            status = 200
            json = {"id": "1"}

        return _Resp()

    monkeypatch.setattr(
        "apps.integrations.services.discord_api._request", fake_request
    )
    monkeypatch.setattr(
        "apps.integrations.services.discord_api._bot_token", lambda: "t"
    )
    return captured


def test_parse_stays_empty_unless_a_human_asked_for_everyone(monkeypatch):
    """The default has to stay closed. Reminder bodies interpolate scraped
    third-party text, and nothing about a scrape may widen what it can ping."""
    captured = _sent(monkeypatch)
    create_message("c1", content="<@5>", allowed_mentions={"users": ["5"]})
    assert captured["body"]["allowed_mentions"]["parse"] == []

    create_message("c1", content="hi")
    assert captured["body"]["allowed_mentions"]["parse"] == []


def test_everyone_opens_the_parse_category_only_when_passed(monkeypatch):
    captured = _sent(monkeypatch)
    create_message("c1", content="@everyone", allowed_mentions={"everyone": True})
    assert captured["body"]["allowed_mentions"]["parse"] == ["everyone"]


def test_a_scraped_title_containing_everyone_can_never_ping(monkeypatch):
    """The guarantee that actually matters, and it holds *with* the category
    open: the escaping is on the interpolated text, not on the parse rule."""
    embed = reminder_embed("@everyone submit to our conference!", "body")
    assert "@everyone" not in embed["title"]
    assert "@​everyone" in embed["title"]

    captured = _sent(monkeypatch)
    create_message("c1", embed=embed, allowed_mentions={"everyone": True})
    assert "@everyone" not in captured["body"]["embeds"][0]["title"]


def test_an_unlinked_mycelium_member_is_named_never_dropped(django_user_model):
    """Silently omitting someone produces an alert that reaches fewer people
    than whoever set it believes."""
    user = django_user_model.objects.create_user("nolink", first_name="Dana")
    targets = _resolve_mentions(
        _Sub([_row(ReminderMention.Kind.USER, member=user)])
    )
    assert targets.user_ids == []
    assert targets.plain_names == ["Dana"]
    assert "Dana" in targets.line()


def test_a_subscription_cannot_collect_two_everyone_rows(django_user_model):
    """A second @everyone would only double the ping."""
    from django.db import IntegrityError, transaction

    user = django_user_model.objects.create_user("owner")
    sub = ReminderSubscription.objects.create(
        target_user=user, deadline_kind="application", area="grant", title="G"
    )
    ReminderMention.objects.create(
        subscription=sub, kind=ReminderMention.Kind.EVERYONE
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        ReminderMention.objects.create(
            subscription=sub, kind=ReminderMention.Kind.EVERYONE
        )
