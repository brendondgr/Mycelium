"""Phase B+C — provisioning a login + populated profile from an author id."""

import pytest
from django.contrib.auth.models import User

from apps.accounts.intake import AuthorProfileDraft
from apps.accounts.interests import validate_interests
from apps.accounts.models import Profile
from apps.accounts.provisioning import provision_from_author


def _draft() -> AuthorProfileDraft:
    return AuthorProfileDraft(
        display_name="Ada Lovelace",
        institution="Analytical Engine Institute",
        areas=["computational mathematics", "theory of computation"],
        keywords=["recursion"],
        external_ids={"openalex": "A5023888391", "orcid": "0000-0002-1825-0097"},
        evidence=[{"title": "Notes on the Analytical Engine", "year": 2021}],
    )


def _fake_importer(identifier: str, source: str) -> AuthorProfileDraft:
    return _draft()


@pytest.mark.django_db
def test_provision_creates_login_and_profile() -> None:
    result = provision_from_author(
        "A5023888391", "openalex", importer=_fake_importer
    )

    assert User.objects.filter(username=result.credentials["username"]).exists()
    assert result.user.check_password(result.credentials["password"])
    profile = Profile.objects.get(user=result.user)
    assert profile.institution == "Analytical Engine Institute"


@pytest.mark.django_db
def test_provision_stores_external_ids() -> None:
    result = provision_from_author(
        "A5023888391", "openalex", importer=_fake_importer
    )
    profile = result.profile

    assert profile.openalex_id == "A5023888391"
    assert profile.orcid == "0000-0002-1825-0097"
    assert profile.scholar_id == ""


@pytest.mark.django_db
def test_provisioned_interests_are_contract_valid() -> None:
    result = provision_from_author(
        "A5023888391", "openalex", importer=_fake_importer
    )
    # Round-trips through the gate without raising.
    validated = validate_interests(result.profile.interests)
    assert validated["areas"] == [
        "computational mathematics",
        "theory of computation",
    ]
    assert validated["sources"]["openalex"] == "A5023888391"


@pytest.mark.django_db
def test_credentials_row_carries_ids_and_password() -> None:
    creds = provision_from_author(
        "A5023888391", "openalex", importer=_fake_importer
    ).credentials

    assert creds["password"]
    assert creds["openalex_id"] == "A5023888391"
    assert creds["orcid"] == "0000-0002-1825-0097"
    assert creds["name"] == "Ada Lovelace"


@pytest.mark.django_db
def test_usernames_are_unique_across_provisions() -> None:
    first = provision_from_author("A1", "openalex", importer=_fake_importer)
    second = provision_from_author("A2", "openalex", importer=_fake_importer)

    assert first.credentials["username"] != second.credentials["username"]
