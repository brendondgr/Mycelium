"""Create or promote a Django superuser admin, reading the password from the env.

This runs *outside* the running web app — a ``manage.py`` command is its own
process — so it can bootstrap the very first admin before anyone can log in. The
password is read ONLY from the ``ADMIN_USER_PASS`` environment variable, which the
project's settings load from the repo-root ``.env`` file. It is never taken from
the command line (so it stays out of shell history) and never printed.

    # ADMIN_USER_PASS=... in .env, then:
    uv run --project web/backend python web/backend/manage.py create_admin alice
    uv run --project web/backend python web/backend/manage.py create_admin alice \
        --email alice@example.org --first-name Alice --last-name Ng

Idempotent and safe to re-run: an existing user is *promoted* to staff+superuser
and their password reset to the current ``ADMIN_USER_PASS`` (identity fields are
only filled from flags, never wiped). The admin is given a minimal onboarded
profile and a personal workspace so they land straight in the app + admin
dashboard instead of the onboarding flow.
"""

from __future__ import annotations

import os

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.services import record_audit_event
from apps.billing.models import Subscription
from apps.billing.services import provision_workspace

#: The only place the admin password may come from (loaded from .env by settings).
ADMIN_PASSWORD_ENV = "ADMIN_USER_PASS"

#: A minimal, contract-shaped interests payload so ``is_onboarding_complete`` is
#: true and the admin is not bounced into onboarding on first sign-in.
ADMIN_INTERESTS = {"version": 1, "areas": ["Platform administration"]}


class Command(BaseCommand):
    help = (
        "Create or promote a superuser admin. The password is read only from the "
        f"{ADMIN_PASSWORD_ENV} environment variable (.env)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("username", help="Username for the admin account.")
        parser.add_argument(
            "--email", default="", help="Email to set (new account, or fill a blank)."
        )
        parser.add_argument("--first-name", dest="first_name", default="")
        parser.add_argument("--last-name", dest="last_name", default="")

    def handle(self, *args, **options) -> None:
        username = str(options["username"]).strip()
        if not username:
            raise CommandError("A non-empty username is required.")

        password = os.environ.get(ADMIN_PASSWORD_ENV, "").strip()
        if not password:
            raise CommandError(
                f"{ADMIN_PASSWORD_ENV} is not set. Add it to your repo-root .env "
                "file — the admin password is read only from there."
            )

        existing = User.objects.filter(username__iexact=username).first()
        try:
            # Enforce the same policy as everywhere else; pass the user so the
            # similarity check is meaningful when promoting an existing account.
            validate_password(password, user=existing)
        except ValidationError as exc:
            raise CommandError(
                f"{ADMIN_PASSWORD_ENV} fails the password policy: "
                + "; ".join(exc.messages)
            ) from exc

        with transaction.atomic():
            user, created = self._upsert_admin(username, password, options)
            self._ensure_onboarded(user)
            self._ensure_workspace(user)
            record_audit_event(
                actor=None,
                action="admin.provision",
                target_type="user",
                target_id=str(user.pk),
                metadata={
                    "username": user.username,
                    "created": created,
                    "via": "create_admin",
                },
            )

        verb = "Created" if created else "Promoted"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} superuser admin '{user.username}' (id={user.pk}). "
                f"Password set from ${ADMIN_PASSWORD_ENV}."
            )
        )

    # -- steps -----------------------------------------------------------------

    def _upsert_admin(self, username: str, password: str, options: dict):
        """Create the user, or promote an existing one; return ``(user, created)``."""
        user = User.objects.filter(username__iexact=username).first()
        created = user is None
        if user is None:
            user = User(username=username)  # post_save signal creates the Profile
        # Only fill identity fields from flags — never blank out existing values.
        if options["email"]:
            user.email = options["email"]
        if options["first_name"]:
            user.first_name = options["first_name"]
        if options["last_name"]:
            user.last_name = options["last_name"]
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)  # hashed by the project's password hashers
        user.save()
        return user, created

    def _ensure_onboarded(self, user: User) -> None:
        """Seed minimal interests so the admin skips the onboarding gate."""
        profile = user.profile
        if not (profile.interests or {}).get("areas"):
            profile.interests = dict(ADMIN_INTERESTS)
            # Include the columns the pre_save embed hook re-derives (mirrors
            # ConfirmIntakeView) so the write stays scoped and consistent.
            profile.save(
                update_fields=[
                    "interests",
                    "embedding_text",
                    "embedding",
                    "updated_at",
                ]
            )

    def _ensure_workspace(self, user: User) -> None:
        """Give the admin a personal workspace (subscription + seat) if absent."""
        if not Subscription.objects.filter(scope_user=user).exists():
            provision_workspace(user, "personal")
