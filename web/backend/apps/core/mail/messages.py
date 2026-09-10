"""The templated-send layer — what product code calls to put mail in an inbox.

:func:`send_email` is the single entry point. It renders a matched pair of
templates (``<name>.html`` and ``<name>.txt`` under ``templates/email/``), builds
a Django ``EmailMultiAlternatives``, and hands it to whichever backend the
settings resolved — Resend in a configured deployment, the console elsewhere.

Two rules are enforced here rather than left to each caller, because each has
already been a real bug somewhere:

* **Every template ships both parts.** A missing ``.txt`` raises at send time
  instead of quietly posting an HTML-only message that some clients render as a
  blank page and some filters score as spam.
* **Links are absolute and never loopback.** A reset link leaves the building.
  ``EMAIL_APP_BASE_URL`` is resolved through the same guard the Discord digest
  links use, so a blank ``PUBLIC_HOSTNAME`` cannot mail someone a link to their
  own machine.

This layer is deliberately synchronous and has no queue behind it. If a flow
later needs delivery to survive a Resend outage, the durable pattern already
exists in :mod:`apps.integrations.services.outbox` and should be copied rather
than reinvented — it is not built here because nothing needs it yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.template.loader import render_to_string

#: Every template this module can send, with the subject it defaults to.
#:
#: A registry rather than free-form template names: it keeps the set of mail this
#: product sends enumerable in one place, and makes a typo in a template name a
#: startup-time error instead of a silent non-delivery.
TEMPLATES: dict[str, str] = {
    "password_reset": "Reset your Mycelium password",
    "lab_invitation": "You have been invited to a lab on Mycelium",
    "department_invitation": "You have been invited to a department on Mycelium",
    "verification_code": "Your Mycelium verification code",
    "test": "Mycelium test",
}


class EmailTemplateError(RuntimeError):
    """A template name that is not in :data:`TEMPLATES`."""


@dataclass(frozen=True)
class MailOutcome:
    """What one :func:`send_email` call did.

    ``sent`` reports that the backend accepted the message, which is not the same
    as the recipient receiving it — see :mod:`apps.core.mail.client`.
    """

    sent: bool
    template: str
    recipients: tuple[str, ...]
    subject: str


def app_url(path: str = "/") -> str:
    """An absolute URL into the app, safe to write into an email.

    Use for every link in a template. Relative paths do not survive leaving the
    building, and a hand-built origin is how a recipient ends up with localhost.
    """
    base = str(settings.EMAIL_APP_BASE_URL or "").rstrip("/") + "/"
    return urljoin(base, str(path or "/").lstrip("/"))


def render(template: str, context: dict | None = None) -> tuple[str, str]:
    """Render ``(html, text)`` for a registered template."""
    if template not in TEMPLATES:
        raise EmailTemplateError(
            f"Unknown email template {template!r}; add it to apps.core.mail.TEMPLATES"
        )
    full = {"app_url": app_url(), "subject": TEMPLATES[template], **(context or {})}
    html = render_to_string(f"email/{template}.html", full)
    # The text half goes through the non-escaping engine (settings.TEMPLATES,
    # NAME="email_text"). Rendering it with the default engine escapes the body,
    # so a reader sees "&lt;" and "&amp;" literally in their client.
    text = render_to_string(f"email/{template}.txt", full, using="email_text")
    return html, text


def send_email(
    template: str,
    *,
    to: str | list[str],
    context: dict | None = None,
    subject: str = "",
    from_email: str = "",
    reply_to: list[str] | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
    fail_silently: bool = False,
) -> MailOutcome:
    """Render ``template`` and send it to ``to``.

    ``fail_silently`` follows Django's meaning: the failure is swallowed and
    ``sent`` comes back false. Leave it off for anything a person is waiting on —
    a reset link that silently never sends is worse than a visible error.
    """
    recipients = normalize_recipients(to)
    resolved_subject = subject or TEMPLATES.get(template, "")
    if not recipients:
        return MailOutcome(False, template, (), resolved_subject)

    html, text = render(template, context)
    message = EmailMultiAlternatives(
        subject=resolved_subject,
        body=text,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        to=list(recipients),
        reply_to=reply_to or _default_reply_to(),
    )
    message.attach_alternative(html, "text/html")
    for filename, content, mimetype in attachments or []:
        message.attach(filename, content, mimetype)

    sent = message.send(fail_silently=fail_silently)
    return MailOutcome(bool(sent), template, recipients, resolved_subject)


def _default_reply_to() -> list[str] | None:
    """The configured Reply-To, or ``None`` so replies fall back to the From address."""
    return [settings.EMAIL_REPLY_TO] if settings.EMAIL_REPLY_TO else None


def normalize_recipients(to: str | list[str] | None) -> tuple[str, ...]:
    """Trimmed, de-duplicated, syntactically valid addresses, order preserved.

    Invalid addresses are dropped rather than raised on. One malformed address in
    a lab-wide invitation should not stop the other twenty from going out, and
    the caller still sees the shortfall in ``MailOutcome.recipients``.
    """
    candidates = [to] if isinstance(to, str) else list(to or [])
    seen: dict[str, None] = {}
    for candidate in candidates:
        address = str(candidate or "").strip()
        if not address:
            continue
        try:
            validate_email(address)
        except ValidationError:
            continue
        seen.setdefault(address, None)
    return tuple(seen)
