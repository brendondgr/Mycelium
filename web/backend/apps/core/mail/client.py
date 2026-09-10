"""Thin Resend REST client (stdlib urllib).

One call — POST ``/emails`` — because that is the whole of what this scope needs.
No third-party HTTP dependency, matching
:mod:`apps.integrations.services.discord_api`: these are synchronous calls made
from request views and Celery tasks, and a dependency earns its place by doing
something ``urllib`` cannot.

The error surface is deliberately split in two, because the caller's correct
response differs:

* :class:`ResendError` carries ``status`` and Resend's machine-readable ``name``.
* :attr:`ResendError.transient` says whether *trying again later could work*.
  A 429 or a 5xx is the network having a bad minute; a 422 for an unverified
  sending domain will fail identically forever, and retrying it just burns quota.

What this module cannot tell you is whether the mail was **delivered**. Resend
returns an id the moment it accepts the message for sending, and a send-only API
key cannot read the delivery log afterwards. Acceptance here means the message
left the building, nothing more — an unverified domain, a missing DMARC record,
or a spam filter all produce a silent failure that looks exactly like success
from this side.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from django.conf import settings

_UA = "Mycelium (core.mail, v1)"

#: Statuses where the same request, sent later, might succeed.
_TRANSIENT_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


class ResendError(RuntimeError):
    """A non-2xx from Resend, or a transport failure reaching it."""

    def __init__(
        self,
        status: int,
        name: str = "",
        message: str = "",
        *,
        transient: bool | None = None,
    ):
        self.status = status
        self.name = name
        self.message = message
        # ``status=0`` is our own marker for "never got an HTTP response at all"
        # (DNS, TLS, timeout), which is the most transient failure there is.
        self.transient = (
            status == 0 or status in _TRANSIENT_STATUSES
            if transient is None
            else transient
        )
        super().__init__(f"Resend HTTP {status} ({name or 'transport'}): {message}")


@dataclass(frozen=True)
class SendResult:
    """What Resend gave back for an accepted message.

    ``id`` is the handle to look the message up in the Resend dashboard, which is
    the only place its actual delivery outcome can be seen. Log it.
    """

    id: str


def is_configured() -> bool:
    """Whether a send could even be attempted with the current settings."""
    return bool(settings.RESEND_API_KEY)


def send(payload: dict) -> SendResult:
    """POST one message to Resend and return its id.

    ``payload`` is passed through as the Resend message body — ``from``, ``to``,
    ``subject``, ``html`` / ``text``, and optionally ``cc``, ``bcc``,
    ``reply_to``, ``attachments``. Building and validating it belongs to the
    caller; this function owns the wire, not the message.
    """
    if not is_configured():
        raise ResendError(
            0, "not_configured", "RESEND_API_KEY is unset", transient=False
        )

    body = json.dumps(payload).encode()
    request = urllib.request.Request(
        settings.RESEND_API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": _UA,
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=settings.RESEND_TIMEOUT_SECONDS
        ) as response:
            parsed = _parse(response.read())
    except urllib.error.HTTPError as exc:  # a real response, just not a 2xx
        detail = _parse(exc.read())
        raise ResendError(
            exc.code,
            str(detail.get("name", "")),
            str(detail.get("message", "")),
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ResendError(0, "transport", str(exc)) from exc

    message_id = str(parsed.get("id", ""))
    if not message_id:
        # A 2xx with no id means the contract moved under us. Treat it as
        # permanent: retrying cannot produce an id the API did not send.
        raise ResendError(
            200, "no_id", "Resend accepted but returned no id", transient=False
        )
    return SendResult(id=message_id)


def _parse(raw: bytes) -> dict:
    """Best-effort JSON decode; a non-JSON body must not mask the real error."""
    try:
        decoded = json.loads(raw.decode() or "{}")
    except (ValueError, UnicodeDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}
