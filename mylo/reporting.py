"""Post Mycelium daily-run errors and status to Mylo's Discord error channel.

This is the out-of-process delivery seam the daily run (``manual_all.py``) calls
when something needs a human's attention — a Pivot re-login, an unreachable LLM,
a stage that failed — plus the nightly run summary, which carries the analytics
PDF as an attachment. It posts straight to the channel over Discord's REST API
with the bot token, so it works whether or not the gateway bot process is up.
This matches the ``discord-bot`` standard: an out-of-band announcement from
another process uses REST/webhooks, not the gateway.

Design contract, relied on by the pipeline:

- ``report()`` **never raises** — a broken error channel must not abort the run.
- It **never blocks for long** — a short socket timeout bounds the worst case.
- It uses **only the standard library**, so it runs in the bare root runner
  environment without any extra dependency.

If credentials are missing or Discord is unreachable, it logs a warning and
returns ``False``; the daily pipeline keeps going regardless.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import socket
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

from .config import MyloConfig, load_config

log = logging.getLogger(__name__)

#: Discord REST base. v10 is the current stable version.
DISCORD_API = "https://discord.com/api/v10"

#: Bound the worst case so a hung request can't stall the daily run.
_TIMEOUT_SECONDS = 10
#: An upload needs longer than a text post, but still bounded.
_UPLOAD_TIMEOUT_SECONDS = 60

# Discord embed hard limits we clamp to (see the discord-bot standard).
_TITLE_MAX = 256
_DESC_MAX = 4096
_FIELD_VALUE_MAX = 1024
_FIELDS_MAX = 25

#: Discord's per-file ceiling on a non-boosted guild is 10 MiB. Stay under it —
#: an over-size upload is rejected outright, which would lose the whole message,
#: not just the file. The report is posted without its attachment instead.
_ATTACHMENT_MAX_BYTES = 8 * 1024 * 1024

#: A transport takes (url, headers, body) and returns the HTTP status code.
#: Injectable so tests never touch the network.
Transport = Callable[[str, "dict[str, str]", bytes], int]


class Severity(Enum):
    """Severity of a reported event — drives the embed colour and icon."""

    ERROR = ("error", 0xC0392B, "\U0001F534")  # red circle
    WARN = ("warn", 0xE0A030, "\U0001F7E0")  # orange circle
    INFO = ("info", 0x2E9E6B, "\U0001F7E2")  # green circle

    def __init__(self, label: str, color: int, emoji: str) -> None:
        self.label = label
        self.color = color
        self.emoji = emoji


def _clip(text: str, limit: int) -> str:
    """Truncate ``text`` to ``limit`` chars, leaving a visible ellipsis marker."""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _http_post(url: str, headers: dict[str, str], body: bytes) -> int:
    """Default transport: a plain stdlib POST. Returns the HTTP status code.

    A multipart body (a PDF attachment) is orders of magnitude larger than an
    embed, so the deadline scales with the payload rather than making every post
    wait out the upload budget.
    """
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    timeout = (
        _UPLOAD_TIMEOUT_SECONDS
        if headers.get("Content-Type", "").startswith("multipart/")
        else _TIMEOUT_SECONDS
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:  # 4xx/5xx still carry a status code
        return int(exc.code)


def _encode_multipart(
    payload: dict, filename: str, file_bytes: bytes
) -> tuple[bytes, str]:
    """Build a ``multipart/form-data`` body for one attached file.

    Discord's message-create endpoint takes the JSON message as a ``payload_json``
    part alongside ``files[n]``. Hand-rolled rather than reached for from a
    library because this module's contract is stdlib-only: it has to run in the
    bare root runner environment that the nightly timer starts.

    Returns ``(body, content_type)``.
    """
    boundary = f"----mylo{uuid.uuid4().hex}"
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    crlf = b"\r\n"
    parts: list[bytes] = []

    parts.append(f"--{boundary}".encode())
    parts.append(b'Content-Disposition: form-data; name="payload_json"')
    parts.append(b"Content-Type: application/json")
    parts.append(b"")
    parts.append(json.dumps(payload).encode("utf-8"))

    parts.append(f"--{boundary}".encode())
    parts.append(
        f'Content-Disposition: form-data; name="files[0]"; filename="{filename}"'
        .encode()
    )
    parts.append(f"Content-Type: {mime}".encode())
    parts.append(b"")
    parts.append(file_bytes)

    parts.append(f"--{boundary}--".encode())
    parts.append(b"")
    return crlf.join(parts), f"multipart/form-data; boundary={boundary}"


def _read_attachment(path: str | Path) -> tuple[str, bytes] | None:
    """Read an attachment, or return ``None`` with a warning. Never raises."""
    file_path = Path(path)
    try:
        size = file_path.stat().st_size
    except OSError as exc:
        log.warning("Mylo reporting could not stat attachment %s: %s", file_path, exc)
        return None
    if size > _ATTACHMENT_MAX_BYTES:
        log.warning(
            "Mylo reporting skipped attachment %s: %s bytes exceeds the %s-byte "
            "limit; posting the message without it.",
            file_path,
            size,
            _ATTACHMENT_MAX_BYTES,
        )
        return None
    try:
        return file_path.name, file_path.read_bytes()
    except OSError as exc:
        log.warning("Mylo reporting could not read attachment %s: %s", file_path, exc)
        return None


def _build_payload(
    title: str,
    body: str,
    *,
    severity: Severity,
    stage: str | None,
    action: str | None,
    fields: dict[str, str] | None,
) -> dict:
    """Assemble the Discord message payload (a single embed), clamped to limits."""
    embed_fields: list[dict] = []
    if stage:
        embed_fields.append(
            {"name": "Stage", "value": _clip(stage, _FIELD_VALUE_MAX), "inline": True}
        )
    if action:
        embed_fields.append(
            {
                "name": "Action needed",
                "value": _clip(action, _FIELD_VALUE_MAX),
                "inline": False,
            }
        )
    for name, value in (fields or {}).items():
        # A value may be a plain string (full width, the original shape) or a
        # ``(value, inline)`` pair, which is what lets the run summary sit three
        # small blocks across a row instead of one stacked column.
        inline = False
        if isinstance(value, tuple) and len(value) == 2:
            value, inline = value[0], bool(value[1])
        embed_fields.append(
            {
                "name": _clip(str(name), _TITLE_MAX),
                "value": _clip(str(value), _FIELD_VALUE_MAX),
                "inline": inline,
            }
        )
    # Discord rejects an embed with more than 25 fields outright, which would
    # cost the whole message rather than the overflow.
    embed_fields = embed_fields[:_FIELDS_MAX]

    embed: dict = {
        "title": _clip(f"{severity.emoji} {title}", _TITLE_MAX),
        "color": severity.color,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": _clip(f"Mylo · {socket.gethostname()}", _FIELD_VALUE_MAX)},
    }
    if body:
        embed["description"] = _clip(body, _DESC_MAX)
    if embed_fields:
        embed["fields"] = embed_fields

    return {
        "embeds": [embed],
        # A status post must never be able to ping @everyone just because a
        # rendered string happened to contain it.
        "allowed_mentions": {"parse": []},
    }


def report(
    title: str,
    body: str = "",
    *,
    severity: Severity = Severity.ERROR,
    stage: str | None = None,
    action: str | None = None,
    fields: dict[str, str] | None = None,
    attachment: str | Path | None = None,
    config: MyloConfig | None = None,
    transport: Transport | None = None,
) -> bool:
    """Post one status/error to the Discord error channel. Never raises.

    Args:
        title: Short headline; becomes the embed title (prefixed with a severity
            icon).
        body: Optional longer description.
        severity: :class:`Severity` — controls colour/icon; defaults to ERROR.
        stage: The pipeline stage that produced the event (e.g. ``"scrape"``).
        action: A human next step, shown as a distinct field (e.g. run
            ``uv run pivot.py login``).
        fields: Extra name/value pairs to attach. A value may be a plain string
            or a ``(value, inline)`` pair for a side-by-side block.
        attachment: A file to post beneath the embed (the nightly analytics PDF).
            An unreadable or over-size file is dropped with a warning and the
            message still goes out — the summary matters more than the file.
        config: Injected config (tests); otherwise loaded from ``.env-mylo``.
        transport: Injected sender (tests); otherwise a stdlib HTTP POST.

    Returns:
        ``True`` if Discord accepted the message, ``False`` otherwise (missing
        credentials, network error, or a non-2xx response).
    """
    cfg = config or load_config()
    if not cfg.reporting_enabled:
        log.warning(
            "Mylo reporting disabled (no DISCORD_API_KEY / ERROR_CHANNEL in "
            ".env-mylo); would have reported [%s] %s",
            severity.label,
            title,
        )
        return False

    payload = _build_payload(
        title, body, severity=severity, stage=stage, action=action, fields=fields
    )
    url = f"{DISCORD_API}/channels/{cfg.error_channel_id}/messages"
    headers = {
        "Authorization": f"Bot {cfg.token}",
        "Content-Type": "application/json",
        "User-Agent": "MyloReporter (Mycelium)",
    }

    body_bytes = json.dumps(payload).encode("utf-8")
    if attachment is not None:
        file_part = _read_attachment(attachment)
        if file_part is not None:
            filename, file_bytes = file_part
            body_bytes, content_type = _encode_multipart(
                payload, filename, file_bytes
            )
            headers["Content-Type"] = content_type

    send = transport or _http_post
    try:
        status = send(url, headers, body_bytes)
    except Exception as exc:  # noqa: BLE001 — reporting must never break the run
        log.warning(
            "Mylo reporting failed to reach Discord (%s): %s",
            type(exc).__name__,
            exc,
        )
        return False

    if 200 <= status < 300:
        return True
    log.warning(
        "Mylo reporting got HTTP %s from Discord for [%s] %s",
        status,
        severity.label,
        title,
    )
    return False


def report_error(title: str, body: str = "", **kwargs) -> bool:
    """Convenience wrapper: report at ERROR severity."""
    return report(title, body, severity=Severity.ERROR, **kwargs)


def report_warning(title: str, body: str = "", **kwargs) -> bool:
    """Convenience wrapper: report at WARN severity."""
    return report(title, body, severity=Severity.WARN, **kwargs)


def report_info(title: str, body: str = "", **kwargs) -> bool:
    """Convenience wrapper: report at INFO severity."""
    return report(title, body, severity=Severity.INFO, **kwargs)
