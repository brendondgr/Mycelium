from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client

from apps.accounts import signup_gate
from apps.accounts.models import (
    Department,
    DeptMembership,
    EmailVerification,
    Lab,
    LabMembership,
    Profile,
)
from apps.accounts.views import RegisterRateThrottle
from apps.billing.models import Seat, Subscription, Tier


@pytest.fixture
def api_client() -> Client:
    return Client(enforce_csrf_checks=True)


def _register(client: Client, payload: dict):
    """POST a registration with a fresh CSRF token, mirroring the login flow."""
    client.get("/api/auth/csrf/")
    csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
    return client.post(
        "/api/auth/register/",
        data=payload,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )


def _personal_payload(**overrides) -> dict:
    payload = {
        "username": "newuser",
        "email": "new@example.com",
        "password": "safe-pass-123",
        "password_confirm": "safe-pass-123",
        "first_name": "Jamie",
        "last_name": "Rivera",
        "account_type": "personal",
        "access_code": settings.SIGNUP_ACCESS_CODE,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def user(db: None) -> User:
    return User.objects.create_user(
        username="researcher",
        password="safe-pass-123",
        email="researcher@example.com",
    )


@pytest.mark.django_db
def test_csrf_sets_cookie(api_client: Client) -> None:
    response = api_client.get("/api/auth/csrf/")

    assert response.status_code == 200
    assert settings.CSRF_COOKIE_NAME in api_client.cookies


@pytest.mark.django_db
def test_me_anonymous_returns_401(api_client: Client) -> None:
    response = api_client.get("/api/auth/me/")

    assert response.status_code == 401


@pytest.mark.django_db
def test_login_and_me_flow(api_client: Client, user: User) -> None:
    api_client.get("/api/auth/csrf/")
    csrf = api_client.cookies[settings.CSRF_COOKIE_NAME].value

    bad = api_client.post(
        "/api/auth/login/",
        data={"username": user.username, "password": "wrong"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert bad.status_code == 401
    assert api_client.get("/api/auth/me/").status_code == 401

    good = api_client.post(
        "/api/auth/login/",
        data={"username": user.username, "password": "safe-pass-123"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert good.status_code == 200
    payload = good.json()
    assert payload["username"] == user.username
    assert payload["email"] == user.email

    me = api_client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.json()["id"] == user.pk


@pytest.mark.django_db
def test_login_missing_fields_returns_400(api_client: Client) -> None:
    api_client.get("/api/auth/csrf/")
    csrf = api_client.cookies[settings.CSRF_COOKIE_NAME].value

    response = api_client.post(
        "/api/auth/login/",
        data={"username": "only-user"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_logout_clears_session(api_client: Client, user: User) -> None:
    api_client.get("/api/auth/csrf/")
    csrf = api_client.cookies[settings.CSRF_COOKIE_NAME].value
    api_client.post(
        "/api/auth/login/",
        data={"username": user.username, "password": "safe-pass-123"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )

    api_client.get("/api/auth/csrf/")
    logout_csrf = api_client.cookies[settings.CSRF_COOKIE_NAME].value
    logout = api_client.post(
        "/api/auth/logout/",
        content_type="application/json",
        HTTP_X_CSRFTOKEN=logout_csrf,
    )
    assert logout.status_code == 204
    assert api_client.get("/api/auth/me/").status_code == 401


# -- Registration --------------------------------------------------------------


@pytest.mark.django_db
def test_register_personal_creates_user_and_seat(api_client: Client) -> None:
    response = _register(api_client, _personal_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "newuser"
    assert body["email"] == "new@example.com"

    user = User.objects.get(username="newuser")
    assert Profile.objects.filter(user=user).exists()

    sub = Subscription.objects.get(scope_user=user)
    assert sub.tier == Tier.FREE
    seat = Seat.objects.get(subscription=sub, member=user)
    assert seat.payer_user == user

    # No org rows for a personal account.
    assert Lab.objects.count() == 0
    assert Department.objects.count() == 0


@pytest.mark.django_db
def test_register_lab_makes_founder_owner_pi(api_client: Client) -> None:
    response = _register(
        api_client,
        _personal_payload(
            username="leadpi",
            email="pi@example.com",
            account_type="lab",
            org_name="Rivera Lab",
        ),
    )

    assert response.status_code == 201
    user = User.objects.get(username="leadpi")
    lab = Lab.objects.get(slug="rivera-lab")
    membership = LabMembership.objects.get(user=user, lab=lab)
    assert membership.role == LabMembership.Role.OWNER
    assert membership.is_lead is True

    sub = Subscription.objects.get(scope_lab=lab)
    assert sub.tier == Tier.LAB


@pytest.mark.django_db
def test_register_department_makes_founder_owner(api_client: Client) -> None:
    response = _register(
        api_client,
        _personal_payload(
            username="deptowner",
            email="dept@example.com",
            account_type="department",
            org_name="Molecular Systems",
            institution="Northgate University",
        ),
    )

    assert response.status_code == 201
    user = User.objects.get(username="deptowner")
    dept = Department.objects.get(owner=user)
    assert dept.name == "Molecular Systems"
    assert DeptMembership.objects.filter(
        user=user, department=dept, role=DeptMembership.Role.OWNER
    ).exists()

    sub = Subscription.objects.get(scope_department=dept)
    assert sub.tier == Tier.CANOPY


@pytest.mark.django_db
def test_register_duplicate_email_returns_400(api_client: Client) -> None:
    User.objects.create_user(
        username="existing", email="taken@example.com", password="safe-pass-123"
    )
    response = _register(api_client, _personal_payload(email="TAKEN@example.com"))

    assert response.status_code == 400
    assert "email" in response.json()


@pytest.mark.django_db
def test_register_duplicate_username_returns_400(api_client: Client) -> None:
    User.objects.create_user(username="newuser", password="safe-pass-123")
    response = _register(api_client, _personal_payload())

    assert response.status_code == 400
    assert "username" in response.json()


@pytest.mark.django_db
def test_register_password_mismatch_returns_400(api_client: Client) -> None:
    response = _register(
        api_client, _personal_payload(password_confirm="different-pass-123")
    )

    assert response.status_code == 400
    assert "password_confirm" in response.json()


@pytest.mark.django_db
def test_register_weak_password_rejected(api_client: Client) -> None:
    response = _register(
        api_client, _personal_payload(password="password", password_confirm="password")
    )

    assert response.status_code == 400
    assert "password" in response.json()


@pytest.mark.django_db
def test_register_lab_without_org_name_returns_400(api_client: Client) -> None:
    response = _register(
        api_client, _personal_payload(account_type="lab", org_name="")
    )

    assert response.status_code == 400
    assert "org_name" in response.json()


@pytest.mark.django_db
def test_register_sets_session(api_client: Client) -> None:
    response = _register(api_client, _personal_payload())
    assert response.status_code == 201

    me = api_client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.json()["username"] == "newuser"


@pytest.mark.django_db
def test_register_is_atomic() -> None:
    client = Client(enforce_csrf_checks=True, raise_request_exception=False)
    with patch(
        "apps.accounts.views.provision_workspace",
        side_effect=RuntimeError("boom"),
    ):
        response = _register(client, _personal_payload())

    assert response.status_code >= 500
    # The user (and its profile) must have rolled back — no orphan account.
    assert not User.objects.filter(username="newuser").exists()
    assert Profile.objects.count() == 0


@pytest.mark.django_db
def test_register_reserved_username_returns_400(api_client: Client) -> None:
    response = _register(api_client, _personal_payload(username="admin"))

    assert response.status_code == 400
    assert "username" in response.json()


@pytest.mark.django_db
def test_register_then_onboarding_handoff(api_client: Client) -> None:
    """The exact frontend handoff: register, then one profile PATCH."""
    assert _register(api_client, _personal_payload()).status_code == 201

    api_client.get("/api/auth/csrf/")
    csrf = api_client.cookies[settings.CSRF_COOKIE_NAME].value
    response = api_client.patch(
        "/api/auth/profile/me/",
        data={
            "academic_title": "pi",
            "institution": "Northgate University",
            "interests": {
                "version": 1,
                "areas": ["Microbial Ecology", "Genomics"],
                "statement": "We study soil microbial communities under drought.",
                "keywords": ["metagenomics", "field sampling"],
            },
        },
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )

    assert response.status_code == 200
    profile = User.objects.get(username="newuser").profile
    assert profile.academic_title == "pi"
    assert profile.institution == "Northgate University"
    assert profile.interests["areas"] == ["Microbial Ecology", "Genomics"]
    assert profile.interests["keywords"] == ["metagenomics", "field sampling"]


@pytest.mark.django_db
def test_me_reports_onboarding_completion(api_client: Client) -> None:
    """`/me` flips onboarding_completed false -> true once interests are saved."""
    assert _register(api_client, _personal_payload()).status_code == 201

    fresh = api_client.get("/api/auth/me/")
    assert fresh.status_code == 200
    assert fresh.json()["onboarding_completed"] is False

    api_client.get("/api/auth/csrf/")
    csrf = api_client.cookies[settings.CSRF_COOKIE_NAME].value
    api_client.patch(
        "/api/auth/profile/me/",
        data={"interests": {"version": 1, "areas": ["Genomics"]}},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )

    done = api_client.get("/api/auth/me/")
    assert done.json()["onboarding_completed"] is True


@pytest.mark.django_db
def test_basics_patch_does_not_clobber_concurrent_interests(
    api_client: Client,
) -> None:
    """A basics PATCH must not revert interests written by a concurrent save.

    Onboarding's ``finish`` fires the basics PATCH and the intake confirm at the
    same time. Both load a still-empty profile; if the basics write persists the
    whole row it writes back ``interests={}``, wiping the confirm — leaving
    ``onboarding_completed`` false and bouncing the user back to the start.
    Reproduced deterministically with two stale instances: confirm saves first,
    the stale basics write lands second and must leave ``interests`` intact.
    """
    from apps.accounts.serializers import ProfileSerializer

    assert _register(api_client, _personal_payload()).status_code == 201
    user = User.objects.get(username="newuser")

    # Two requests that both loaded the profile while it was still blank.
    stale_basics = Profile.objects.get(user=user)
    stale_confirm = Profile.objects.get(user=user)

    # The confirm request writes interests (scoped save).
    stale_confirm.interests = {"version": 1, "areas": ["Genomics"]}
    stale_confirm.save(
        update_fields=["interests", "embedding_text", "embedding", "updated_at"]
    )

    # The basics request lands afterwards with its stale (empty) interests.
    serializer = ProfileSerializer(
        stale_basics, data={"academic_title": "pi"}, partial=True
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()

    fresh = Profile.objects.get(user=user)
    assert fresh.academic_title == "pi"
    assert fresh.interests.get("areas") == ["Genomics"]  # not clobbered


# -- Email verification (scaffold) + throttling --------------------------------


@pytest.mark.django_db
def test_verify_email_requires_auth(api_client: Client) -> None:
    api_client.get("/api/auth/csrf/")
    csrf = api_client.cookies[settings.CSRF_COOKIE_NAME].value
    response = api_client.post(
        "/api/auth/email/verify/",
        data={"code": "123456"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )

    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_register_is_rate_limited() -> None:
    # DRF binds THROTTLE_RATES on the class at import, so patch it directly
    # rather than via override_settings (which the class never re-reads).
    # Use a fresh anonymous client per request: AnonRateThrottle only counts
    # anonymous requests (keyed by IP), and a successful register logs the
    # client in — both clients share the 127.0.0.1 bucket.
    with patch.object(RegisterRateThrottle, "THROTTLE_RATES", {"register": "1/min"}):
        first = _register(
            Client(enforce_csrf_checks=True),
            _personal_payload(username="rl1", email="rl1@example.com"),
        )
        assert first.status_code == 201
        second = _register(
            Client(enforce_csrf_checks=True),
            _personal_payload(username="rl2", email="rl2@example.com"),
        )
        assert second.status_code == 429


# --------------------------------------------------------------------------- #
# Invite-only sign-up code + shadow ban (apps.accounts.signup_gate)
# --------------------------------------------------------------------------- #
INVALID_CODE = signup_gate.INVALID_CODE_MESSAGE


@pytest.mark.django_db
def test_register_with_valid_code_leaves_account_unverified(
    api_client: Client,
) -> None:
    """Clearing the invite gate proves an invitation, not a mailbox.

    The address the person typed is what a reset link and every lab invitation
    will later depend on, so it has to answer for itself — sign-up mails a code
    and the account stays unactivated until that code comes back.
    """
    response = _register(api_client, _personal_payload())

    assert response.status_code == 201
    assert response.json()["is_verified"] is False
    assert User.objects.get(username="newuser").profile.is_verified is False
    assert EmailVerification.objects.filter(
        user__username="newuser",
        purpose=EmailVerification.Purpose.SIGNUP,
        consumed_at__isnull=True,
    ).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("code", ["", "000000", "251254", " 25125 3"])
def test_register_rejects_a_bad_code_and_creates_nothing(
    api_client: Client, code: str
) -> None:
    response = _register(api_client, _personal_payload(access_code=code))

    assert response.status_code == 400
    assert response.json()["access_code"] == [INVALID_CODE]
    assert not User.objects.filter(username="newuser").exists()


@pytest.mark.django_db
def test_register_accepts_a_padded_code(api_client: Client) -> None:
    response = _register(
        api_client, _personal_payload(access_code=f"  {settings.SIGNUP_ACCESS_CODE} ")
    )

    assert response.status_code == 201


@pytest.mark.django_db
def test_three_wrong_codes_shadow_ban_the_client_for_an_hour(
    api_client: Client,
) -> None:
    for _ in range(settings.SIGNUP_CODE_MAX_FAILURES):
        assert (
            _register(api_client, _personal_payload(access_code="000000")).status_code
            == 400
        )

    assert signup_gate.is_shadow_banned("127.0.0.1") is True

    # The right code is now refused too, with the *same* body — that is what makes
    # the ban shadow: the caller cannot tell a wrong code from a blocked client.
    blocked = _register(api_client, _personal_payload())
    assert blocked.status_code == 400
    assert blocked.json()["access_code"] == [INVALID_CODE]
    assert not User.objects.filter(username="newuser").exists()

    # The ban expires on its own after the configured hour.
    assert settings.SIGNUP_CODE_LOCKOUT_SECONDS == 3600


@pytest.mark.django_db
def test_two_wrong_codes_then_a_right_one_still_registers(api_client: Client) -> None:
    for _ in range(settings.SIGNUP_CODE_MAX_FAILURES - 1):
        assert (
            _register(api_client, _personal_payload(access_code="000000")).status_code
            == 400
        )

    assert _register(api_client, _personal_payload()).status_code == 201


@pytest.mark.django_db
def test_a_success_resets_the_failure_streak(api_client: Client) -> None:
    _register(api_client, _personal_payload(access_code="000000"))
    _register(api_client, _personal_payload(access_code="000000"))
    assert _register(api_client, _personal_payload()).status_code == 201

    # Two more misses would have tripped the ban had the streak carried over.
    for _ in range(settings.SIGNUP_CODE_MAX_FAILURES - 1):
        _register(
            Client(enforce_csrf_checks=True), _personal_payload(access_code="000000")
        )
    assert signup_gate.is_shadow_banned("127.0.0.1") is False


@pytest.mark.django_db
def test_ban_is_keyed_per_client_ip(api_client: Client) -> None:
    for _ in range(settings.SIGNUP_CODE_MAX_FAILURES):
        _register(api_client, _personal_payload(access_code="000000"))
    assert signup_gate.is_shadow_banned("127.0.0.1") is True

    other = Client(enforce_csrf_checks=True, REMOTE_ADDR="10.0.0.7")
    other.get("/api/auth/csrf/")
    csrf = other.cookies[settings.CSRF_COOKIE_NAME].value
    response = other.post(
        "/api/auth/register/",
        data=_personal_payload(),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 201


@pytest.mark.django_db
def test_a_banned_client_never_reaches_field_validation(api_client: Client) -> None:
    """A ban answers before the serializer, so it leaks no other field errors."""
    User.objects.create_user(username="taken", email="taken@example.com")
    for _ in range(settings.SIGNUP_CODE_MAX_FAILURES):
        _register(api_client, _personal_payload(access_code="000000"))

    response = _register(api_client, _personal_payload(username="taken"))
    assert response.json() == {"access_code": [INVALID_CODE]}


def test_gate_fails_closed_when_the_cache_is_down() -> None:
    """A Redis outage must not turn the gate into an unmetered guessing surface."""
    with patch.object(signup_gate, "_cache", side_effect=RuntimeError("redis down")):
        assert signup_gate.is_shadow_banned("127.0.0.1") is True
