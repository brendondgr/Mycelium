"""An institution may be *granted*, never typed by its subject (plan phase 2).

``test_institution_from_email.py`` pins the derivation: an address proves an
institution or it proves none. This file pins the one exception — an operator
placing an account the directory cannot place — and, crucially, that the
exception keeps the invariant it looks like it breaks. The subject still cannot
set their own; someone accountable does, and it is recorded.
"""

import pytest
from django.contrib.auth.models import User

from apps.accounts import institution
from apps.accounts.models import AuditEvent

from .conftest import verified

FSU = "Florida State University"


def _user(name: str, email: str) -> User:
    return User.objects.create_user(username=name, password="p", email=email)


@pytest.mark.django_db
def test_a_personal_address_proves_nothing_on_its_own() -> None:
    """The behaviour that made the exception necessary."""
    user = verified(_user("olmo", "olmo@gmail.com"))

    assert institution.sync(user) == ""


@pytest.mark.django_db
def test_a_grant_places_an_account_its_address_cannot() -> None:
    user = verified(_user("olmo", "olmo@gmail.com"))
    actor = _user("admin", "admin@fsu.edu")

    assert institution.grant(user, FSU, actor=actor) == FSU

    user.profile.refresh_from_db()
    assert user.profile.institution == FSU
    assert user.profile.institution_granted == FSU
    assert user.profile.institution_granted_by == actor
    assert user.profile.institution_granted_at is not None


@pytest.mark.django_db
def test_a_grant_survives_a_later_re_sync() -> None:
    """The bug this would otherwise have: verification quietly erasing the grant."""
    user = verified(_user("olmo", "olmo@gmail.com"))
    institution.grant(user, FSU)

    assert institution.sync(user) == FSU


@pytest.mark.django_db
def test_a_grant_outranks_what_the_address_would_prove() -> None:
    user = verified(_user("someone", "someone@ufl.edu"))
    derived = institution.sync(user)
    assert derived and derived != FSU

    assert institution.grant(user, FSU) == FSU


@pytest.mark.django_db
def test_revoking_falls_back_to_the_address() -> None:
    user = verified(_user("olmo", "olmo@fsu.edu"))
    institution.grant(user, "University of Florida")

    assert institution.revoke_grant(user) == FSU
    user.profile.refresh_from_db()
    assert user.profile.institution_granted == ""
    assert user.profile.institution_granted_by is None


@pytest.mark.django_db
def test_revoking_a_personal_address_leaves_no_institution() -> None:
    user = verified(_user("olmo", "olmo@gmail.com"))
    institution.grant(user, FSU)

    assert institution.revoke_grant(user) == ""


@pytest.mark.django_db
def test_a_grant_cannot_invent_an_institution() -> None:
    """An operator may place someone, not make somewhere up."""
    user = verified(_user("olmo", "olmo@gmail.com"))

    with pytest.raises(ValueError, match="affiliation directory"):
        institution.grant(user, "Hogwarts School of Witchcraft")

    user.profile.refresh_from_db()
    assert user.profile.institution_granted == ""


@pytest.mark.django_db
def test_a_grant_is_case_insensitive_and_stores_the_canonical_name() -> None:
    user = verified(_user("olmo", "olmo@gmail.com"))

    assert institution.grant(user, "florida STATE university") == FSU


@pytest.mark.django_db
def test_both_grant_and_revoke_are_audited() -> None:
    user = verified(_user("olmo", "olmo@gmail.com"))
    actor = _user("admin", "admin@fsu.edu")

    institution.grant(user, FSU, actor=actor)
    institution.revoke_grant(user, actor=actor)

    assert AuditEvent.objects.filter(action="account.institution.grant").exists()
    assert AuditEvent.objects.filter(
        action="account.institution.grant.revoked"
    ).exists()


@pytest.mark.django_db
def test_the_subject_still_cannot_type_their_own() -> None:
    """The invariant the grant must not loosen."""
    user = verified(_user("olmo", "olmo@gmail.com"))
    institution.grant(user, FSU)

    # Resending what they were shown is the usual no-op...
    assert institution.refusal(user, FSU) is None
    # ...but naming somewhere else is still refused, now saying who to ask.
    refused = institution.refusal(user, "University of Florida")
    assert refused is not None
    assert "administrator" in refused
