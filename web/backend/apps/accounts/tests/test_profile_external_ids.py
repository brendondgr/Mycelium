"""Phase B — external author identity fields on Profile."""

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import Profile


@pytest.mark.django_db
def test_external_ids_blank_by_default() -> None:
    user = User.objects.create_user(username="ext", password="pass-123")
    profile = user.profile

    assert profile.orcid == ""
    assert profile.openalex_id == ""
    assert profile.scholar_id == ""


@pytest.mark.django_db
def test_external_ids_persist() -> None:
    user = User.objects.create_user(username="ext2", password="pass-123")
    profile = user.profile
    profile.orcid = "0000-0002-1825-0097"
    profile.openalex_id = "A5023888391"
    profile.scholar_id = "abc123XYZ"
    profile.save()

    profile.refresh_from_db()
    assert profile.orcid == "0000-0002-1825-0097"
    assert profile.openalex_id == "A5023888391"
    assert profile.scholar_id == "abc123XYZ"


@pytest.mark.django_db
def test_external_ids_are_indexed() -> None:
    # Each external-id column carries a db_index so re-imports can look a
    # profile up by its source identifier.
    fields = {f.name: f for f in Profile._meta.get_fields() if hasattr(f, "db_index")}
    assert fields["orcid"].db_index is True
    assert fields["openalex_id"].db_index is True
    assert fields["scholar_id"].db_index is True


@pytest.mark.django_db
def test_lookup_by_external_id() -> None:
    user = User.objects.create_user(username="ext3", password="pass-123")
    user.profile.openalex_id = "A999"
    user.profile.save()

    assert Profile.objects.get(openalex_id="A999").user_id == user.id
