"""Diagnose the TypeSafe System One seam from inside the backend.

    uv run --project web/backend python web/backend/manage.py typesafe_check

Prints the effective ``TYPESAFE_*`` settings (never the key), then asks one
yes/no question of a fixed sentence and prints the probability, the request id,
the token usage and the wall time. ``--strict`` exits non-zero on any failure so
automation can detect a dead key. The sentence is hand-written: nothing from the
database is ever sent by this command.
"""

from __future__ import annotations

import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

SAMPLE_STATE = {
    "message": (
        "Our lab's grant application is due Friday and the budget section still "
        "has two blank tables."
    )
}


class Command(BaseCommand):
    help = "Check that the TypeSafe System One endpoint is reachable and answers."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit non-zero when the key is missing or the call fails.",
        )

    def handle(self, *args: object, **options: object) -> None:
        strict = bool(options.get("strict"))
        self._print_settings()
        if not self._ping():
            if strict:
                raise CommandError("TypeSafe endpoint unreachable or the call failed.")

    def _print_settings(self) -> None:
        from apps.core.systemone import is_pinned

        self.stdout.write(self.style.MIGRATE_HEADING("Effective TypeSafe settings"))
        for name in (
            "TYPESAFE_MODEL",
            "TYPESAFE_BASE_URL",
            "TYPESAFE_TIMEOUT",
            "TYPESAFE_MAX_RETRIES",
        ):
            self.stdout.write(f"  {name} = {getattr(settings, name, '<unset>')!r}")
        # Never print the key itself — just whether one is set.
        has_key = bool(getattr(settings, "TYPESAFE_API_KEY", ""))
        self.stdout.write(f"  TYPESAFE_API_KEY set = {has_key}")
        if not is_pinned(getattr(settings, "TYPESAFE_MODEL", "")):
            self.stderr.write(
                self.style.WARNING(
                    "  TYPESAFE_MODEL is an alias; pin a version so a recorded "
                    "number names the model that produced it."
                )
            )

    def _ping(self) -> bool:
        from apps.core.systemone import build_systemone_client, noul

        self.stdout.write(self.style.MIGRATE_HEADING("\nAsking one question"))
        try:
            client = build_systemone_client(component="typesafe_check")
            started = time.perf_counter()
            result = client.ask(
                SAMPLE_STATE,
                {"urgent": noul("Does this message express urgency?")},
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
        except Exception as exc:  # noqa: BLE001 — surface the real reason
            self.stderr.write(
                self.style.ERROR(f"  Call failed: {type(exc).__name__}: {exc}")
            )
            return False
        answer = result.answers.get("urgent")
        self.stdout.write(f"  model      = {result.model!r}")
        self.stdout.write(f"  request_id = {result.request_id!r}")
        self.stdout.write(f"  p(urgent)  = {getattr(answer, 'noul', None)!r}")
        self.stdout.write(f"  usage      = {dict(result.usage)!r}")
        self.stdout.write(f"  wall       = {elapsed_ms:.0f} ms")
        self.stdout.write(self.style.SUCCESS("  Endpoint reachable."))
        return True
