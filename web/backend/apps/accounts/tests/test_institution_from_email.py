"""An institution is proved by a verified email, never typed.

The rule behind ``apps.accounts.institution``: a person is at an institution
only when the address they verified belongs to it in the affiliation directory.
Typing one is refused; verifying an address sets it; a personal address sets
none; the collaboration affiliation follows the same derivation.
"""

from importlib import import_module

import pytest
from django.apps import apps as django_apps
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts import email_verification, institution
from apps.accounts.models import AuditEvent, Department, EmailVerification
from apps.collab.models import VerifiedAffiliation

FSU = "Florida State University"


@pytest.fixture(autouse=True)
def _commit_inline(monkeypatch):
    """Run ``on_commit`` hooks inline: a test never commits."""
    monkeypatch.setattr(
        "django.db.transaction.on_commit", lambda func, *args, **kwargs: func()
    )


@pytest.fixture
def known_code(monkeypatch):
    monkeypatch.setattr(email_verification, "_new_code", lambda: "123456")
    return "123456"


def _user(username, email, *, verified=False, typed=""):
    user = User.objects.create_user(username, email, "pw-Str0ng-1234")
    profile = user.profile
    profile.is_verified = verified
    profile.institution = typed
    profile.save(update_fields=["is_verified", "institution"])
    return user


def _client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


# --- deriving it ------------------------------------------------------------


@pytest.mark.django_db
def test_verifying_a_signup_code_sets_the_institution(known_code):
    user = _user("bo", "bo@fsu.edu")
    email_verification.issue(user, user.email)
    assert institution.sync(user) == ""  # not proved yet

    email_verification.verify(user, known_code)

    user.profile.refresh_from_db()
    assert user.profile.institution == FSU
    # The collaboration scope was re-derived in the same moment.
    assert VerifiedAffiliation.objects.get(user=user).domain == "fsu.edu"


@pytest.mark.django_db
def test_a_personal_address_places_nobody(known_code):
    user = _user("cy", "cy@gmail.com")
    email_verification.issue(user, user.email)
    email_verification.verify(user, known_code)

    user.profile.refresh_from_db()
    assert user.profile.is_verified is True
    assert user.profile.institution == ""


@pytest.mark.django_db
def test_changing_email_moves_the_institution_once_the_new_address_answers(
    known_code,
):
    user = _user("dee", "dee@fsu.edu", verified=True)
    institution.sync(user)
    email_verification.issue(user, "dee@umich.edu", EmailVerification.Purpose.CHANGE)
    user.profile.refresh_from_db()
    assert user.profile.institution == FSU  # still the proved one

    email_verification.verify(user, known_code, EmailVerification.Purpose.CHANGE)

    user.profile.refresh_from_db()
    assert user.email == "dee@umich.edu"
    assert user.profile.institution == "University of Michigan - Ann Arbor"


@pytest.mark.django_db
def test_an_unverified_account_holds_no_institution_but_is_told_which():
    user = _user("eve", "eve@fsu.edu", typed="Harvard University")
    assert institution.sync(user) == ""

    response = _client(user).get("/api/auth/account/")

    assert response.data["institution"] == ""
    assert response.data["institution_verified"] is False
    assert response.data["institution_from_email"] == FSU


@pytest.mark.django_db
def test_the_collaboration_refresh_keeps_the_profile_in_step():
    from apps.collab import affiliation

    user = _user("fay", "fay@fsu.edu", verified=True, typed="Harvard University")
    affiliation.refresh(user)
    user.profile.refresh_from_db()
    assert user.profile.institution == FSU


# --- refusing a typed one ----------------------------------------------------


@pytest.mark.django_db
def test_typing_a_different_institution_is_refused():
    user = _user("gus", "gus@fsu.edu", verified=True)
    institution.sync(user)

    response = _client(user).patch(
        "/api/auth/account/", {"institution": "Harvard University"}, format="json"
    )

    assert response.status_code == 400
    assert response.data["code"] == institution.REFUSAL_CODE
    assert "change your email" in response.data["institution"][0]
    user.profile.refresh_from_db()
    assert user.profile.institution == FSU


@pytest.mark.django_db
def test_resending_the_held_institution_is_a_harmless_no_op():
    user = _user("hal", "hal@fsu.edu", verified=True)
    institution.sync(user)

    response = _client(user).patch(
        "/api/auth/account/",
        {"institution": FSU.upper(), "first_name": "Hal"},
        format="json",
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.first_name == "Hal"
    assert user.profile.institution == FSU


@pytest.mark.django_db
def test_a_personal_address_cannot_type_one():
    user = _user("ida", "ida@gmail.com", verified=True)

    response = _client(user).patch(
        "/api/auth/account/", {"institution": FSU}, format="json"
    )

    assert response.status_code == 400
    assert "isn't at an institution" in response.data["institution"][0]


@pytest.mark.django_db
def test_the_profile_endpoint_cannot_type_one_either():
    user = _user("jo", "jo@gmail.com", verified=True)

    response = _client(user).patch(
        "/api/auth/profile/me/", {"institution": FSU}, format="json"
    )

    assert response.status_code == 400
    assert response.data["code"] == institution.REFUSAL_CODE
    user.profile.refresh_from_db()
    assert user.profile.institution == ""


@pytest.mark.django_db
def test_a_department_sits_at_its_creators_verified_institution():
    user = _user("kim", "kim@fsu.edu", verified=True)
    client = _client(user)

    refused = client.post(
        "/api/auth/departments/",
        {"name": "Biology", "institution": "Harvard University"},
        format="json",
    )
    created = client.post("/api/auth/departments/", {"name": "Biology"}, format="json")

    assert refused.status_code == 400
    assert created.status_code == 201
    assert Department.objects.get(owner=user).institution == FSU


# --- the migration that retired typed institutions ---------------------------


@pytest.mark.django_db
def test_rederiving_rewrites_typed_institutions_and_audits_each_change():
    kept = _user("lee", "lee@fsu.edu", verified=True, typed=FSU)
    wrong = _user("max", "max@fsu.edu", verified=True, typed="Harvard University")
    personal = _user("ned", "ned@gmail.com", verified=True, typed="MIT")
    unverified = _user("ola", "ola@fsu.edu", typed=FSU)

    migration = import_module("apps.accounts.migrations.0029_institution_from_email")
    migration.rederive(django_apps, None)

    def held(user):
        user.profile.refresh_from_db()
        return user.profile.institution

    assert held(kept) == FSU
    assert held(wrong) == FSU
    assert held(personal) == ""
    assert held(unverified) == ""
    events = AuditEvent.objects.filter(action="profile.institution_rederived")
    assert {e.target_id: e.metadata["before"] for e in events} == {
        str(wrong.pk): "Harvard University",
        str(personal.pk): "MIT",
        str(unverified.pk): FSU,
    }
