"""Django ``EMAIL_BACKEND`` that delivers through Resend.

Registered as the transport for :mod:`django.core.mail` so every sender in the
codebase — this module's own :func:`apps.core.mail.send_email`, Django's built-in
password-reset views when they are built, ``mail_admins`` — reaches Resend
through one path, with one sender identity and one place to change.

Adapting rather than replacing Django's ``EmailMessage`` is the point. It already
models multipart alternatives, cc/bcc, reply-to and attachments; re-inventing
that would mean the built-in password reset could not use it.

``fail_silently`` keeps Django's documented meaning: swallow the failure and
report zero sent. Everything else raises, so a caller that must know can know.
"""

from __future__ import annotations

import base64
import logging

from django.core.mail.backends.base import BaseEmailBackend

from . import client

logger = logging.getLogger("mycelium.mail")


class ResendEmailBackend(BaseEmailBackend):
    """Send Django ``EmailMessage`` objects via the Resend API."""

    def send_messages(self, email_messages) -> int:
        sent = 0
        for message in email_messages or []:
            if not message.recipients():
                continue  # Django's contract: no recipients is a silent no-op.
            try:
                result = client.send(_to_payload(message))
            except client.ResendError as exc:
                # The id is the only handle on a message once it is accepted, and
                # a failure has none — so log the addressing instead, at a level
                # that survives production filtering.
                logger.error(
                    "Resend send failed "
                    "(status=%s name=%s transient=%s to=%s subject=%r)",
                    exc.status,
                    exc.name,
                    exc.transient,
                    ", ".join(message.recipients()),
                    message.subject,
                )
                if not self.fail_silently:
                    raise
                continue
            logger.info(
                "Resend accepted message id=%s to=%s subject=%r",
                result.id,
                ", ".join(message.recipients()),
                message.subject,
            )
            sent += 1
        return sent


def _to_payload(message) -> dict:
    """Translate one Django ``EmailMessage`` into a Resend message body.

    Both a text and an HTML part are sent whenever the message carries both.
    That is not decoration: a plain-text alternative measurably helps a message
    past spam filtering, and it is the only version some clients will render.
    """
    payload: dict = {
        "from": message.from_email,
        "to": list(message.to or []),
        "subject": message.subject or "",
    }

    # Django expresses "this body is HTML" two ways: content_subtype on a plain
    # EmailMessage, or an alternatives entry on EmailMultiAlternatives. Honour both.
    if getattr(message, "content_subtype", "plain") == "html":
        payload["html"] = message.body or ""
    else:
        payload["text"] = message.body or ""
    for content, mimetype in getattr(message, "alternatives", None) or []:
        if mimetype == "text/html":
            payload["html"] = content
        elif mimetype == "text/plain":
            payload["text"] = content

    if message.cc:
        payload["cc"] = list(message.cc)
    if message.bcc:
        payload["bcc"] = list(message.bcc)
    if getattr(message, "reply_to", None):
        payload["reply_to"] = list(message.reply_to)

    attachments = [_attachment(a) for a in getattr(message, "attachments", None) or []]
    if any(a is None for a in attachments):
        # A MIMEBase attachment (rather than the 3-tuple form) has no filename we
        # can rely on. Dropping it silently would send a "your report is attached"
        # mail with nothing attached, so refuse the whole message instead.
        raise ValueError(
            "ResendEmailBackend supports only "
            "(filename, content, mimetype) attachments"
        )
    if attachments:
        payload["attachments"] = attachments

    return payload


def _attachment(attachment) -> dict | None:
    """One Django attachment tuple as Resend's base64 form, else ``None``."""
    if not isinstance(attachment, (tuple, list)) or len(attachment) != 3:
        return None
    filename, content, _mimetype = attachment
    if isinstance(content, str):
        content = content.encode()
    return {"filename": filename, "content": base64.b64encode(content).decode()}
