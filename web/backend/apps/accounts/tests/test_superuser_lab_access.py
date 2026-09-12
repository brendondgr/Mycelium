"""A superuser is not a member of every lab.

Platform administration happens in ``apps.adminpanel`` (its own ``IsStaffOrSuperuser``
permission) and in Django admin. The workspace API is a *member* surface, and the
``is_superuser`` early-returns that used to sit in ``apps.accounts.permissions`` made
an operator account a silent member of every lab: opening a lab URL showed its feed,
its roster and its settings with no ``LabMembership`` row saying so.

Two reasons that is worth a test rather than a comment. It read other people's
research without leaving anything auditable behind. And it meant the one account most
likely to be reproducing a bug report could not see what the reporter sees.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Lab, LabMembership
from apps.accounts.permissions import (
    user_can_edit_lab_profile,
    user_can_manage_lab,
    user_has_lab_access,
)
from apps.accounts.services import get_lab_for_user


@pytest.fixture
def lab() -> Lab:
    lab = Lab.objects.create(name="Someone Else's Lab", slug="not-mine")
    member = User.objects.create_user(username="member", password="p")
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.OWNER)
    return lab


@pytest.mark.django_db
def test_a_superuser_is_refused_a_lab_it_has_not_joined(lab: Lab) -> None:
    root = User.objects.create_superuser(username="root", password="p")
    assert not user_has_lab_access(root, lab)
    assert not user_can_manage_lab(root, lab)
    assert not user_can_edit_lab_profile(root, lab)
    assert get_lab_for_user(root, lab.slug) is None


@pytest.mark.django_db
def test_the_lab_switcher_never_listed_it_either(lab: Lab) -> None:
    """The API half of the same rule: the workspace list is membership-derived.

    This already held before the permission change — which is exactly why the leak
    was confusing. The lab was absent from the switcher and reachable by URL.
    """
    root = User.objects.create_superuser(username="root", password="p")
    client = APIClient()
    client.force_authenticate(root)
    assert client.get("/api/auth/labs/").data == []


@pytest.mark.django_db
def test_joining_the_lab_is_what_grants_access(lab: Lab) -> None:
    """Membership, not privilege. An operator who needs in is added like anyone else."""
    root = User.objects.create_superuser(username="root", password="p")
    LabMembership.objects.create(user=root, lab=lab, role=LabMembership.Role.ADMIN)

    assert user_has_lab_access(root, lab)
    assert user_can_manage_lab(root, lab)
    assert get_lab_for_user(root, lab.slug) == lab


@pytest.mark.django_db
def test_a_superuser_still_reaches_the_admin_dashboard(lab: Lab) -> None:
    """The intended path is untouched: adminpanel guards on staff/superuser itself."""
    root = User.objects.create_superuser(username="root", password="p")
    client = APIClient()
    client.force_authenticate(root)
    response = client.get("/api/admin/labs/")
    assert response.status_code == 200
    assert any(row["slug"] == lab.slug for row in response.data["results"])


@pytest.mark.django_db
def test_a_plain_member_is_refused_the_admin_dashboard(lab: Lab) -> None:
    client = APIClient()
    client.force_authenticate(User.objects.get(username="member"))
    assert client.get("/api/admin/labs/").status_code == 403
