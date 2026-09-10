"""Transactional email for Mycelium, delivered through Resend.

The public surface is :func:`send_email` — everything else is the transport it
sits on. See :mod:`apps.core.mail.messages` for the sending contract,
:mod:`apps.core.mail.backend` for the Django ``EMAIL_BACKEND`` adapter, and
:mod:`apps.core.mail.client` for the Resend wire calls.

This module is a foundation, not a feature: it owns *how* mail is sent, and the
flows that decide *when* — password resets, lab and department invitations,
verification codes — call into it as they are built.
"""

from .client import ResendError, SendResult, is_configured
from .messages import (
    TEMPLATES,
    EmailTemplateError,
    MailOutcome,
    app_url,
    normalize_recipients,
    render,
    send_email,
)

__all__ = [
    "TEMPLATES",
    "EmailTemplateError",
    "MailOutcome",
    "ResendError",
    "SendResult",
    "app_url",
    "is_configured",
    "normalize_recipients",
    "render",
    "send_email",
]
