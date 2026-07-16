"""R9 — the reminder API (create / list / cancel), auth + authorization."""

from __future__ import annotations

from datetime import date

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Lab, LabMembership
from apps.content.models import (
    ContentDeadline,
    ContentItem,
    ReminderSubscription,
    SavedOpportunity,
)

_Kind = SavedOpportunity.DeadlineKind


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _grant(ext="g1", *, due=date(2026, 12, 1), confidence=None):
    confidence = confidence or ContentDeadline.Confidence.CONFIRMED
    item = ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="pivot",
        external_id=ext,
        metadata={"title": "Neural grant", "website": "https://x.test"},
    )
    ContentDeadline.objects.create(
        content=item, kind=_Kind.APPLICATION, due_date=due, confidence=confidence
    )
    return item


@pytest.mark.django_db
def test_create_personal_reminder(client) -> None:
    user = User.objects.create_user("u")
    client.force_authenticate(user)
    item = _grant()
    resp = client.post(
        "/api/reminders/",
        {
            "content_id": str(item.id),
            "deadline_kind": "application",
            "scope": "personal",
            "offsets": [{"amount": 2, "unit": "week"}],
        },
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["scope"] == "user"
    assert resp.data["offsets"] == [{"amount": 2, "unit": "week"}]
    assert ReminderSubscription.objects.filter(target_user=user).count() == 1


@pytest.mark.django_db
def test_create_uses_default_offsets_when_omitted(client) -> None:
    user = User.objects.create_user("u")
    client.force_authenticate(user)
    item = _grant()
    resp = client.post(
        "/api/reminders/",
        {"content_id": str(item.id), "deadline_kind": "application"},
        format="json",
    )
    assert resp.status_code == 201
    assert len(resp.data["offsets"]) == 3  # 1 month / 1 week / 1 day default


@pytest.mark.django_db
def test_create_rejects_rolling_deadline(client) -> None:
    user = User.objects.create_user("u")
    client.force_authenticate(user)
    item = ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP, source="illinois", external_id="f1"
    )
    ContentDeadline.objects.create(
        content=item,
        kind=_Kind.APPLICATION,
        due_date=None,
        confidence=ContentDeadline.Confidence.ROLLING,
    )
    resp = client.post(
        "/api/reminders/",
        {"content_id": str(item.id), "deadline_kind": "application"},
        format="json",
    )
    assert resp.status_code == 400
    assert "no date" in resp.data["detail"]


@pytest.mark.django_db
def test_create_requires_fields(client) -> None:
    client.force_authenticate(User.objects.create_user("u"))
    resp = client.post("/api/reminders/", {}, format="json")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_rejects_bad_offset(client) -> None:
    user = User.objects.create_user("u")
    client.force_authenticate(user)
    item = _grant()
    resp = client.post(
        "/api/reminders/",
        {
            "content_id": str(item.id),
            "deadline_kind": "application",
            "offsets": [{"amount": 0, "unit": "week"}],
        },
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_lab_reminder_requires_manager(client) -> None:
    lab = Lab.objects.create(name="Lab", slug="lab")
    member = User.objects.create_user("member")
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)
    item = _grant()
    client.force_authenticate(member)
    resp = client.post(
        "/api/reminders/",
        {
            "content_id": str(item.id),
            "deadline_kind": "application",
            "scope": "lab",
            "lab_slug": "lab",
        },
        format="json",
    )
    assert resp.status_code == 400  # only a manager can create a lab reminder


@pytest.mark.django_db
def test_lab_manager_creates_lab_reminder(client) -> None:
    lab = Lab.objects.create(name="Lab", slug="lab")
    owner = User.objects.create_user("owner")
    LabMembership.objects.create(user=owner, lab=lab, role=LabMembership.Role.OWNER)
    item = _grant()
    client.force_authenticate(owner)
    resp = client.post(
        "/api/reminders/",
        {
            "content_id": str(item.id),
            "deadline_kind": "application",
            "scope": "lab",
            "lab_slug": "lab",
            "mentions": ["owner"],
        },
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["scope"] == "lab"
    assert resp.data["lab_slug"] == "lab"
    assert resp.data["mentions"][0]["username"] == "owner"


@pytest.mark.django_db
def test_list_returns_personal_and_accessible_lab_reminders(client) -> None:
    lab = Lab.objects.create(name="Lab", slug="lab")
    owner = User.objects.create_user("owner")
    LabMembership.objects.create(user=owner, lab=lab, role=LabMembership.Role.OWNER)
    item = _grant()
    client.force_authenticate(owner)
    client.post(
        "/api/reminders/",
        {"content_id": str(item.id), "deadline_kind": "application"},
        format="json",
    )
    client.post(
        "/api/reminders/",
        {
            "content_id": str(item.id),
            "deadline_kind": "application",
            "scope": "lab",
            "lab_slug": "lab",
        },
        format="json",
    )
    resp = client.get("/api/reminders/")
    assert resp.status_code == 200
    scopes = {r["scope"] for r in resp.data["items"]}
    assert scopes == {"user", "lab"}


@pytest.mark.django_db
def test_delete_personal_reminder_owner_only(client) -> None:
    owner = User.objects.create_user("owner")
    other = User.objects.create_user("other")
    item = _grant()
    client.force_authenticate(owner)
    created = client.post(
        "/api/reminders/",
        {"content_id": str(item.id), "deadline_kind": "application"},
        format="json",
    )
    rid = created.data["id"]

    client.force_authenticate(other)
    assert client.delete(f"/api/reminders/{rid}/").status_code == 403

    client.force_authenticate(owner)
    assert client.delete(f"/api/reminders/{rid}/").status_code == 204
    assert ReminderSubscription.objects.count() == 0


@pytest.mark.django_db
def test_deadlines_array_lets_composer_pick_kind(client) -> None:
    # A conference exposes independently-remindable abstract/event deadlines.
    user = User.objects.create_user("u")
    client.force_authenticate(user)
    item = ContentItem.objects.create(
        type=ContentItem.Type.CONFERENCE, source="pivot", external_id="c1"
    )
    ContentDeadline.objects.create(
        content=item,
        kind=_Kind.ABSTRACT,
        due_date=date(2026, 11, 1),
        confidence=ContentDeadline.Confidence.CONFIRMED,
    )
    for kind in ("abstract",):
        resp = client.post(
            "/api/reminders/",
            {"content_id": str(item.id), "deadline_kind": kind},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["deadline_kind"] == kind
    assert ReminderSubscription.objects.filter(deadline_kind="abstract").count() == 1
