"""The reminder gate: a paid plan **and** synced Discord, or no reminder.

Two independent conditions, checked in three places — when a reminder is created,
when Mylo tries to deliver it, and on the read endpoint the UI locks its button
with. These assert all three agree, that the refusal names *which* condition is
missing (a user told "unavailable" learns nothing), and that the rule is the same
for grants, fellowships and conferences.

The case that matters most for real researchers is
``test_a_member_whose_lab_pays_for_their_seat_is_entitled``: someone with no plan of
their own, seated on a lab's, must be able to set personal reminders.
"""

from __future__ import annotations

from datetime import date

import pytest
from apps.accounts.models import Lab, LabMembership
from apps.billing.models import Seat, Subscription, Tier
from apps.billing.testing import entitle_lab, entitle_user, link_discord
from apps.integrations.testing import bind
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from tools.delivery.models import ReminderSubscription, SavedOpportunity
from tools.delivery.reminder_access import (
    Reason,
    lab_reminder_access,
    personal_reminder_access,
)
from tools.delivery.reminders import ReminderAccessError, create_subscription
from tools.delivery.reminders_discord import send_lab_channel, send_personal_dm
from tools.retrieval.models import ContentDeadline, ContentItem

DUE = date(2026, 12, 1)
_Kind = SavedOpportunity.DeadlineKind
_Area = SavedOpportunity.Area


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _item(kind=ContentItem.Type.GRANT, ext="g1"):
    """A dated opportunity of any of the three remindable types."""
    titles = {
        ContentItem.Type.GRANT: {"title": "Neural grant"},
        ContentItem.Type.FELLOWSHIP: {"title": "Neural fellowship"},
        ContentItem.Type.CONFERENCE: {"name": "Neural conference"},
    }
    item = ContentItem.objects.create(
        type=kind, source="pivot", external_id=ext, metadata=titles[kind]
    )
    ContentDeadline.objects.create(
        content=item,
        kind=_Kind.APPLICATION,
        due_date=DUE,
        confidence=ContentDeadline.Confidence.CONFIRMED,
    )
    return item


def _post(client, item, **extra):
    return client.post(
        "/api/reminders/",
        {
            "content_id": str(item.id),
            "deadline_kind": "application",
            "offsets": [{"amount": 1, "unit": "week"}],
            **extra,
        },
        format="json",
    )


# --------------------------------------------------------------------------- #
# Personal reminders
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_free_user_cannot_create_a_reminder(client) -> None:
    user = User.objects.create_user("free")
    link_discord(user)  # Discord alone is not enough
    client.force_authenticate(user)

    resp = _post(client, _item())

    assert resp.status_code == 403  # not 400: well-formed, just not permitted
    assert resp.data["reason"] == Reason.PLAN
    assert ReminderSubscription.objects.count() == 0


@pytest.mark.django_db
def test_paid_user_without_discord_cannot_create_a_reminder(client) -> None:
    user = User.objects.create_user("paid")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    client.force_authenticate(user)

    resp = _post(client, _item())

    assert resp.status_code == 403
    assert resp.data["reason"] == Reason.DISCORD
    assert resp.data["plan_ok"] is True  # the half they already have is acknowledged


@pytest.mark.django_db
def test_a_free_user_with_no_discord_is_told_about_both(client) -> None:
    client.force_authenticate(User.objects.create_user("nothing"))

    resp = _post(client, _item())

    assert resp.status_code == 403
    assert resp.data["reason"] == Reason.PLAN_AND_DISCORD


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("kind", "ext"),
    [
        (ContentItem.Type.GRANT, "g-ok"),
        (ContentItem.Type.FELLOWSHIP, "f-ok"),
        (ContentItem.Type.CONFERENCE, "c-ok"),
    ],
)
def test_entitled_user_can_remind_on_every_opportunity_type(client, kind, ext) -> None:
    """The gate is a property of the account, not of the feed it was opened from."""
    client.force_authenticate(entitle_user(User.objects.create_user("spore")))

    resp = _post(client, _item(kind, ext))

    assert resp.status_code == 201


@pytest.mark.django_db
def test_a_member_whose_lab_pays_for_their_seat_is_entitled(client) -> None:
    """No personal plan, one active seat on a lab's plan — reminders are theirs.

    This falls out of ``covering_subscriptions`` rather than a special case, and it
    is the whole point of the "or via a lab's paid membership" rule: a researcher
    should not have to buy a second plan to be reminded of a deadline.
    """
    lab = Lab.objects.create(name="Rivera Lab", slug="rivera")
    subscription = Subscription.objects.create(
        tier=Tier.LAB, scope_lab=lab, status=Subscription.Status.ACTIVE
    )
    member = User.objects.create_user("seated")
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)
    Seat.objects.create(
        subscription=subscription,
        member=member,
        payer_lab=lab,
        status=Seat.Status.ACTIVE,
    )
    link_discord(member)
    client.force_authenticate(member)

    assert Subscription.objects.filter(scope_user=member).count() == 0
    assert _post(client, _item()).status_code == 201


@pytest.mark.django_db
def test_a_revoked_seat_takes_the_entitlement_with_it(client) -> None:
    lab = Lab.objects.create(name="Rivera Lab", slug="rivera")
    subscription = Subscription.objects.create(
        tier=Tier.LAB, scope_lab=lab, status=Subscription.Status.ACTIVE
    )
    member = User.objects.create_user("ex-seated")
    Seat.objects.create(
        subscription=subscription,
        member=member,
        payer_lab=lab,
        status=Seat.Status.REVOKED,
    )
    link_discord(member)
    client.force_authenticate(member)

    assert _post(client, _item()).status_code == 403


# --------------------------------------------------------------------------- #
# Lab reminders — the lab's plan and the lab's server, not the manager's
# --------------------------------------------------------------------------- #
def _managed_lab(username="owner", *, slug="lab"):
    lab = Lab.objects.create(name="Lab", slug=slug)
    owner = User.objects.create_user(username)
    LabMembership.objects.create(user=owner, lab=lab, role=LabMembership.Role.OWNER)
    return lab, owner


@pytest.mark.django_db
def test_a_free_lab_cannot_hold_reminders(client) -> None:
    lab, owner = _managed_lab()
    bind(lab=lab, guild_id="g1", deadlines="chan")
    entitle_user(owner)  # the manager personally qualifies; the lab does not
    client.force_authenticate(owner)

    resp = _post(client, _item(), scope="lab", lab_slug="lab")

    assert resp.status_code == 403
    assert resp.data["reason"] == Reason.PLAN


@pytest.mark.django_db
def test_a_paid_lab_with_no_server_cannot_hold_reminders(client) -> None:
    """Nowhere to post is a real refusal, not something to discover on the tick."""
    lab, owner = _managed_lab()
    Subscription.objects.create(
        tier=Tier.LAB, scope_lab=lab, status=Subscription.Status.ACTIVE
    )
    entitle_user(owner)
    client.force_authenticate(owner)

    resp = _post(client, _item(), scope="lab", lab_slug="lab")

    assert resp.status_code == 403
    assert resp.data["reason"] == Reason.DISCORD


@pytest.mark.django_db
def test_an_unclaimed_server_does_not_count_as_synced() -> None:
    lab, _ = _managed_lab()
    Subscription.objects.create(
        tier=Tier.LAB, scope_lab=lab, status=Subscription.Status.ACTIVE
    )
    bind(lab=lab, state="pending_setup", guild_id="g1")

    access = lab_reminder_access(lab)

    assert access.allowed is False
    assert access.discord_ok is False


@pytest.mark.django_db
def test_an_entitled_lab_can_hold_reminders(client) -> None:
    lab, owner = _managed_lab()
    entitle_lab(lab, guild_id="g1", channel="chan")
    entitle_user(owner)
    client.force_authenticate(owner)

    assert _post(client, _item(), scope="lab", lab_slug="lab").status_code == 201


# --------------------------------------------------------------------------- #
# Delivery re-checks the plan — a lapse must stop the Discord half
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_a_lapsed_plan_stops_the_dm_without_touching_the_reminder(settings) -> None:
    """The subscription survives a billing event; only Discord delivery stops.

    Deleting reminders when a plan lapses would be unrecoverable data loss on a
    reversible event, so the row stays and the in-app bell keeps working.
    """
    settings.DISCORD_BOT_TOKEN = "test-token"
    user = entitle_user(User.objects.create_user("lapsing"))
    sub = create_subscription(
        target_user=user,
        content=_item(),
        deadline_kind=_Kind.APPLICATION,
        area=_Area.GRANT,
        title="Neural grant",
        due_date=DUE,
        offsets=[(1, "week")],
        created_by=user,
        today=date(2026, 11, 1),
    )
    assert send_personal_dm(sub, "t", "b").ok is True

    Subscription.objects.filter(scope_user=user).delete()  # the plan lapses

    outcome = send_personal_dm(sub, "t", "b", dedupe_key="after-lapse")
    assert outcome.ok is False
    assert outcome.not_entitled is True
    sub.refresh_from_db()
    assert sub.state == ReminderSubscription.State.ACTIVE


@pytest.mark.django_db
def test_a_lapsed_lab_plan_stops_the_channel_post(settings) -> None:
    settings.DISCORD_BOT_TOKEN = "test-token"
    lab, owner = _managed_lab()
    entitle_lab(lab, guild_id="g1", channel="chan")
    sub = create_subscription(
        target_lab=lab,
        content=_item(),
        deadline_kind=_Kind.APPLICATION,
        area=_Area.GRANT,
        title="Neural grant",
        due_date=DUE,
        offsets=[(1, "week")],
        today=date(2026, 11, 1),
    )
    assert send_lab_channel(sub, "t", "b").ok is True

    Subscription.objects.filter(scope_lab=lab).delete()

    outcome = send_lab_channel(sub, "t", "b", dedupe_key="after-lapse")
    assert outcome.ok is False
    assert outcome.not_entitled is True


# --------------------------------------------------------------------------- #
# The read endpoint the UI locks its button with
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_access_endpoint_reports_each_half_separately(client) -> None:
    user = User.objects.create_user("half")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    client.force_authenticate(user)

    resp = client.get("/api/reminders/access/")

    assert resp.status_code == 200
    assert resp.data == {
        "allowed": False,
        "plan_ok": True,
        "discord_ok": False,
        "reason": Reason.DISCORD,
        "detail": resp.data["detail"],
    }
    assert resp.data["detail"]  # never an empty explanation


@pytest.mark.django_db
def test_access_endpoint_agrees_with_the_create_path(client) -> None:
    """The button and the endpoint must never disagree — one computation, two reads."""
    user = entitle_user(User.objects.create_user("spore"))
    client.force_authenticate(user)

    assert client.get("/api/reminders/access/").data["allowed"] is True
    assert personal_reminder_access(user).allowed is True
    assert _post(client, _item()).status_code == 201


@pytest.mark.django_db
def test_access_endpoint_answers_for_a_lab(client) -> None:
    lab, owner = _managed_lab()
    entitle_lab(lab, guild_id="g1", channel="chan")
    entitle_user(owner)
    client.force_authenticate(owner)

    resp = client.get("/api/reminders/access/?lab=lab")

    assert resp.status_code == 200
    assert resp.data["allowed"] is True


@pytest.mark.django_db
def test_a_plain_member_is_answered_permission_not_the_labs_plan(client) -> None:
    """A non-manager gets "you can't", not a report on the lab's billing state."""
    lab, _ = _managed_lab()
    entitle_lab(lab, guild_id="g1", channel="chan")
    member = entitle_user(User.objects.create_user("member"))
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)
    client.force_authenticate(member)

    resp = client.get("/api/reminders/access/?lab=lab")

    assert resp.data["allowed"] is False
    assert resp.data["reason"] == "permission"


@pytest.mark.django_db
def test_the_service_refuses_even_if_a_view_forgot_to(client) -> None:
    """The gate is in the service, so no future endpoint can route around it."""
    user = User.objects.create_user("free")
    with pytest.raises(ReminderAccessError) as exc:
        create_subscription(
            target_user=user,
            content=_item(),
            deadline_kind=_Kind.APPLICATION,
            area=_Area.GRANT,
            title="Neural grant",
            due_date=DUE,
            offsets=[(1, "week")],
            created_by=user,
            today=date(2026, 11, 1),
        )
    assert exc.value.reason == Reason.PLAN_AND_DISCORD
