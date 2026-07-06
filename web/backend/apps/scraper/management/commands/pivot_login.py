"""Interactive Pivot-RP login — opens a browser, saves the SSO session.

    uv run --project web/backend python web/backend/manage.py pivot_login

Run this on a machine with a display (the host, NOT the headless container): a
real Chromium window opens, you complete your institution's SSO + MFA by hand,
press ENTER, and the authenticated session is saved to ``storage_state.json``
(``PIVOT_STORAGE_STATE`` overrides the path). The scrapers reuse that session so
no password is ever stored. Re-run whenever the session expires (~1h idle).

Needs the optional ``pivot`` extra and a browser binary:
    uv sync --project web/backend --extra pivot
    uv run --project web/backend playwright install chromium
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Interactively log in to Pivot-RP and save the session for scraping."

    def handle(self, *args, **options):
        from apps.scraper.pivot.common import STATE_PATH

        try:
            from apps.scraper.pivot.login import login
        except Exception as exc:  # pragma: no cover - import guard
            raise CommandError(
                "Could not start the login flow. Install the browser extra first:\n"
                "  uv sync --project web/backend --extra pivot\n"
                "  uv run --project web/backend playwright install chromium\n"
                f"(underlying error: {exc})"
            ) from exc

        self.stdout.write(f"Session will be saved to: {STATE_PATH}")
        try:
            login()
        except Exception as exc:  # noqa: BLE001 - surface any Playwright error clearly
            raise CommandError(
                f"Login failed: {exc}. Ensure Chromium is installed "
                "(playwright install chromium) and you have a display."
            ) from exc

        from apps.scraper.pivot.common import state_exists

        if state_exists():
            self.stdout.write(self.style.SUCCESS("Session saved. You can now scrape."))
        else:
            self.stdout.write(
                self.style.WARNING("No session saved (login not completed).")
            )
