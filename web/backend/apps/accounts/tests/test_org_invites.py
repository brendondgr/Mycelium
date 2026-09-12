"""Join invitations for labs and departments — email invites and share links.

Two shapes of the same object, and the tests are organised around what makes each
one safe: an email invite is bound to one address and must refuse every other; a
share link is bound to nothing, so its budget and its clock have to hold.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import invites
from apps.accounts.models import (
    Department,
    DeptMembership,
    EmailVerification,
    Lab,
    LabMembership,
    OrgInvite,
    OrgInviteRedemption,
)

from .conftest import verified


@pytest.fixture(autouse=True)
def _mail_sends_immediately(monkeypatch):
    """Run ``on_commit`` hooks inline, so the sign-up code lands in the outbox.

    ``email_verification`` mails on commit and a test never commits, so without
    this every assertion about that mail would pass vacuously.
    """
    monkeypatch.setattr(
        "django.db.transaction.on_commit", lambda func, *args, **kwargs: func()
    )


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def lab(db) -> Lab:
    return Lab.objects.create(name="Reyes Lab", slug="reyes-lab")


@pytest.fixture
def owner(db, lab) -> User:
    user = verified(
        User.objects.create_user(
            username="lena", password="p", email="lena@uni.edu"
        )
    )
    LabMembership.objects.create(
        user=user, lab=lab, role=LabMembership.Role.OWNER, is_lead=True
    )
    return user


@pytest.fixture
def department(db, owner) -> Department:
    dept = Department.objects.create(owner=owner, name="Biology")
    DeptMembership.objects.create(
        department=dept, user=owner, role=DeptMembership.Role.OWNER
    )
    return dept


def _link(client: APIClient, lab: Lab, **body) -> dict:
    payload = {"kind": "link", **body}
    response = client.post(
        f"/api/auth/labs/{lab.slug}/invites/", payload, format="json"
    )
    assert response.status_code == 201, response.data
    return response.data


def _token(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


# -- Creating ------------------------------------------------------------------


@pytest.mark.django_db
def test_creating_an_invite_needs_a_verified_account(client, lab) -> None:
    unverified = User.objects.create_user(
        username="new", password="p", email="new@uni.edu"
    )
    LabMembership.objects.create(
        user=unverified, lab=lab, role=LabMembership.Role.OWNER, is_lead=True
    )
    client.force_authenticate(unverified)

    response = client.post(
        f"/api/auth/labs/{lab.slug}/invites/", {"kind": "link"}, format="json"
    )

    assert response.status_code == 403
    assert OrgInvite.objects.count() == 0


@pytest.mark.django_db
def test_a_plain_member_cannot_invite(client, lab, owner) -> None:
    member = verified(
        User.objects.create_user(username="pat", password="p", email="pat@uni.edu")
    )
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)
    client.force_authenticate(member)

    response = client.post(
        f"/api/auth/labs/{lab.slug}/invites/", {"kind": "link"}, format="json"
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_a_share_link_defaults_to_a_week_and_a_usage_budget(
    client, lab, owner
) -> None:
    client.force_authenticate(owner)

    row = _link(client, lab)

    assert row["kind"] == "link"
    assert row["max_uses"] == invites.DEFAULT_MAX_USES
    assert row["used_count"] == 0
    assert row["is_live"] is True
    invite = OrgInvite.objects.get(id=row["id"])
    days = (invite.expires_at - timezone.now()).days
    assert days == invites.DEFAULT_EXPIRY_DAYS - 1  # a whisker under seven


@pytest.mark.django_db
def test_a_creator_can_set_the_budget_and_the_clock(client, lab, owner) -> None:
    client.force_authenticate(owner)

    row = _link(client, lab, max_uses=3, expires_in_days=30)

    assert row["max_uses"] == 3
    invite = OrgInvite.objects.get(id=row["id"])
    assert 29 <= (invite.expires_at - timezone.now()).days <= 30


@pytest.mark.django_db
@pytest.mark.parametrize(
    "body",
    [
        {"kind": "link", "max_uses": 0},
        {"kind": "link", "max_uses": invites.MAX_MAX_USES + 1},
        {"kind": "link", "expires_in_days": 0},
        {"kind": "link", "expires_in_days": invites.MAX_EXPIRY_DAYS + 1},
        {"kind": "email"},  # no address
        {"kind": "carrier-pigeon"},
    ],
)
def test_bad_invite_settings_are_refused(client, lab, owner, body) -> None:
    client.force_authenticate(owner)

    response = client.post(
        f"/api/auth/labs/{lab.slug}/invites/", body, format="json"
    )

    assert response.status_code == 400
    assert OrgInvite.objects.count() == 0


@pytest.mark.django_db
def test_an_email_invite_is_mailed_and_capped_at_one_use(client, lab, owner) -> None:
    client.force_authenticate(owner)

    response = client.post(
        f"/api/auth/labs/{lab.slug}/invites/",
        {"kind": "email", "email": "Sam@Uni.edu", "message": "Come join us"},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["email"] == "sam@uni.edu"  # normalized
    assert response.data["max_uses"] == 1
    assert len(mail.outbox) == 1
    sent = mail.outbox[0]
    assert sent.to == ["sam@uni.edu"]
    assert response.data["url"] in sent.body
    assert "Come join us" in sent.body


@pytest.mark.django_db
def test_an_email_invite_wont_be_sent_to_an_existing_member(
    client, lab, owner
) -> None:
    member = User.objects.create_user(
        username="pat", password="p", email="pat@uni.edu"
    )
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)
    client.force_authenticate(owner)

    response = client.post(
        f"/api/auth/labs/{lab.slug}/invites/",
        {"kind": "email", "email": "pat@uni.edu"},
        format="json",
    )

    assert response.status_code == 400
    assert mail.outbox == []


@pytest.mark.django_db
def test_an_invite_never_hands_out_ownership(client, lab, owner) -> None:
    """`owner` is a transfer, not something a link can confer — it lands as admin."""
    client.force_authenticate(owner)

    row = _link(client, lab, role="owner")

    assert row["role"] == OrgInvite.Role.ADMIN


# -- Previewing ----------------------------------------------------------------


@pytest.mark.django_db
def test_a_stranger_can_read_what_the_link_invites_them_to(
    client, lab, owner
) -> None:
    client.force_authenticate(owner)
    url = _link(client, lab)["url"]
    client.force_authenticate(None)

    response = client.get(f"/api/auth/invites/{_token(url)}/")

    assert response.status_code == 200
    assert response.data["org_kind"] == "lab"
    assert response.data["org_name"] == "Reyes Lab"
    assert response.data["invited_by"] == "lena"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda i: i.__setattr__("revoked_at", timezone.now()), "revoked"),
        (
            lambda i: i.__setattr__(
                "expires_at", timezone.now() - timedelta(minutes=1)
            ),
            "expired",
        ),
        (lambda i: i.__setattr__("used_count", i.max_uses), "exhausted"),
    ],
)
def test_a_dead_link_says_why(client, lab, owner, mutate, reason) -> None:
    client.force_authenticate(owner)
    url = _link(client, lab, max_uses=1)["url"]
    invite = OrgInvite.objects.get()
    mutate(invite)
    invite.save()
    client.force_authenticate(None)

    response = client.get(f"/api/auth/invites/{_token(url)}/")

    assert response.status_code == 410
    assert response.data["reason"] == reason


@pytest.mark.django_db
def test_an_unknown_token_is_gone_not_found(client) -> None:
    response = client.get("/api/auth/invites/not-a-real-token/")

    assert response.status_code == 410
    assert response.data["reason"] == "invalid"


# -- Accepting while signed in --------------------------------------------------


@pytest.mark.django_db
def test_accepting_a_link_joins_the_lab(client, lab, owner) -> None:
    client.force_authenticate(owner)
    url = _link(client, lab)["url"]
    joiner = User.objects.create_user(
        username="pat", password="p", email="pat@uni.edu"
    )
    client.force_authenticate(joiner)

    response = client.post(f"/api/auth/invites/{_token(url)}/accept/")

    assert response.status_code == 200
    assert response.data["slug"] == lab.slug
    assert LabMembership.objects.filter(lab=lab, user=joiner).exists()
    assert OrgInvite.objects.get().used_count == 1


@pytest.mark.django_db
def test_joining_does_not_require_the_joiner_to_be_verified(
    client, lab, owner
) -> None:
    """Verification gates *creating* an org, not being brought into one."""
    client.force_authenticate(owner)
    url = _link(client, lab)["url"]
    joiner = User.objects.create_user(
        username="pat", password="p", email="pat@uni.edu"
    )
    assert joiner.profile.is_verified is False
    client.force_authenticate(joiner)

    assert client.post(f"/api/auth/invites/{_token(url)}/accept/").status_code == 200


@pytest.mark.django_db
def test_following_your_own_link_twice_spends_one_use(client, lab, owner) -> None:
    client.force_authenticate(owner)
    url = _link(client, lab)["url"]
    joiner = User.objects.create_user(
        username="pat", password="p", email="pat@uni.edu"
    )
    client.force_authenticate(joiner)

    client.post(f"/api/auth/invites/{_token(url)}/accept/")
    client.post(f"/api/auth/invites/{_token(url)}/accept/")

    assert OrgInvite.objects.get().used_count == 1
    assert OrgInviteRedemption.objects.count() == 1
    assert LabMembership.objects.filter(lab=lab, user=joiner).count() == 1


@pytest.mark.django_db
def test_a_link_stops_admitting_people_at_its_budget(client, lab, owner) -> None:
    client.force_authenticate(owner)
    url = _link(client, lab, max_uses=1)["url"]

    first = User.objects.create_user(username="a", password="p", email="a@uni.edu")
    second = User.objects.create_user(username="b", password="p", email="b@uni.edu")

    client.force_authenticate(first)
    assert client.post(f"/api/auth/invites/{_token(url)}/accept/").status_code == 200
    client.force_authenticate(second)
    response = client.post(f"/api/auth/invites/{_token(url)}/accept/")

    assert response.status_code == 400
    assert response.data["reason"] == "exhausted"
    assert not LabMembership.objects.filter(lab=lab, user=second).exists()


@pytest.mark.django_db
def test_an_email_invite_refuses_every_address_but_its_own(
    client, lab, owner
) -> None:
    client.force_authenticate(owner)
    url = client.post(
        f"/api/auth/labs/{lab.slug}/invites/",
        {"kind": "email", "email": "sam@uni.edu"},
        format="json",
    ).data["url"]

    wrong = User.objects.create_user(
        username="pat", password="p", email="pat@uni.edu"
    )
    client.force_authenticate(wrong)
    response = client.post(f"/api/auth/invites/{_token(url)}/accept/")

    assert response.status_code == 400
    assert response.data["reason"] == "wrong_email"
    assert not LabMembership.objects.filter(lab=lab, user=wrong).exists()

    right = User.objects.create_user(
        username="sam", password="p", email="SAM@uni.edu"
    )
    client.force_authenticate(right)
    assert client.post(f"/api/auth/invites/{_token(url)}/accept/").status_code == 200


@pytest.mark.django_db
def test_a_revoked_invite_cannot_be_spent(client, lab, owner) -> None:
    client.force_authenticate(owner)
    row = _link(client, lab)
    revoke = client.post(
        f"/api/auth/labs/{lab.slug}/invites/{row['id']}/revoke/", format="json"
    )
    assert revoke.status_code == 200
    assert revoke.data["is_live"] is False

    joiner = User.objects.create_user(
        username="pat", password="p", email="pat@uni.edu"
    )
    client.force_authenticate(joiner)
    response = client.post(f"/api/auth/invites/{_token(row['url'])}/accept/")

    assert response.status_code == 400
    assert response.data["reason"] == "revoked"


# -- Departments ----------------------------------------------------------------


@pytest.mark.django_db
def test_a_department_link_joins_the_department(client, department, owner) -> None:
    client.force_authenticate(owner)
    created = client.post(
        f"/api/auth/departments/{department.id}/invites/",
        {"kind": "link"},
        format="json",
    )
    assert created.status_code == 201

    joiner = User.objects.create_user(
        username="pat", password="p", email="pat@uni.edu"
    )
    client.force_authenticate(joiner)
    response = client.post(
        f"/api/auth/invites/{_token(created.data['url'])}/accept/"
    )

    assert response.status_code == 200
    assert response.data["org_kind"] == "department"
    assert DeptMembership.objects.filter(department=department, user=joiner).exists()


@pytest.mark.django_db
def test_a_department_invite_can_be_revoked(client, department, owner) -> None:
    client.force_authenticate(owner)
    row = client.post(
        f"/api/auth/departments/{department.id}/invites/",
        {"kind": "link"},
        format="json",
    ).data

    response = client.post(
        f"/api/auth/departments/{department.id}/invites/{row['id']}/revoke/",
        format="json",
    )

    assert response.status_code == 200
    assert response.data["is_live"] is False


@pytest.mark.django_db
def test_an_outsider_cannot_read_a_departments_invitations(
    client, department, owner
) -> None:
    stranger = verified(User.objects.create_user(username="nope", password="p"))
    client.force_authenticate(stranger)

    response = client.get(f"/api/auth/departments/{department.id}/invites/")

    assert response.status_code == 403


# -- Signing up through an invitation --------------------------------------------


def _register(client: APIClient, **overrides) -> object:
    payload = {
        "username": "newcomer",
        "email": "newcomer@uni.edu",
        "password": "safe-pass-123",
        "password_confirm": "safe-pass-123",
        **overrides,
    }
    return client.post("/api/auth/register/", payload, format="json")


@pytest.mark.django_db
def test_a_link_gets_someone_past_the_beta_gate_and_into_the_lab(
    client, lab, owner
) -> None:
    """No access code: the invitation *is* the invitation."""
    client.force_authenticate(owner)
    url = _link(client, lab)["url"]
    client.force_authenticate(None)

    response = _register(client, invite_token=_token(url))

    assert response.status_code == 201, response.data
    joined = User.objects.get(username="newcomer")
    assert LabMembership.objects.filter(lab=lab, user=joined).exists()


@pytest.mark.django_db
def test_signing_up_without_a_code_or_an_invite_is_still_refused(client) -> None:
    response = _register(client)

    assert response.status_code == 400
    assert "access_code" in response.data
    assert not User.objects.filter(username="newcomer").exists()


@pytest.mark.django_db
def test_an_email_invite_only_admits_the_address_it_was_sent_to(
    client, lab, owner
) -> None:
    client.force_authenticate(owner)
    url = client.post(
        f"/api/auth/labs/{lab.slug}/invites/",
        {"kind": "email", "email": "sam@uni.edu"},
        format="json",
    ).data["url"]
    client.force_authenticate(None)

    refused = _register(client, invite_token=_token(url), email="someone@else.edu")

    assert refused.status_code == 400
    assert refused.data["reason"] == "wrong_email"
    assert not User.objects.filter(username="newcomer").exists()


@pytest.mark.django_db
def test_registering_through_an_email_invite_activates_the_account(
    client, lab, owner
) -> None:
    """The link went to that mailbox and came back — the same proof a code asks for."""
    client.force_authenticate(owner)
    url = client.post(
        f"/api/auth/labs/{lab.slug}/invites/",
        {"kind": "email", "email": "sam@uni.edu"},
        format="json",
    ).data["url"]
    client.force_authenticate(None)
    mail.outbox.clear()

    response = _register(client, invite_token=_token(url), email="sam@uni.edu")

    assert response.status_code == 201
    joined = User.objects.get(username="newcomer")
    assert joined.profile.is_verified is True
    # No six-digit code chasing a mailbox that has already answered.
    assert mail.outbox == []
    assert not EmailVerification.objects.filter(user=joined).exists()


@pytest.mark.django_db
def test_registering_through_a_share_link_still_has_to_verify(
    client, lab, owner
) -> None:
    """A link proves nothing about the mailbox typed into the form."""
    client.force_authenticate(owner)
    url = _link(client, lab)["url"]
    client.force_authenticate(None)
    mail.outbox.clear()

    response = _register(client, invite_token=_token(url))

    assert response.status_code == 201
    joined = User.objects.get(username="newcomer")
    assert joined.profile.is_verified is False
    assert len(mail.outbox) == 1
    assert EmailVerification.objects.filter(
        user=joined, purpose=EmailVerification.Purpose.SIGNUP, consumed_at=None
    ).exists()


@pytest.mark.django_db
def test_a_dead_invite_creates_no_account(client, lab, owner) -> None:
    client.force_authenticate(owner)
    row = _link(client, lab)
    client.post(f"/api/auth/labs/{lab.slug}/invites/{row['id']}/revoke/")
    client.force_authenticate(None)

    response = _register(client, invite_token=_token(row["url"]))

    assert response.status_code == 400
    assert response.data["reason"] == "revoked"
    assert not User.objects.filter(username="newcomer").exists()


# -- Inviting a batch ----------------------------------------------------------
#
# The batch path exists so a manager can stand a lab up in one submission instead
# of fifteen. What has to hold is that the cap is real, that one bad address does
# not cost the good ones, and that every refusal says which address and why.


def _batch(client: APIClient, lab: Lab, emails, **body) -> dict:
    response = client.post(
        f"/api/auth/labs/{lab.slug}/invites/",
        {"emails": emails, **body},
        format="json",
    )
    assert response.status_code == 201, response.data
    return response.data


@pytest.mark.django_db
def test_a_batch_invites_everyone_it_was_given(client, lab, owner) -> None:
    client.force_authenticate(owner)
    addresses = [f"person{n}@uni.edu" for n in range(invites.MAX_BATCH_EMAILS)]

    data = _batch(client, lab, addresses, role="member")

    assert data["requested"] == invites.MAX_BATCH_EMAILS
    assert data["failed"] == []
    assert len(data["created"]) == invites.MAX_BATCH_EMAILS
    assert [row["email"] for row in data["created"]] == addresses
    # Every one is an email invite worth exactly one use, as if sent singly.
    assert {row["kind"] for row in data["created"]} == {"email"}
    assert {row["max_uses"] for row in data["created"]} == {1}
    assert len(mail.outbox) == invites.MAX_BATCH_EMAILS
    assert sorted(m.to[0] for m in mail.outbox) == sorted(addresses)


@pytest.mark.django_db
def test_a_batch_over_the_cap_creates_nothing(client, lab, owner) -> None:
    client.force_authenticate(owner)
    addresses = [f"person{n}@uni.edu" for n in range(invites.MAX_BATCH_EMAILS + 1)]

    response = client.post(
        f"/api/auth/labs/{lab.slug}/invites/",
        {"emails": addresses},
        format="json",
    )

    assert response.status_code == 400
    assert "15" in str(response.data["emails"][0])
    assert OrgInvite.objects.count() == 0
    assert mail.outbox == []


@pytest.mark.django_db
def test_an_empty_batch_is_refused(client, lab, owner) -> None:
    client.force_authenticate(owner)

    response = client.post(
        f"/api/auth/labs/{lab.slug}/invites/", {"emails": []}, format="json"
    )

    assert response.status_code == 400
    assert OrgInvite.objects.count() == 0


@pytest.mark.django_db
def test_one_bad_address_does_not_cost_the_good_ones(client, lab, owner) -> None:
    """The point of the batch: eleven good addresses survive a twelfth typo."""
    client.force_authenticate(owner)
    member = User.objects.create_user(
        username="sam", password="p", email="sam@uni.edu"
    )
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)

    data = _batch(
        client,
        lab,
        [
            "fresh@uni.edu",
            "sam@uni.edu",  # already in the lab
            "not-an-address",  # malformed
            "fresh@uni.edu",  # repeated in this very list
        ],
    )

    assert data["requested"] == 4
    assert [row["email"] for row in data["created"]] == ["fresh@uni.edu"]
    assert {row["reason"] for row in data["failed"]} == {
        "already_member",
        "invalid_email",
        "duplicate",
    }
    # Each refusal names the address it is about, so the UI can mark that chip.
    assert {row["email"] for row in data["failed"]} == {
        "sam@uni.edu",
        "not-an-address",
        "fresh@uni.edu",
    }
    assert [m.to[0] for m in mail.outbox] == ["fresh@uni.edu"]


@pytest.mark.django_db
def test_a_second_batch_will_not_mail_the_same_person_twice(
    client, lab, owner
) -> None:
    client.force_authenticate(owner)
    _batch(client, lab, ["kim@uni.edu"])
    mail.outbox.clear()

    data = _batch(client, lab, ["kim@uni.edu", "jo@uni.edu"])

    assert [row["email"] for row in data["created"]] == ["jo@uni.edu"]
    assert data["failed"][0]["reason"] == "already_invited"
    assert [m.to[0] for m in mail.outbox] == ["jo@uni.edu"]


@pytest.mark.django_db
def test_withdrawing_an_invitation_frees_the_address_again(
    client, lab, owner
) -> None:
    """``already_invited`` is about a *live* invitation, not a permanent block."""
    client.force_authenticate(owner)
    first = _batch(client, lab, ["kim@uni.edu"])["created"][0]
    client.post(
        f"/api/auth/labs/{lab.slug}/invites/{first['id']}/revoke/", format="json"
    )

    data = _batch(client, lab, ["kim@uni.edu"])

    assert len(data["created"]) == 1
    assert data["failed"] == []


@pytest.mark.django_db
def test_a_pasted_list_is_split_the_way_people_paste_it(client, lab, owner) -> None:
    client.force_authenticate(owner)

    data = _batch(client, lab, ["a@uni.edu, b@uni.edu; c@uni.edu\nd@uni.edu"])

    assert [row["email"] for row in data["created"]] == [
        "a@uni.edu",
        "b@uni.edu",
        "c@uni.edu",
        "d@uni.edu",
    ]


@pytest.mark.django_db
def test_a_batch_carries_the_role_and_the_note(client, lab, owner) -> None:
    client.force_authenticate(owner)

    data = _batch(
        client, lab, ["a@uni.edu", "b@uni.edu"], role="admin", message="Join us"
    )

    assert {row["role"] for row in data["created"]} == {"admin"}
    assert {row["message"] for row in data["created"]} == {"Join us"}


@pytest.mark.django_db
def test_a_batch_never_hands_out_ownership(client, lab, owner) -> None:
    client.force_authenticate(owner)

    data = _batch(client, lab, ["a@uni.edu"], role="owner")

    assert data["created"][0]["role"] == "admin"


@pytest.mark.django_db
def test_a_department_takes_a_batch_the_same_way(client, department, owner) -> None:
    client.force_authenticate(owner)

    response = client.post(
        f"/api/auth/departments/{department.id}/invites/",
        {"emails": ["a@uni.edu", "b@uni.edu"]},
        format="json",
    )

    assert response.status_code == 201, response.data
    assert len(response.data["created"]) == 2
    assert (
        OrgInvite.objects.filter(department=department, kind="email").count() == 2
    )


@pytest.mark.django_db
def test_a_batch_needs_a_verified_account(client, lab) -> None:
    """The gate runs before the payload, so nothing leaks about the addresses."""
    unverified = User.objects.create_user(
        username="new", password="p", email="new@uni.edu"
    )
    LabMembership.objects.create(
        user=unverified, lab=lab, role=LabMembership.Role.OWNER, is_lead=True
    )
    client.force_authenticate(unverified)

    response = client.post(
        f"/api/auth/labs/{lab.slug}/invites/",
        {"emails": ["a@uni.edu"]},
        format="json",
    )

    assert response.status_code == 403
    assert OrgInvite.objects.count() == 0
    assert mail.outbox == []


@pytest.mark.django_db
def test_a_plain_member_cannot_send_a_batch(client, lab, owner) -> None:
    member = verified(
        User.objects.create_user(username="pat", password="p", email="pat@uni.edu")
    )
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)
    client.force_authenticate(member)

    response = client.post(
        f"/api/auth/labs/{lab.slug}/invites/",
        {"emails": ["a@uni.edu"]},
        format="json",
    )

    assert response.status_code == 403
    assert OrgInvite.objects.count() == 0


@pytest.mark.django_db
def test_a_single_address_still_works_exactly_as_before(client, lab, owner) -> None:
    """The batch branch must not have moved the original payload shape."""
    client.force_authenticate(owner)

    response = client.post(
        f"/api/auth/labs/{lab.slug}/invites/",
        {"kind": "email", "email": "solo@uni.edu"},
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["email"] == "solo@uni.edu"
    assert "created" not in response.data
