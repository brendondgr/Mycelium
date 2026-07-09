"""Delete the fake users created by the onboarding load test (``loadtest.py``).

The load-test harness is a pure HTTP client, but there is no HTTP endpoint that
deletes a user — and cleaning up after a stress run must cascade a user's whole
footprint (Profile, Subscription, Seat, RelevanceScore, SavedOpportunity, audit
events). Deleting the ``User`` row does exactly that for a ``personal`` account,
so cleanup is an ORM operation, exposed here as a management command the harness
shells out to at the end of a run (and that an operator can run by hand).

Fake users are marked two ways, mirroring the demo seeder's convention:

- **email domain** — every load-test account uses ``@loadtest.mycelium.test``.
- **username prefix** — every username starts with ``lt_`` (optionally
  ``lt_<run-id>_`` so a single run can be purged in isolation).

The email-domain marker is always required, so this command can never match a
real account. Staff and superusers are refused outright as a second guard.

    # (prefix: uv run --project web/backend python web/backend/manage.py)
    <prefix> loadtest_purge              # delete every load-test user
    <prefix> loadtest_purge --dry-run    # preview only, delete nothing
    <prefix> loadtest_purge --run-id 7f3a1c   # delete just one run's users
"""

from __future__ import annotations

import argparse

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db.models import Q

#: Every load-test account is created with this email domain — the safety marker.
DEFAULT_EMAIL_DOMAIN = "loadtest.mycelium.test"
#: Every load-test username starts with this prefix.
DEFAULT_USERNAME_PREFIX = "lt_"


class Command(BaseCommand):
    help = "Delete load-test users (marked by @loadtest.mycelium.test / lt_ prefix)."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--email-domain",
            default=DEFAULT_EMAIL_DOMAIN,
            help=(
                "Required safety marker: only accounts whose email ends with "
                f"@<domain> are eligible (default: {DEFAULT_EMAIL_DOMAIN})."
            ),
        )
        parser.add_argument(
            "--username-prefix",
            default=DEFAULT_USERNAME_PREFIX,
            help=(
                "Extra filter: only usernames starting with this prefix "
                f"(default: {DEFAULT_USERNAME_PREFIX!r}). Pass '' to disable."
            ),
        )
        parser.add_argument(
            "--run-id",
            default="",
            help=(
                "Limit to one run: matches usernames beginning "
                "'<prefix><run-id>_'. Omit to purge every load-test user."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without deleting anything.",
        )

    def handle(self, *args, **options) -> None:
        email_domain = str(options["email_domain"]).strip().lstrip("@")
        username_prefix = str(options["username_prefix"])
        run_id = str(options["run_id"]).strip()
        dry_run = bool(options["dry_run"])

        if not email_domain:
            # The domain is the one guard that makes this command safe; never run
            # without it, or an empty filter could match every account.
            self.stderr.write(
                self.style.ERROR("--email-domain is required and cannot be empty.")
            )
            return

        # Build the marker filter. The email domain is mandatory; the username
        # prefix (and optional run-id) narrow it further.
        query = Q(email__iendswith=f"@{email_domain}")
        if run_id:
            query &= Q(username__startswith=f"{username_prefix}{run_id}_")
        elif username_prefix:
            query &= Q(username__startswith=username_prefix)

        # Never touch privileged accounts, even if one somehow matched the marker.
        candidates = User.objects.filter(query).exclude(
            Q(is_staff=True) | Q(is_superuser=True)
        )

        total = candidates.count()
        if total == 0:
            self.stdout.write("No load-test users matched — nothing to delete.")
            return

        if dry_run:
            sample = list(candidates.values_list("username", flat=True)[:10])
            preview = ", ".join(sample)
            more = "" if total <= len(sample) else f", … (+{total - len(sample)} more)"
            self.stdout.write(
                self.style.WARNING(
                    f"[dry-run] would delete {total} load-test user(s): "
                    f"{preview}{more}"
                )
            )
            return

        # delete() cascades Profile / Subscription / Seat / RelevanceScore /
        # SavedOpportunity / audit rows for these personal accounts.
        deleted_count, by_model = candidates.delete()
        users_removed = by_model.get("auth.User", 0)
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {users_removed} load-test user(s) "
                f"({deleted_count} rows total across cascaded tables)."
            )
        )
