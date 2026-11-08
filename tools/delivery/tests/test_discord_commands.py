"""What the five slash commands do, and — more importantly — refuse to do.

No gateway here: every command is a plain function taking a snowflake and returning
``(status, payload)``, which is exactly why it can be tested this way.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from apps.accounts.models import Lab, LabMembership
from apps.billing.testing import entitle_user, paid_plan
from apps.integrations.models import DiscordIdentity
from apps.integrations.tests.base import (
    clear_discord_cache,
    discord_test_settings,
    grant_bot_server,
)
from django.contrib.auth.models import User

from tools.delivery import discord_commands as cmd
from tools.delivery.models import DailyBriefing, ReminderSubscription, SavedOpportunity
from tools.delivery.reminders import create_subscription
from tools.retrieval.models import ContentDeadline, ContentItem

SNOWFLAKE = "900000000000000020"
OTHER = "900000000000000021"
TODAY = date(2026, 7, 16)
_Kind = SavedOpportunity.DeadlineKind
_Area = SavedOpportunity.Area


@pytest.fixture(autouse=True)
def _discord_settings():
    with discord_test_settings:
        clear_discord_cache()
        yield
        clear_discord_cache()


def _linked(username="dc-user", snowflake=SNOWFLAKE, *, paid=True):
    """A Discord-linked user, by default on a paid plan.

    Paid by default because reminders — which most of these commands act on — need
    one. ``paid=False`` is for the tests that are specifically about what a Free
    account is told.
    """
    user = User.objects.create_user(username)
    DiscordIdentity.objects.create(
        user=user,
        discord_user_id=snowflake,
        state=DiscordIdentity.State.ACTIVE,
        link_method=DiscordIdentity.LinkMethod.OAUTH,
    )
    if paid:
        paid_plan(user)
    return user


def _grant(external_id="g-1", due=None):
    item = ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="pivot",
        external_id=external_id,
        metadata={"title": "Neural interfaces grant"},
    )
    if due:
        ContentDeadline.objects.create(
            content=item,
            kind=_Kind.APPLICATION,
            due_date=due,
            confidence=ContentDeadline.Confidence.CONFIRMED,
        )
    return item


def _reminder(user=None, lab=None, due=None, title="Neural grant"):
    due = due or TODAY + timedelta(days=30)
    return create_subscription(
        target_user=user,
        target_lab=lab,
        content=_grant(f"g-{title}-{due}", due),
        deadline_kind=_Kind.APPLICATION,
        area=_Area.GRANT,
        title=title,
        due_date=due,
        offsets=[(1, "week")],
        created_by=user,
        today=TODAY,
    )


# --------------------------------------------------------------------------- #
# Everything refuses an unlinked caller
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
@pytest.mark.parametrize(
    "call",
    [
        lambda: cmd.search(SNOWFLAKE, "anything"),
        lambda: cmd.digest(SNOWFLAKE),
        lambda: cmd.saves(SNOWFLAKE),
        lambda: cmd.snooze(SNOWFLAKE, reminder_id="x"),
        lambda: cmd.cancel(SNOWFLAKE, reminder_id="x"),
    ],
)
def test_every_command_refuses_an_unlinked_caller(db, call) -> None:
    status, payload = call()
    assert status == "not_linked"
    assert "Mycelium" in payload["message"]


# --------------------------------------------------------------------------- #
# /mylo digest
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_digest_returns_todays_report(db) -> None:
    user = _linked()
    DailyBriefing.objects.create(
        user=user, body="Three papers matter today.", counts={"papers": 3}
    )

    status, payload = cmd.digest(SNOWFLAKE)

    assert status == "ok"
    assert payload["stale"] is False
    assert payload["counts"] == {"papers": 3}
    assert "Three papers" in payload["body"]


@pytest.mark.django_db
def test_a_free_user_is_told_plainly_rather_than_shown_a_hollow_report(db) -> None:
    """Free is never run through the daily pipeline, so there is genuinely nothing.

    Saying so — and naming what Spore adds — beats assembling something
    report-shaped from whatever happens to be stored.
    """
    _linked(paid=False)

    status, payload = cmd.digest(SNOWFLAKE)

    assert status == "none"
    assert "Spore" in payload["message"]
    assert "hasn't written you a report" in payload["message"]


@pytest.mark.django_db
def test_an_entitled_user_with_no_report_yet_is_told_it_is_coming(db) -> None:
    """A different, and honest, message: entitled means one *will* be written."""
    _linked()  # paid by default

    status, payload = cmd.digest(SNOWFLAKE)

    assert status == "none"
    assert "Spore" not in payload["message"]
    assert "each morning" in payload["message"]


@pytest.mark.django_db
def test_a_stale_report_is_returned_but_named_as_stale(db) -> None:
    """Never quietly present yesterday's report as today's."""
    from django.utils import timezone

    user = _linked()
    two_days_ago = timezone.localdate() - timedelta(days=2)
    DailyBriefing.objects.create(
        user=user, body="Older news.", generated_on=two_days_ago
    )

    status, payload = cmd.digest(SNOWFLAKE)

    assert status == "ok"
    assert payload["stale"] is True
    assert payload["generated_on"] == two_days_ago.isoformat()


@pytest.mark.django_db
def test_a_lab_digest_needs_membership_and_the_bot_addon(db) -> None:
    user = _linked()
    lab = Lab.objects.create(name="Neuro", slug="neuro")
    grant_bot_server(lab)

    # Not a member yet — indistinguishable from a lab that does not exist.
    status, _ = cmd.digest(SNOWFLAKE, lab_slug="neuro")
    assert status == "forbidden"

    LabMembership.objects.create(user=user, lab=lab, role=LabMembership.Role.MEMBER)
    DailyBriefing.objects.create(lab=lab, body="Lab news.")
    status, payload = cmd.digest(SNOWFLAKE, lab_slug="neuro")
    assert status == "ok"
    assert payload["owner"] == "Neuro"


# --------------------------------------------------------------------------- #
# /mylo saves
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_saves_lists_newest_first_and_paginates(db) -> None:
    user = _linked()
    for i in range(7):
        SavedOpportunity.objects.create(
            user=user,
            content=_grant(f"s-{i}"),
            area=_Area.GRANT,
            title=f"Save {i}",
            deadline_kind=_Kind.APPLICATION,
        )

    status, first = cmd.saves(SNOWFLAKE, page=0)
    assert status == "ok"
    assert first["total"] == 7
    assert len(first["items"]) == cmd.SAVES_PAGE
    assert first["items"][0]["title"] == "Save 6"  # newest first
    assert first["has_more"] is True

    _, second = cmd.saves(SNOWFLAKE, page=1)
    assert len(second["items"]) == 2
    assert second["has_more"] is False


@pytest.mark.django_db
def test_saves_shows_only_your_own(db) -> None:
    user = _linked()
    stranger = User.objects.create_user("stranger")
    SavedOpportunity.objects.create(
        user=stranger,
        content=_grant("theirs"),
        area=_Area.GRANT,
        title="Not yours",
        deadline_kind=_Kind.APPLICATION,
    )
    SavedOpportunity.objects.create(
        user=user,
        content=_grant("mine"),
        area=_Area.GRANT,
        title="Mine",
        deadline_kind=_Kind.APPLICATION,
    )

    _, payload = cmd.saves(SNOWFLAKE)

    assert [i["title"] for i in payload["items"]] == ["Mine"]


@pytest.mark.django_db
def test_an_empty_saved_list_says_how_to_start(db) -> None:
    _linked()
    status, payload = cmd.saves(SNOWFLAKE)
    assert status == "empty"
    assert "bookmark" in payload["message"]


# --------------------------------------------------------------------------- #
# /mylo snooze
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_snooze_counts_from_when_you_asked_not_from_the_deadline(db) -> None:
    user = _linked()
    sub = _reminder(user=user, due=TODAY + timedelta(days=60))

    status, payload = cmd.snooze(
        SNOWFLAKE, reminder_id=str(sub.id), amount=1, unit="week", today=TODAY
    )

    assert status == "ok"
    assert payload["snoozed_until"] == (TODAY + timedelta(days=7)).isoformat()
    sub.refresh_from_db()
    assert sub.snoozed_until == TODAY + timedelta(days=7)


@pytest.mark.django_db
def test_snoozing_past_the_deadline_stops_at_the_deadline_and_says_so(db) -> None:
    """Otherwise 'snooze' would silently mean 'cancel'."""
    user = _linked()
    sub = _reminder(user=user, due=TODAY + timedelta(days=3))

    status, payload = cmd.snooze(
        SNOWFLAKE, reminder_id=str(sub.id), amount=6, unit="month", today=TODAY
    )

    assert status == "ok"
    assert payload["clamped"] is True
    assert payload["snoozed_until"] == (TODAY + timedelta(days=3)).isoformat()


@pytest.mark.django_db
def test_snoozing_twice_extends_rather_than_erroring(db) -> None:
    user = _linked()
    sub = _reminder(user=user, due=TODAY + timedelta(days=90))

    cmd.snooze(SNOWFLAKE, reminder_id=str(sub.id), amount=1, unit="week", today=TODAY)
    status, payload = cmd.snooze(
        SNOWFLAKE, reminder_id=str(sub.id), amount=2, unit="week", today=TODAY
    )

    assert status == "ok"
    assert payload["snoozed_until"] == (TODAY + timedelta(days=14)).isoformat()


@pytest.mark.django_db
def test_a_snoozed_reminder_is_deferred_not_swallowed(db) -> None:
    """The property that makes snooze safe: the offsets stay unsealed.

    When the snooze lapses the still-open offsets trigger together and the
    one-message-per-day collapse sends a single reminder — later, not never.
    """
    from tools.delivery.reminders_tick import run_tick

    user = _linked()
    due = TODAY + timedelta(days=7)
    sub = _reminder(user=user, due=due)  # its 1-week offset fires today

    cmd.snooze(SNOWFLAKE, reminder_id=str(sub.id), amount=3, unit="day", today=TODAY)
    assert run_tick(TODAY).fired == 0  # suppressed
    assert sub.fires.count() == 0  # and, crucially, nothing was sealed

    result = run_tick(TODAY + timedelta(days=3))  # the snooze has lapsed
    assert result.fired == 1
    assert result.notifications == 1


@pytest.mark.django_db
def test_you_cannot_snooze_someone_elses_reminder(db) -> None:
    _linked()
    stranger = User.objects.create_user("stranger")
    entitle_user(stranger)
    theirs = _reminder(user=stranger, title="Theirs")

    status, payload = cmd.snooze(SNOWFLAKE, reminder_id=str(theirs.id))

    assert status == "not_found"  # same answer as a reminder that does not exist
    theirs.refresh_from_db()
    assert theirs.snoozed_until is None


@pytest.mark.django_db
def test_a_malformed_id_reads_as_not_found_not_a_crash(db) -> None:
    _linked()
    status, _ = cmd.snooze(SNOWFLAKE, reminder_id="not-a-uuid")
    assert status == "not_found"


@pytest.mark.django_db
def test_a_lab_reminder_needs_management_not_mere_membership(db) -> None:
    """Silencing a lab reminder speaks for the whole lab, as creating one does."""
    user = _linked()
    lab = Lab.objects.create(name="Neuro", slug="neuro")
    owner = User.objects.create_user("owner")
    LabMembership.objects.create(user=owner, lab=lab, role=LabMembership.Role.OWNER)
    LabMembership.objects.create(user=user, lab=lab, role=LabMembership.Role.MEMBER)
    sub = _reminder(lab=lab, title="Lab grant")

    status, _ = cmd.snooze(SNOWFLAKE, reminder_id=str(sub.id))
    assert status == "not_found"

    LabMembership.objects.filter(user=user, lab=lab).update(
        role=LabMembership.Role.ADMIN
    )
    status, _ = cmd.snooze(
        SNOWFLAKE, reminder_id=str(sub.id), amount=1, unit="day", today=TODAY
    )
    assert status == "ok"


# --------------------------------------------------------------------------- #
# /mylo cancel
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_cancel_is_a_soft_stop_that_keeps_the_record(db) -> None:
    """'Why did this stop?' should have an answer."""
    user = _linked()
    sub = _reminder(user=user)

    status, payload = cmd.cancel(SNOWFLAKE, reminder_id=str(sub.id))

    assert status == "ok"
    assert payload["already"] is False
    sub.refresh_from_db()
    assert sub.state == ReminderSubscription.State.CANCELLED
    assert ReminderSubscription.objects.filter(pk=sub.pk).exists()


@pytest.mark.django_db
def test_cancelling_twice_confirms_rather_than_erroring(db) -> None:
    user = _linked()
    sub = _reminder(user=user)

    cmd.cancel(SNOWFLAKE, reminder_id=str(sub.id))
    status, payload = cmd.cancel(SNOWFLAKE, reminder_id=str(sub.id))

    assert status == "ok"
    assert payload["already"] is True


@pytest.mark.django_db
def test_a_cancelled_reminder_stops_firing(db) -> None:
    from tools.delivery.reminders_tick import run_tick

    user = _linked()
    sub = _reminder(user=user, due=TODAY + timedelta(days=7))
    cmd.cancel(SNOWFLAKE, reminder_id=str(sub.id))

    assert run_tick(TODAY).fired == 0


# --------------------------------------------------------------------------- #
# Autocomplete is part of the authorization surface
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_autocomplete_offers_only_what_you_may_act_on(db) -> None:
    """Offering a reminder you'd then be refused still tells you it exists."""
    user = _linked()
    stranger = User.objects.create_user("stranger")
    entitle_user(stranger)
    mine = _reminder(user=user, title="Mine")
    _reminder(user=stranger, title="Theirs")

    status, payload = cmd.list_manageable(SNOWFLAKE)

    assert status == "ok"
    assert [i["title"] for i in payload["items"]] == ["Mine"]
    assert payload["items"][0]["id"] == str(mine.id)


@pytest.mark.django_db
def test_autocomplete_filters_by_what_was_typed(db) -> None:
    user = _linked()
    _reminder(user=user, title="Neural grant", due=TODAY + timedelta(days=10))
    _reminder(user=user, title="Robotics fellowship", due=TODAY + timedelta(days=20))

    _, payload = cmd.list_manageable(SNOWFLAKE, prefix="robot")

    assert [i["title"] for i in payload["items"]] == ["Robotics fellowship"]
