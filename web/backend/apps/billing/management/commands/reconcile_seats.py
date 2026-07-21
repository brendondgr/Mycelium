"""Backfill billing seats so every membership on an ACTIVE org plan holds its seat.

The live path is the ``seat_sync`` service (called from invite-accept and the member/lab
endpoints); this command is the bulk backstop for memberships that predate a fix, seed,
or a direct admin add. It seats against the same rules the live path uses:

- Lab members are seated on the correct **paying scope** — the lab's active plan, or its
  department's plan when the lab belongs to an active department (decision B2).
- A department's plan seats its full **effective** membership (direct members ∪ every
  member of every lab under it, decision L2) ACTIVE + department-paid.

Memberships on an INACTIVE / unsubscribed org are left alone (nothing to seat yet).

    # preview only — no writes
    uv run --project web/backend python web/backend/manage.py reconcile_seats --dry-run

    # actually backfill
    uv run --project web/backend python web/backend/manage.py reconcile_seats

Safe to re-run: granting is idempotent, so an already-seated member is skipped.
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from apps.accounts.models import Department, LabMembership
from apps.accounts.services import effective_member_ids
from apps.billing.models import Seat
from apps.billing.seat_sync import (
    paying_scope_for_lab,
    sync_dept_member,
    sync_lab_member,
)
from apps.billing.seats import (
    SeatCeilingExceeded,
    _active_subscription_for_department,
)


class Command(BaseCommand):
    help = "Backfill billing seats for lab/department memberships that have none."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be seated without writing.",
        )

    def handle(self, *args, dry_run: bool = False, **options):
        granted = 0
        over_cap = 0
        no_subscription = 0

        def has_active_seat(subscription, user_id: int) -> bool:
            return Seat.objects.filter(
                subscription=subscription,
                member_id=user_id,
                status=Seat.Status.ACTIVE,
            ).exists()

        # Lab members → the correct paying scope (lab, or its active department).
        for membership in LabMembership.objects.select_related(
            "lab", "lab__department", "user"
        ):
            kind, subscription = paying_scope_for_lab(membership.lab)
            if subscription is None:
                no_subscription += 1
                continue
            if has_active_seat(subscription, membership.user_id):
                continue
            label = f"lab {membership.lab.slug} ← {membership.user.get_username()}"
            if dry_run:
                granted += 1
                self.stdout.write(f"would seat ({kind}) {label}")
                continue
            try:
                sync_lab_member(membership.user, membership.lab)
                granted += 1
            except SeatCeilingExceeded:
                over_cap += 1
                self.stderr.write(f"over member ceiling, skipped {label}")

        # Department effective membership → ACTIVE, department-paid. Lab-under-dept
        # members already seated above are skipped by the active-seat check.
        for department in Department.objects.all():
            subscription = _active_subscription_for_department(department)
            if subscription is None:
                continue
            for user_id in effective_member_ids(department):
                if has_active_seat(subscription, user_id):
                    continue
                if dry_run:
                    granted += 1
                    self.stdout.write(
                        f"would seat (department) dept {department.id} ← user {user_id}"
                    )
                    continue
                sync_dept_member(User.objects.get(id=user_id), department)
                granted += 1

        verb = "would grant" if dry_run else "granted"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {granted} seat(s); {no_subscription} membership(s) on an "
                f"inactive/unsubscribed org; {over_cap} over the ceiling."
            )
        )
