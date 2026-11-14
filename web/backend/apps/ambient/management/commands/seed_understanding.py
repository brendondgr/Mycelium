"""Write a fixture person's "Mylo & you" rows: open questions and changes.

For a fictional world such as the public demo's lab (``apps/demo``), which may
not import this app (``tests/test_import_boundary.py``) and so calls this
command by name. It replaces the person's open questions and change log with
the ones given, so it refuses anyone whose email is not on a reserved
``.invalid`` domain: it must never touch a real person's record.

    manage.py seed_understanding '{"user": "demo.mara", "questions": [...],
                                    "changes": [...]}'

A question is ``{"kind", "topic", "explanation", "choices": [{"key",
"label"}], "project"?: <uuid>, "days_open"?: 14}``. It is stored as already
asked, so the nightly never sends it as a message or rings the bell. A change
is ``{"kind", "topic", "project"?, "field"?, "old_value"?, "new_value"?,
"explanation"?, "visibility"?}``.
"""

from __future__ import annotations

import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.ambient import review
from apps.ambient.models import AppliedChange, PendingSuggestion
from apps.research.models import Project


class Command(BaseCommand):
    help = "Replace a fixture person's Mylo & you questions and changes."

    def add_arguments(self, parser) -> None:
        parser.add_argument("spec", help="JSON: user, questions, changes.")

    def handle(self, *args, **options) -> None:
        try:
            spec = json.loads(options["spec"])
        except ValueError as exc:
            raise CommandError(f"The spec is not JSON: {exc}") from exc
        user = get_user_model().objects.filter(username=spec.get("user")).first()
        if user is None:
            raise CommandError(f"No such user: {spec.get('user')!r}")
        if not (user.email or "").lower().endswith(".invalid"):
            raise CommandError(
                f"{user.username} is not a fixture account (its email is not on a "
                ".invalid domain); refusing to replace its record."
            )
        now = timezone.now()
        with transaction.atomic():
            PendingSuggestion.objects.filter(user=user).delete()
            AppliedChange.objects.filter(user=user).delete()
            for q in spec.get("questions", []):
                PendingSuggestion.objects.create(
                    user=user,
                    kind=q["kind"],
                    topic=q["topic"][:200],
                    explanation=q.get("explanation", ""),
                    choices=q.get("choices", []),
                    project=_project(q.get("project")),
                    influence=float(q.get("influence", 0.6)),
                    state=PendingSuggestion.State.ASKED,
                    asked_at=now,
                    expires_at=now + timedelta(days=int(q.get("days_open", 14))),
                )
            for c in spec.get("changes", []):
                review.record(
                    user,
                    c["kind"],
                    c["topic"],
                    project=_project(c.get("project")),
                    field=c.get("field", ""),
                    old_value=c.get("old_value"),
                    new_value=c.get("new_value"),
                    explanation=c.get("explanation", ""),
                    visibility=c.get("visibility", "personal"),
                )
        self.stdout.write(
            f"{user.username}: {len(spec.get('questions', []))} question(s), "
            f"{len(spec.get('changes', []))} change(s)"
        )


def _project(pk):
    return Project.objects.filter(pk=pk).first() if pk else None
