"""The ``create_admin`` management command — the standalone admin bootstrap.

The password is sourced only from ``$ADMIN_USER_PASS``; the command creates or
promotes a staff+superuser, gives them an onboarded profile + a personal
workspace, and is safe to re-run.
"""

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.services import is_onboarding_complete
from apps.billing.models import Subscription

STRONG_PASSWORD = "Str0ng-Admin-Pass-2026"


@pytest.mark.django_db
def test_creates_onboarded_superuser(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_USER_PASS", STRONG_PASSWORD)
    call_command("create_admin", "alice", "--email", "alice@example.org")

    user = User.objects.get(username="alice")
    assert user.is_staff and user.is_superuser
    assert user.email == "alice@example.org"
    assert user.check_password(STRONG_PASSWORD)
    # Onboarded (minimal interests) so they are not bounced to onboarding.
    assert is_onboarding_complete(user) is True
    # And a personal workspace exists so entitlement reads are consistent.
    assert Subscription.objects.filter(scope_user=user).exists()


@pytest.mark.django_db
def test_missing_password_env_errors(monkeypatch) -> None:
    monkeypatch.delenv("ADMIN_USER_PASS", raising=False)
    with pytest.raises(CommandError, match="ADMIN_USER_PASS is not set"):
        call_command("create_admin", "bob")
    assert not User.objects.filter(username="bob").exists()


@pytest.mark.django_db
def test_weak_password_rejected(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_USER_PASS", "password")  # common → policy failure
    with pytest.raises(CommandError, match="password policy"):
        call_command("create_admin", "carol")
    assert not User.objects.filter(username="carol").exists()


@pytest.mark.django_db
def test_promotes_existing_user_without_wiping_identity(monkeypatch) -> None:
    existing = User.objects.create_user(
        username="dave",
        email="dave@example.org",
        password="original-pass",
        first_name="Dave",
    )
    assert not existing.is_superuser

    monkeypatch.setenv("ADMIN_USER_PASS", STRONG_PASSWORD)
    call_command("create_admin", "dave")  # no flags: identity must survive

    existing.refresh_from_db()
    assert existing.is_staff and existing.is_superuser
    assert existing.check_password(STRONG_PASSWORD)  # password reset
    assert existing.email == "dave@example.org"  # not wiped
    assert existing.first_name == "Dave"


@pytest.mark.django_db
def test_rerun_is_idempotent(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_USER_PASS", STRONG_PASSWORD)
    call_command("create_admin", "erin")
    call_command("create_admin", "erin")  # second run must not raise or duplicate

    users = User.objects.filter(username="erin")
    assert users.count() == 1
    assert Subscription.objects.filter(scope_user=users.first()).count() == 1
