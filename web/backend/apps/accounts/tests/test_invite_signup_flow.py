"""The whole journey: invite a batch, then sign up through one of those invites.

``test_org_invites.py`` covers each half — creating invitations, and registering
through a singly-sent one. This file covers the seam between them, because that is
what a batch could plausibly break: an invitation created in bulk has to behave at
sign-up exactly like one sent on its own. Address-bound, activating, joining the
right org at the right role, and spendable once.

It runs both org kinds through the same journey, parameterised, so a lab-only or
department-only regression cannot hide.
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
)

from .conftest import verified


@pytest.fixture(autouse=True)
def _mail_sends_immediately(monkeypatch):
    """Run ``on_commit`` inline; a test never commits, so mail would never send."""
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
        User.objects.create_user(username="lena", password="p", email="lena@uni.edu")
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


# --------------------------------------------------------------------------- #
# One journey, two org kinds
# --------------------------------------------------------------------------- #


class Org:
    """The two org kinds behind one interface, so a journey runs against both."""

    def __init__(self, kind: str, lab: Lab, department: Department) -> None:
        self.kind = kind
        self.lab = lab if kind == "lab" else None
        self.department = department if kind == "department" else None

    @property
    def invites_url(self) -> str:
        if self.kind == "lab":
            return f"/api/auth/labs/{self.lab.slug}/invites/"
        return f"/api/auth/departments/{self.department.id}/invites/"

    def has_member(self, user: User) -> bool:
        if self.kind == "lab":
            return LabMembership.objects.filter(lab=self.lab, user=user).exists()
        return DeptMembership.objects.filter(
            department=self.department, user=user
        ).exists()

    def role_of(self, user: User) -> str:
        if self.kind == "lab":
            return LabMembership.objects.get(lab=self.lab, user=user).role
        return DeptMembership.objects.get(
            department=self.department, user=user
        ).role


@pytest.fixture(params=["lab", "department"])
def org(request, lab, department) -> Org:
    return Org(request.param, lab, department)


def _token(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def _send_batch(client: APIClient, org: Org, emails, **body) -> dict:
    response = client.post(
        org.invites_url, {"emails": emails, **body}, format="json"
    )
    assert response.status_code == 201, response.data
    return response.data


def _register(client: APIClient, **overrides):
    payload = {
        "username": "newcomer",
        "email": "newcomer@uni.edu",
        "password": "safe-pass-123",
        "password_confirm": "safe-pass-123",
        **overrides,
    }
    return client.post("/api/auth/register/", payload, format="json")


# --------------------------------------------------------------------------- #
# The journey
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_batched_invitation_carries_someone_all_the_way_in(
    client, org, owner
) -> None:
    """Batch of three, one of them signs up: joined, activated, no code chased.

    This is the whole feature in one test. An invitation created in a batch is the
    same object as one sent alone, so everything the single path guarantees has to
    hold here too.
    """
    client.force_authenticate(owner)
    created = _send_batch(
        client, org, ["ada@uni.edu", "ben@uni.edu", "cy@uni.edu"], role="member"
    )["created"]
    client.force_authenticate(None)
    mine = next(row for row in created if row["email"] == "ben@uni.edu")
    mail.outbox.clear()

    # The stranger reads what they were invited to before registering.
    preview = client.get(f"/api/auth/invites/{_token(mine['url'])}/")
    assert preview.status_code == 200, preview.data
    assert preview.data["org_kind"] == org.kind
    assert preview.data["email"] == "ben@uni.edu"

    response = _register(
        client, invite_token=_token(mine["url"]), email="ben@uni.edu"
    )

    assert response.status_code == 201, response.data
    joined = User.objects.get(username="newcomer")
    assert org.has_member(joined)
    assert org.role_of(joined) == "member"
    # The mailbox already answered, so no six-digit code goes after it.
    assert joined.profile.is_verified is True
    assert not EmailVerification.objects.filter(user=joined).exists()
    assert mail.outbox == []
    # Their invitation is spent; the other two are untouched.
    assert OrgInvite.objects.get(id=mine["id"]).used_count == 1
    others = OrgInvite.objects.exclude(id=mine["id"])
    assert list(others.values_list("used_count", flat=True)) == [0, 0]


@pytest.mark.django_db
def test_a_batched_invitation_is_still_bound_to_its_own_address(
    client, org, owner
) -> None:
    """Batching must not loosen the binding — that is the point of email invites."""
    client.force_authenticate(owner)
    created = _send_batch(client, org, ["ada@uni.edu", "ben@uni.edu"])["created"]
    client.force_authenticate(None)
    ada = next(row for row in created if row["email"] == "ada@uni.edu")

    # Ben cannot spend Ada's invitation, even though both came from one submission.
    refused = _register(
        client, invite_token=_token(ada["url"]), email="ben@uni.edu"
    )

    assert refused.status_code == 400
    assert refused.data["reason"] == "wrong_email"
    assert not User.objects.filter(username="newcomer").exists()
    assert OrgInvite.objects.get(id=ada["id"]).used_count == 0


@pytest.mark.django_db
def test_a_batch_can_hand_out_a_role_other_than_member(client, org, owner) -> None:
    client.force_authenticate(owner)
    created = _send_batch(client, org, ["ada@uni.edu"], role="admin")["created"]
    client.force_authenticate(None)

    response = _register(
        client, invite_token=_token(created[0]["url"]), email="ada@uni.edu"
    )

    assert response.status_code == 201, response.data
    assert org.role_of(User.objects.get(username="newcomer")) == "admin"


@pytest.mark.django_db
def test_withdrawing_a_batched_invitation_stops_the_sign_up(
    client, org, owner
) -> None:
    client.force_authenticate(owner)
    created = _send_batch(client, org, ["ada@uni.edu", "ben@uni.edu"])["created"]
    ada = next(row for row in created if row["email"] == "ada@uni.edu")
    invites.revoke_invite(OrgInvite.objects.get(id=ada["id"]), actor=owner)
    client.force_authenticate(None)

    response = _register(
        client, invite_token=_token(ada["url"]), email="ada@uni.edu"
    )

    assert response.status_code == 400
    assert response.data["reason"] == "revoked"
    assert not User.objects.filter(username="newcomer").exists()


@pytest.mark.django_db
def test_an_expired_invitation_creates_no_account(client, org, owner) -> None:
    """The clock is checked at registration, not only at preview."""
    client.force_authenticate(owner)
    created = _send_batch(client, org, ["ada@uni.edu"])["created"]
    invite = OrgInvite.objects.get(id=created[0]["id"])
    invite.expires_at = timezone.now() - timedelta(minutes=1)
    invite.save(update_fields=["expires_at"])
    client.force_authenticate(None)

    response = _register(
        client, invite_token=_token(created[0]["url"]), email="ada@uni.edu"
    )

    assert response.status_code == 400
    assert response.data["reason"] == "expired"
    assert not User.objects.filter(username="newcomer").exists()


@pytest.mark.django_db
def test_an_invitation_is_spent_once_however_many_people_present_it(
    client, org, owner
) -> None:
    """A one-use invitation admits one account and then says so.

    Concurrency is enforced by the ``select_for_update`` in ``invites.redeem``;
    this asserts the invariant that lock exists to protect — a one-use invitation
    never yields two memberships — rather than racing two threads, which under
    pytest's outer transaction would not exercise the lock honestly anyway.
    """
    client.force_authenticate(owner)
    created = _send_batch(client, org, ["ada@uni.edu"])["created"]
    client.force_authenticate(None)
    token = _token(created[0]["url"])

    first = _register(client, invite_token=token, email="ada@uni.edu")
    assert first.status_code == 201, first.data

    client.force_authenticate(None)
    second = _register(
        client, username="second", invite_token=token, email="ada@uni.edu"
    )

    assert second.status_code == 400
    assert second.data["reason"] == "exhausted"
    assert not User.objects.filter(username="second").exists()
    assert OrgInvite.objects.get(id=created[0]["id"]).used_count == 1


@pytest.mark.django_db
def test_a_whole_batch_can_sign_up_one_after_another(client, org, owner) -> None:
    """Fifteen invitations, fifteen accounts, fifteen members — no cross-talk."""
    client.force_authenticate(owner)
    addresses = [f"person{n}@uni.edu" for n in range(invites.MAX_BATCH_EMAILS)]
    created = _send_batch(client, org, addresses)["created"]
    client.force_authenticate(None)

    for index, row in enumerate(created):
        fresh = APIClient()
        response = _register(
            fresh,
            username=f"person{index}",
            invite_token=_token(row["url"]),
            email=row["email"],
        )
        assert response.status_code == 201, (row["email"], response.data)

    assert User.objects.filter(username__startswith="person").count() == len(
        addresses
    )
    for index in range(len(addresses)):
        joined = User.objects.get(username=f"person{index}")
        assert org.has_member(joined)
        assert joined.profile.is_verified is True


@pytest.mark.django_db
def test_signing_up_with_the_access_code_still_verifies_by_email(
    client, settings
) -> None:
    """A guard, not a change.

    The sign-up access code proves the caller may create an account at all. It
    says nothing about their mailbox, so the six-digit code still goes out and the
    account starts unactivated. Nothing in this feature touches that, and this test
    is here so nothing quietly starts to.
    """
    mail.outbox.clear()

    response = _register(client, access_code=settings.SIGNUP_ACCESS_CODE)

    assert response.status_code == 201, response.data
    joined = User.objects.get(username="newcomer")
    assert joined.profile.is_verified is False
    assert EmailVerification.objects.filter(
        user=joined, purpose=EmailVerification.Purpose.SIGNUP, consumed_at=None
    ).exists()
    assert len(mail.outbox) == 1
    # No invitation, so no membership anywhere.
    assert not LabMembership.objects.filter(user=joined).exists()
    assert not DeptMembership.objects.filter(user=joined).exists()


# --------------------------------------------------------------------------- #
# Signing up beside the invitation, rather than through it (plan phase 1)
# --------------------------------------------------------------------------- #
#
# The case that prompted this: two people were invited to PULSE Lab, both went to
# the sign-up page instead of their link, and both landed outside the lab with
# nothing telling anyone why. Registration only ever redeemed a posted
# ``invite_token``, so a matching address was simply never noticed.


def _invite_for(owner: User, lab: Lab, address: str) -> OrgInvite:
    return invites.create_invite(
        creator=owner, lab=lab, kind=OrgInvite.Kind.EMAIL, email=address
    )


@pytest.mark.django_db
def test_signup_reports_a_waiting_invitation_without_naming_the_org(
    client, settings, owner, lab
) -> None:
    """They are told to verify; they are not told who invited them.

    Nothing has proved this caller owns the address yet, and "who was invited
    where" is not a stranger's to read.
    """
    _invite_for(owner, lab, "newcomer@uni.edu")

    response = _register(client, access_code=settings.SIGNUP_ACCESS_CODE)

    assert response.status_code == 201, response.data
    assert response.data["pending_invite"] is True
    assert lab.name not in str(response.data)
    assert lab.slug not in str(response.data)


@pytest.mark.django_db
def test_a_waiting_invitation_is_not_spent_before_the_address_is_proved(
    client, settings, owner, lab
) -> None:
    """The claim is only a claim until a code mailed there comes back."""
    invite = _invite_for(owner, lab, "newcomer@uni.edu")

    _register(client, access_code=settings.SIGNUP_ACCESS_CODE)

    joined = User.objects.get(username="newcomer")
    assert not LabMembership.objects.filter(user=joined, lab=lab).exists()
    invite.refresh_from_db()
    assert invite.used_count == 0


@pytest.mark.django_db
def test_verifying_the_address_joins_the_lab_that_invited_them(
    client, settings, owner, lab
) -> None:
    """The whole point: nobody has to re-send anything."""
    from apps.accounts import email_verification

    invite = _invite_for(owner, lab, "newcomer@uni.edu")
    _register(client, access_code=settings.SIGNUP_ACCESS_CODE)
    joined = User.objects.get(username="newcomer")

    _verify_now(joined, email_verification)

    assert LabMembership.objects.filter(user=joined, lab=lab).exists()
    invite.refresh_from_db()
    assert invite.used_count == 1


@pytest.mark.django_db
def test_verifying_without_any_invitation_changes_nothing(
    client, settings
) -> None:
    from apps.accounts import email_verification

    _register(client, access_code=settings.SIGNUP_ACCESS_CODE)
    joined = User.objects.get(username="newcomer")

    _verify_now(joined, email_verification)

    assert joined.profile.is_verified is True
    assert not LabMembership.objects.filter(user=joined).exists()


@pytest.mark.django_db
def test_an_invitation_to_another_address_is_not_claimed(
    client, settings, owner, lab
) -> None:
    """Matching is on the proved address, never on the person."""
    from apps.accounts import email_verification

    _invite_for(owner, lab, "someone.else@uni.edu")
    _register(client, access_code=settings.SIGNUP_ACCESS_CODE)
    joined = User.objects.get(username="newcomer")

    _verify_now(joined, email_verification)

    assert not LabMembership.objects.filter(user=joined, lab=lab).exists()


@pytest.mark.django_db
def test_a_revoked_invitation_is_never_claimed(client, settings, owner, lab) -> None:
    from apps.accounts import email_verification

    invite = _invite_for(owner, lab, "newcomer@uni.edu")
    invite.revoked_at = timezone.now()
    invite.save(update_fields=["revoked_at"])

    _register(client, access_code=settings.SIGNUP_ACCESS_CODE)
    joined = User.objects.get(username="newcomer")
    _verify_now(joined, email_verification)

    assert not LabMembership.objects.filter(user=joined, lab=lab).exists()


@pytest.mark.django_db
def test_an_expired_invitation_is_never_claimed(client, settings, owner, lab) -> None:
    from apps.accounts import email_verification

    invite = _invite_for(owner, lab, "newcomer@uni.edu")
    invite.expires_at = timezone.now() - timedelta(days=1)
    invite.save(update_fields=["expires_at"])

    _register(client, access_code=settings.SIGNUP_ACCESS_CODE)
    joined = User.objects.get(username="newcomer")
    _verify_now(joined, email_verification)

    assert not LabMembership.objects.filter(user=joined, lab=lab).exists()


def _verify_now(user: User, email_verification) -> None:
    """Answer the outstanding sign-up code the way the real endpoint would."""
    row = EmailVerification.objects.filter(
        user=user, purpose=EmailVerification.Purpose.SIGNUP, consumed_at=None
    ).latest("created_at")
    code = "123456"
    row.code_hash = email_verification._hash(row.pk, code)
    row.save(update_fields=["code_hash"])
    email_verification.verify(user, code)


# --------------------------------------------------------------------------- #
# Requiring an institutional address (plan phase 2, off by default)
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_personal_address_is_accepted_while_the_rule_is_off(
    client, settings
) -> None:
    """The default. A personal address proves no institution; it is not refused."""
    settings.SIGNUP_REQUIRE_INSTITUTION_EMAIL = False

    response = _register(
        client, email="someone@gmail.com", access_code=settings.SIGNUP_ACCESS_CODE
    )

    assert response.status_code == 201, response.data


@pytest.mark.django_db
def test_a_personal_address_is_refused_while_the_rule_is_on(client, settings) -> None:
    settings.SIGNUP_REQUIRE_INSTITUTION_EMAIL = True

    response = _register(
        client, email="someone@gmail.com", access_code=settings.SIGNUP_ACCESS_CODE
    )

    assert response.status_code == 400
    assert response.data["reason"] == "institution_required"
    assert not User.objects.filter(username="newcomer").exists()


@pytest.mark.django_db
def test_an_institutional_address_passes_the_rule(client, settings) -> None:
    settings.SIGNUP_REQUIRE_INSTITUTION_EMAIL = True

    response = _register(
        client, email="someone@fsu.edu", access_code=settings.SIGNUP_ACCESS_CODE
    )

    assert response.status_code == 201, response.data


@pytest.mark.django_db
def test_an_invited_address_is_exempt_from_the_rule(client, settings, owner, lab):
    """How someone at an institute the directory has never heard of still gets in."""
    settings.SIGNUP_REQUIRE_INSTITUTION_EMAIL = True
    invite = invites.create_invite(
        creator=owner, lab=lab, kind=OrgInvite.Kind.EMAIL, email="someone@gmail.com"
    )

    response = _register(
        client, email="someone@gmail.com", invite_token=invite.token
    )

    assert response.status_code == 201, response.data
    joined = User.objects.get(username="newcomer")
    assert LabMembership.objects.filter(user=joined, lab=lab).exists()
