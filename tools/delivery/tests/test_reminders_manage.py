"""The reminders management surface: re-setting, editing, snoozing, deleting.

The bug these start from: ``ReminderSubscription`` is unique per
``(target, content, deadline_kind)``, and the create path used to ``objects.create``
straight into that constraint — so setting a reminder on an item that already had one
(or re-arming one you had cancelled) raised an ``IntegrityError`` the UI reported as
"Could not create the reminder". A repeat request is now an update.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from apps.accounts.models import Lab, LabMembership
from apps.billing.testing import entitle_lab, entitle_user
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from tools.delivery.models import ReminderSubscription, SavedOpportunity
from tools.retrieval.models import ContentDeadline, ContentItem

_Kind = SavedOpportunity.DeadlineKind


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _grant(ext="g1", *, due=None):
    due = due or (timezone.localdate() + timedelta(days=90))
    item = ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="legacy",
        external_id=ext,
        metadata={"title": "Neural grant", "website": "https://x.test"},
    )
    ContentDeadline.objects.create(
        content=item,
        kind=_Kind.APPLICATION,
        due_date=due,
        confidence=ContentDeadline.Confidence.CONFIRMED,
    )
    return item


def _user(username="u"):
    return entitle_user(User.objects.create_user(username))


def _set(client, item, **extra):
    body = {
        "content_id": str(item.id),
        "deadline_kind": "application",
        "scope": "personal",
        **extra,
    }
    return client.post("/api/reminders/", body, format="json")


# --------------------------------------------------------------------------- #
# Re-setting a reminder (the reported bug)
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_second_reminder_on_same_deadline_updates_instead_of_erroring(client) -> None:
    user = _user()
    client.force_authenticate(user)
    item = _grant()

    first = _set(client, item, offsets=[{"amount": 2, "unit": "week"}])
    assert first.status_code == 201

    second = _set(
        client,
        item,
        offsets=[{"amount": 1, "unit": "month"}, {"amount": 3, "unit": "day"}],
    )
    # 200, not 201: the request succeeded but nothing new was created.
    assert second.status_code == 200
    assert second.data["id"] == first.data["id"]
    assert {(o["amount"], o["unit"]) for o in second.data["offsets"]} == {
        (1, "month"),
        (3, "day"),
    }
    assert ReminderSubscription.objects.filter(target_user=user).count() == 1


@pytest.mark.django_db
def test_setting_again_after_cancel_rearms_the_reminder(client) -> None:
    user = _user()
    client.force_authenticate(user)
    item = _grant()
    created = _set(client, item, offsets=[{"amount": 1, "unit": "week"}])
    rid = created.data["id"]

    assert client.delete(f"/api/reminders/{rid}/").status_code == 204
    sub = ReminderSubscription.objects.get(pk=rid)
    assert sub.state == ReminderSubscription.State.CANCELLED

    again = _set(client, item, offsets=[{"amount": 1, "unit": "week"}])
    assert again.status_code == 200
    sub.refresh_from_db()
    assert sub.state == ReminderSubscription.State.ACTIVE


@pytest.mark.django_db
def test_reset_clears_a_snooze(client) -> None:
    user = _user()
    client.force_authenticate(user)
    item = _grant()
    rid = _set(client, item, offsets=[{"amount": 1, "unit": "week"}]).data["id"]
    ReminderSubscription.objects.filter(pk=rid).update(
        snoozed_until=timezone.localdate() + timedelta(days=5)
    )

    _set(client, item, offsets=[{"amount": 2, "unit": "week"}])
    assert ReminderSubscription.objects.get(pk=rid).snoozed_until is None


# --------------------------------------------------------------------------- #
# PATCH: edit / snooze / reinstate
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_patch_replaces_offsets(client) -> None:
    user = _user()
    client.force_authenticate(user)
    rid = _set(
        client, _grant(), offsets=[{"amount": 1, "unit": "week"}]
    ).data["id"]

    resp = client.patch(
        f"/api/reminders/{rid}/",
        {"offsets": [{"amount": 10, "unit": "day"}]},
        format="json",
    )
    assert resp.status_code == 200
    assert [(o["amount"], o["unit"]) for o in resp.data["offsets"]] == [(10, "day")]


@pytest.mark.django_db
def test_patch_rejects_an_empty_offset_list(client) -> None:
    user = _user()
    client.force_authenticate(user)
    rid = _set(client, _grant(), offsets=[{"amount": 1, "unit": "week"}]).data["id"]

    resp = client.patch(f"/api/reminders/{rid}/", {"offsets": []}, format="json")
    assert resp.status_code == 400
    assert ReminderSubscription.objects.get(pk=rid).offsets.count() == 1


@pytest.mark.django_db
def test_patch_snoozes_and_unsnoozes(client) -> None:
    user = _user()
    client.force_authenticate(user)
    rid = _set(client, _grant(), offsets=[{"amount": 1, "unit": "week"}]).data["id"]
    until = timezone.localdate() + timedelta(days=7)

    resp = client.patch(
        f"/api/reminders/{rid}/", {"snoozed_until": until.isoformat()}, format="json"
    )
    assert resp.status_code == 200
    assert ReminderSubscription.objects.get(pk=rid).snoozed_until == until

    # An explicit null is "un-snooze", distinct from the key being absent.
    resp = client.patch(
        f"/api/reminders/{rid}/", {"snoozed_until": None}, format="json"
    )
    assert resp.status_code == 200
    assert ReminderSubscription.objects.get(pk=rid).snoozed_until is None


@pytest.mark.django_db
def test_patch_refuses_a_snooze_past_the_deadline(client) -> None:
    user = _user()
    client.force_authenticate(user)
    due = timezone.localdate() + timedelta(days=20)
    rid = _set(
        client, _grant(due=due), offsets=[{"amount": 1, "unit": "week"}]
    ).data["id"]

    resp = client.patch(
        f"/api/reminders/{rid}/",
        {"snoozed_until": (due + timedelta(days=1)).isoformat()},
        format="json",
    )
    assert resp.status_code == 400
    assert ReminderSubscription.objects.get(pk=rid).snoozed_until is None


@pytest.mark.django_db
def test_patch_reinstates_a_cancelled_reminder(client) -> None:
    user = _user()
    client.force_authenticate(user)
    rid = _set(client, _grant(), offsets=[{"amount": 1, "unit": "week"}]).data["id"]
    client.delete(f"/api/reminders/{rid}/")

    resp = client.patch(f"/api/reminders/{rid}/", {"state": "active"}, format="json")
    assert resp.status_code == 200
    assert (
        ReminderSubscription.objects.get(pk=rid).state
        == ReminderSubscription.State.ACTIVE
    )


@pytest.mark.django_db
def test_patch_refuses_to_reinstate_a_passed_deadline(client) -> None:
    user = _user()
    client.force_authenticate(user)
    rid = _set(client, _grant(), offsets=[{"amount": 1, "unit": "week"}]).data["id"]
    client.delete(f"/api/reminders/{rid}/")
    ReminderSubscription.objects.filter(pk=rid).update(
        due_date=timezone.localdate() - timedelta(days=1)
    )

    resp = client.patch(f"/api/reminders/{rid}/", {"state": "active"}, format="json")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_patch_rejects_someone_elses_reminder(client) -> None:
    owner = _user("owner")
    other = _user("other")
    api = APIClient()
    api.force_authenticate(owner)
    rid = _set(api, _grant(), offsets=[{"amount": 1, "unit": "week"}]).data["id"]

    client.force_authenticate(other)
    resp = client.patch(
        f"/api/reminders/{rid}/",
        {"offsets": [{"amount": 3, "unit": "day"}]},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_personal_reminder_cannot_take_mentions_or_a_channel(client) -> None:
    user = _user()
    client.force_authenticate(user)
    rid = _set(client, _grant(), offsets=[{"amount": 1, "unit": "week"}]).data["id"]

    assert (
        client.patch(
            f"/api/reminders/{rid}/", {"channel_id_override": "42"}, format="json"
        ).status_code
        == 400
    )
    assert (
        client.patch(
            f"/api/reminders/{rid}/", {"mentions": ["u"]}, format="json"
        ).status_code
        == 400
    )


# --------------------------------------------------------------------------- #
# DELETE: soft cancel vs purge
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_purge_destroys_the_row(client) -> None:
    user = _user()
    client.force_authenticate(user)
    rid = _set(client, _grant(), offsets=[{"amount": 1, "unit": "week"}]).data["id"]

    assert client.delete(f"/api/reminders/{rid}/?purge=1").status_code == 204
    assert not ReminderSubscription.objects.filter(pk=rid).exists()


# --------------------------------------------------------------------------- #
# The list the page reads
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_list_reports_fire_dates_and_manage_rights(client) -> None:
    user = _user()
    client.force_authenticate(user)
    due = timezone.localdate() + timedelta(days=30)
    _set(client, _grant(due=due), offsets=[{"amount": 1, "unit": "week"}])

    resp = client.get("/api/reminders/")
    assert resp.status_code == 200
    row = resp.data["items"][0]
    assert row["can_manage"] is True
    assert row["offsets"][0]["fire_date"] == (due - timedelta(days=7)).isoformat()
    assert row["next_fire_date"] == (due - timedelta(days=7)).isoformat()
    # Personal reminders ride the daily run rather than a configured hour.
    assert row["send_hour_local"] is None
    assert row["timezone"]


@pytest.mark.django_db
def test_list_filters_by_state(client) -> None:
    user = _user()
    client.force_authenticate(user)
    keep = _set(client, _grant("g1"), offsets=[{"amount": 1, "unit": "week"}])
    drop = _set(client, _grant("g2"), offsets=[{"amount": 1, "unit": "week"}])
    client.delete(f"/api/reminders/{drop.data['id']}/")

    resp = client.get("/api/reminders/?state=active")
    assert [r["id"] for r in resp.data["items"]] == [keep.data["id"]]


@pytest.mark.django_db
def test_lab_member_sees_the_reminder_but_cannot_manage_it(client) -> None:
    lead = _user("lead")
    member = _user("member")
    lab = entitle_lab(Lab.objects.create(name="Lab", slug="lab"))
    LabMembership.objects.create(lab=lab, user=lead, role="owner")
    LabMembership.objects.create(lab=lab, user=member, role="member")

    api = APIClient()
    api.force_authenticate(lead)
    created = _set(api, _grant(), scope="lab", lab_slug="lab",
                   offsets=[{"amount": 1, "unit": "week"}])
    assert created.status_code == 201

    client.force_authenticate(member)
    row = client.get("/api/reminders/").data["items"][0]
    assert row["can_manage"] is False
    assert row["lab_name"] == "Lab"
    assert (
        client.delete(f"/api/reminders/{row['id']}/").status_code == 403
    )


@pytest.mark.django_db
def test_snoozed_reminder_reports_its_next_fire_after_the_snooze(client) -> None:
    user = _user()
    client.force_authenticate(user)
    due = timezone.localdate() + timedelta(days=40)
    rid = _set(
        client,
        _grant(due=due),
        offsets=[{"amount": 1, "unit": "month"}, {"amount": 1, "unit": "week"}],
    ).data["id"]
    # Snooze past the one-month lead time; the weekly one is what's left.
    client.patch(
        f"/api/reminders/{rid}/",
        {"snoozed_until": (due - timedelta(days=20)).isoformat()},
        format="json",
    )

    row = client.get("/api/reminders/").data["items"][0]
    assert row["next_fire_date"] == (due - timedelta(days=7)).isoformat()
