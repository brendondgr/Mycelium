"""Backfill billing seats for memberships that predate seat-on-accept.

Before ``accept_invitation`` granted a seat, an invited member of a paying lab got
a ``LabMembership`` and **no** ``Seat`` — so they silently resolved to Free. This
command sweeps every lab / department membership and grants the missing seat
(lab members ACTIVE + lab-paid; department members PENDING). Memberships on a lab
with no active subscription (a Free lab) are left alone.

    # preview only — no writes
    uv run --project web/backend python web/backend/manage.py reconcile_seats --dry-run

    # actually backfill
    uv run --project web/backend python web/backend/manage.py reconcile_seats

Safe to re-run: granting is idempotent, so an already-seated member is skipped.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.accounts.models import DeptMembership, LabMembership
from apps.billing.models import Seat
from apps.billing.seats import (
    SeatCeilingExceeded,
    _active_subscription_for_department,
    _active_subscription_for_lab,
    grant_seat_for_dept_member,
    grant_seat_for_lab_member,
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

        def needs_seat(subscription, user) -> bool:
            return not Seat.objects.filter(
                subscription=subscription,
                member=user,
                status=Seat.Status.ACTIVE,
            ).exists()

        for membership in LabMembership.objects.select_related("lab", "user"):
            subscription = _active_subscription_for_lab(membership.lab)
            if subscription is None:
                no_subscription += 1
                continue
            if not needs_seat(subscription, membership.user):
                continue
            label = f"lab {membership.lab.slug} ← {membership.user.get_username()}"
            if dry_run:
                granted += 1
                self.stdout.write(f"would seat {label}")
                continue
            try:
                grant_seat_for_lab_member(membership.user, membership.lab)
                granted += 1
            except SeatCeilingExceeded:
                over_cap += 1
                self.stderr.write(f"over member ceiling, skipped {label}")

        # Department members seat as PENDING (an admin activates them). A PENDING
        # seat still counts as "seated" for reconcile — we only backfill absences.
        for membership in DeptMembership.objects.select_related("department", "user"):
            subscription = _active_subscription_for_department(membership.department)
            if subscription is None:
                no_subscription += 1
                continue
            if Seat.objects.filter(
                subscription=subscription, member=membership.user
            ).exists():
                continue
            label = (
                f"dept {membership.department_id} ← {membership.user.get_username()}"
            )
            if dry_run:
                granted += 1
                self.stdout.write(f"would seat (pending) {label}")
                continue
            grant_seat_for_dept_member(membership.user, membership.department)
            granted += 1

        verb = "would grant" if dry_run else "granted"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {granted} seat(s); {no_subscription} membership(s) on a "
                f"lab/dept with no active subscription; {over_cap} over the ceiling."
            )
        )
