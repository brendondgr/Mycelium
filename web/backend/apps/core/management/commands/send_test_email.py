"""Send one real email, to prove the transport is configured end to end.

    uv run --project web/backend python web/backend/manage.py \
        send_test_email --to you@example.com

This is the operational counterpart to a curl against the Resend API: it goes
through the *actual* stack the product uses — settings, template registry, Django
message, backend adapter — so a pass means the product can send, not merely that
the key is valid.

Read the output carefully. "Accepted" is not "delivered": Resend returns an id
the moment it queues the message, and the send-only API key cannot read the
delivery log afterwards. An unverified domain, a missing DMARC record, or a spam
filter all fail *after* this command reports success. The printed id is how you
look the real outcome up in the Resend dashboard.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.core import mail


class Command(BaseCommand):
    help = "Send a test email through the configured backend."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--to", required=True, help="Recipient address.")
        parser.add_argument(
            "--template",
            default="test",
            choices=sorted(mail.TEMPLATES),
            help="Which registered template to render (default: test).",
        )

    def handle(self, *args: object, **options: object) -> None:
        recipient = str(options["to"])
        template = str(options["template"])

        provider = settings.EMAIL_PROVIDER
        self.stdout.write(f"email.provider  {provider}")
        self.stdout.write(f"EMAIL_BACKEND   {settings.EMAIL_BACKEND}")
        self.stdout.write(f"From            {settings.DEFAULT_FROM_EMAIL}")
        self.stdout.write(f"App base URL    {settings.EMAIL_APP_BASE_URL}")
        if provider == "none":
            self.stdout.write(
                self.style.WARNING(
                    'email.provider is "none" — the message will be printed, '
                    "not sent."
                )
            )
        elif provider == "resend" and not mail.is_configured():
            raise CommandError(
                'email.provider is "resend" but RESEND_API_KEY is unset.'
            )
        elif provider == "smtp" and not settings.EMAIL_HOST:
            raise CommandError('email.provider is "smtp" but email.smtp_host is unset.')

        if not mail.normalize_recipients(recipient):
            raise CommandError(f"{recipient!r} is not a valid email address.")

        outcome = mail.send_email(
            template,
            to=recipient,
            context=_sample_context(),
        )
        if not outcome.sent:
            raise CommandError("The backend reported nothing sent.")
        self.stdout.write(
            self.style.SUCCESS(
                f"Accepted for delivery to {', '.join(outcome.recipients)}."
            )
        )
        self.stdout.write(
            "Accepted is not delivered — check the Resend dashboard for the outcome."
        )


def _sample_context() -> dict:
    """Placeholder values so any template renders without a real record behind it."""
    return {
        "sent_at": timezone.now().strftime("%Y-%m-%d %H:%M %Z"),
        "sender": settings.DEFAULT_FROM_EMAIL,
        "recipient_name": "there",
        "inviter_name": "A Mycelium colleague",
        "lab_name": "Sample Lab",
        "department_name": "Sample Department",
        "message": "",
        "code": "123456",
        "expires_in": "1 hour",
        "reset_url": mail.app_url("/reset-password?token=sample-token"),
        "invitation_url": mail.app_url("/invitations/sample-token"),
    }
