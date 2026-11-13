"""``seed_demo`` is safe by default: it refuses a DEBUG-off instance without
``--force``, makes accounts nobody can sign in to unless ``--passwords`` is
given, and writes its people file readable by its owner only."""

from __future__ import annotations

import stat

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError

DEMO = "@demo.mycelium.test"


@pytest.mark.django_db
def test_it_refuses_a_production_instance_without_force(settings, tmp_path):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="--force"):
        call_command("seed_demo", "--users", "20", "--logins-dir", str(tmp_path))
    assert not User.objects.filter(email__endswith=DEMO).exists()


@pytest.mark.django_db
def test_default_accounts_cannot_sign_in_and_the_file_is_private(
    settings, tmp_path
):
    settings.DEBUG = True
    call_command("seed_demo", "--users", "20", "--logins-dir", str(tmp_path))
    users = User.objects.filter(email__endswith=DEMO)
    assert users.exists()
    assert not any(u.has_usable_password() for u in users)
    logins = tmp_path / "demo_users.csv"
    assert stat.S_IMODE(logins.stat().st_mode) == 0o600


@pytest.mark.django_db
def test_passwords_are_random_per_run(settings, tmp_path):
    from apps.accounts.management.commands import seed_demo

    settings.DEBUG = True
    call_command(
        "seed_demo", "--users", "20", "--passwords", "--logins-dir", str(tmp_path)
    )
    assert all(
        u.has_usable_password() for u in User.objects.filter(email__endswith=DEMO)
    )
    # the password generator ignores the seeded `random` the data uses
    cmd = seed_demo.Command()
    import random

    random.seed(42)
    first = cmd._password()
    random.seed(42)
    assert cmd._password() != first
