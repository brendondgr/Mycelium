import pytest
from django.contrib.auth.models import User

from apps.accounts.models import Lab, LabMembership
from apps.accounts.permissions import user_can_manage_lab, user_has_lab_access
from apps.accounts.services import get_lab_for_user, record_audit_event


@pytest.fixture
def owner(db: None) -> User:
    return User.objects.create_user(username="owner", password="pass-123")


@pytest.fixture
def member(db: None) -> User:
    return User.objects.create_user(username="member", password="pass-123")


@pytest.fixture
def outsider(db: None) -> User:
    return User.objects.create_user(username="outsider", password="pass-123")


@pytest.fixture
def lab(db: None) -> Lab:
    return Lab.objects.create(name="Forest Lab", slug="forest-lab")


@pytest.mark.django_db
def test_user_without_membership_cannot_access_lab(
    member: User,
    outsider: User,
    lab: Lab,
) -> None:
    LabMembership.objects.create(
        user=member,
        lab=lab,
        role=LabMembership.Role.MEMBER,
    )

    assert user_has_lab_access(member, lab) is True
    assert user_has_lab_access(outsider, lab) is False
    assert get_lab_for_user(outsider, lab.slug) is None
    assert get_lab_for_user(member, lab.slug) == lab


@pytest.mark.django_db
def test_only_admins_can_manage_lab(owner: User, member: User, lab: Lab) -> None:
    LabMembership.objects.create(
        user=owner,
        lab=lab,
        role=LabMembership.Role.OWNER,
    )
    LabMembership.objects.create(
        user=member,
        lab=lab,
        role=LabMembership.Role.MEMBER,
    )

    assert user_can_manage_lab(owner, lab) is True
    assert user_can_manage_lab(member, lab) is False


@pytest.mark.django_db
def test_audit_event_records_actor(owner: User, lab: Lab) -> None:
    event = record_audit_event(
        actor=owner,
        action="lab.viewed",
        target_type="lab",
        target_id=str(lab.pk),
        metadata={"slug": lab.slug},
    )

    assert event.actor == owner
    assert event.target_type == "lab"
    assert event.metadata["slug"] == lab.slug
