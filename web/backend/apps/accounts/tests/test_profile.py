import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from apps.accounts.models import AcademicTitle, Profile


@pytest.mark.django_db
def test_profile_is_auto_created_for_new_user() -> None:
    user = User.objects.create_user(username="researcher", password="pass-123")

    assert Profile.objects.filter(user=user).exists()
    assert user.profile.academic_title == AcademicTitle.RESEARCHER
    assert user.profile.interests == {}
    assert user.profile.embedding is None


@pytest.mark.django_db
def test_profile_is_one_to_one() -> None:
    user = User.objects.create_user(username="researcher", password="pass-123")

    with pytest.raises(IntegrityError), transaction.atomic():
        Profile.objects.create(user=user)


@pytest.mark.django_db
def test_profile_title_can_be_set() -> None:
    user = User.objects.create_user(username="pi-user", password="pass-123")
    profile = user.profile
    profile.academic_title = AcademicTitle.PI
    profile.institution = "Example University"
    profile.interests = {"areas": ["genomics"], "funding_needs": ["R01"]}
    profile.save()

    profile.refresh_from_db()
    assert profile.academic_title == AcademicTitle.PI
    assert profile.interests["areas"] == ["genomics"]


@pytest.mark.django_db
def test_profile_removed_with_user() -> None:
    user = User.objects.create_user(username="temp", password="pass-123")
    profile_id = user.profile.id

    user.delete()

    assert not Profile.objects.filter(id=profile_id).exists()
