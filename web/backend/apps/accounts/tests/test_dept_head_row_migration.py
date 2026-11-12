"""Migration 0033 gives every department head an OWNER row and only them."""

import importlib

import pytest
from django.apps import apps as django_apps
from django.contrib.auth.models import User

from apps.accounts.models import Department, DeptMembership

migration = importlib.import_module(
    "apps.accounts.migrations.0033_department_head_membership"
)


@pytest.mark.django_db
def test_heads_get_an_owner_row_and_stray_owners_become_admins() -> None:
    head = User.objects.create_user("head")
    legacy = Department.objects.create(owner=head, name="Legacy")
    other_head = User.objects.create_user("other_head")
    crowded = Department.objects.create(owner=other_head, name="Crowded")
    DeptMembership.objects.create(department=crowded, user=other_head, role="member")
    stray = User.objects.create_user("stray")
    DeptMembership.objects.create(department=crowded, user=stray, role="owner")

    migration.forwards(django_apps, None)

    assert DeptMembership.objects.get(department=legacy, user=head).role == "owner"
    assert (
        DeptMembership.objects.get(department=crowded, user=other_head).role
        == "owner"
    )
    assert DeptMembership.objects.get(department=crowded, user=stray).role == "admin"
