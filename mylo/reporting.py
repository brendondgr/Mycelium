"""Post Mycelium daily-run errors and status to Mylo's Discord error channel.

This is the out-of-process delivery seam the daily run (``manual_all.py``) calls
when something needs a human's attention — a Pivot re-login, an unreachable LLM,
a stage that failed — plus an optional success summary. It posts straight to the
channel over Discord's REST API with the bot token, so it works whether or not
the gateway bot process is up. This matches the ``discord-bot`` standard: an
out-of-band announcement from another process uses REST/webhooks, not the
gateway.

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
import socket
import urllib.error
import urllib.request
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

from .config import MyloConfig, load_config

log = logging.getLogger(__name__)

#: Discord REST base. v10 is the current stable version.
DISCORD_API = "https://discord.com/api/v10"

#: Bound the worst case so a hung request can't stall the daily run.
_TIMEOUT_SECONDS = 10

# Discord embed hard limits we clamp to (see the discord-bot standard).
_TITLE_MAX = 256
_DESC_MAX = 4096
_FIELD_VALUE_MAX = 1024

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
    """Default transport: a plain stdlib POST. Returns the HTTP status code."""
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:  # 4xx/5xx still carry a status code
        return int(exc.code)


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
        embed_fields.append(
            {
                "name": _clip(str(name), _TITLE_MAX),
                "value": _clip(str(value), _FIELD_VALUE_MAX),
                "inline": False,
            }
        )

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
        fields: Extra name/value pairs to attach.
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
    send = transport or _http_post
    try:
        status = send(url, headers, json.dumps(payload).encode("utf-8"))
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
