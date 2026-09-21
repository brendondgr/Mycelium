"""Place an account at an institution its email cannot prove.

The escape hatch for the case the derivation is wrong about rather than the case
it is built for: a real affiliation held on an address the directory does not
place — a collaborator using a personal mailbox, or an institute missing from
the list. It does not reopen "typed institutions"; the subject still cannot set
their own. An operator does, by name, and the grant records who and when.

    uv run --project web/backend python web/backend/manage.py \\
        grant_institution --user olmozavala --institution "Florida State University"
    ... --revoke                 # drop the grant, fall back to the address
    ... --actor bdgr             # who is accountable (defaults to no actor)

The institution must already exist in the affiliation directory, so a grant can
place someone but never invent somewhere. If it is genuinely missing, add it to
``web/scripts/data/research-institutions.json`` and rebuild with
``npm run institutions`` first.
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from apps.accounts import institution


class Command(BaseCommand):
    help = "Grant (or revoke) an institution for an account that cannot prove one."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--user",
            "-u",
            required=True,
            metavar="USERNAME",
            help="The account to place.",
        )
        parser.add_argument(
            "--institution",
            "-i",
            metavar="NAME",
            help="The institution to grant, as the directory spells it.",
        )
        parser.add_argument(
            "--actor",
            metavar="USERNAME",
            help="Who is accountable for the grant; recorded in the audit log.",
        )
        parser.add_argument(
            "--revoke",
            action="store_true",
            help="Remove the grant instead, falling back to the verified address.",
        )

    def handle(self, *args, **options) -> None:
        user = self._user(options["user"])
        actor = self._user(options["actor"]) if options.get("actor") else None

        if options["revoke"]:
            now = institution.revoke_grant(user, actor=actor)
            self.stdout.write(
                self.style.SUCCESS(
                    f"{user.get_username()}: grant revoked; "
                    f"institution is now {now or '(none)'}."
                )
            )
            return

        name = (options.get("institution") or "").strip()
        if not name:
            raise CommandError("Pass --institution, or --revoke.")
        try:
            granted = institution.grant(user, name, actor=actor)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(f"{user.get_username()}: institution is now {granted}.")
        )

    @staticmethod
    def _user(username: str) -> User:
        found = User.objects.filter(username=username).first()
        if found is None:
            raise CommandError(f"No account named {username!r}.")
        return found
