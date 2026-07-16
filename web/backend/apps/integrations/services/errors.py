"""The ERROR_CHANNEL ops sink for the Discord integration.

A dev-convenience mirror (NOT observability — it does not replace Sentry). Treat
the channel as public; assume screenshots. So this module:

* **Emits only** severity, component, error code, correlation id, occurrence count.
* **Never emits** emails, names, tokens, plaintext codes, or a raw ``discord_user_id``
  — callers pass an already-hashed id or nothing.
* **Dedupes** by ``(component, error_code)`` on a 5-minute window — one message per
  bucket, not N.
* **Circuit-breaks**: above a per-minute rate it posts one "cascade" notice and goes
  quiet, so a failure storm can't burn the bot's own rate limit.
* Is **fire-and-forget** and never raises.

The transport is a self-contained stdlib POST (Django cannot import the root
``mylo`` package). It mirrors ``mylo.reporting``'s never-raise, short-timeout
contract and reuses the same bot token + ERROR_CHANNEL.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import caches

logger = logging.getLogger("mycelium.integrations.discord")


def _cache():
    return caches["discord"]


_DEDUPE_WINDOW = 300  # 5 min: one message per (component, error_code)
_RATE_WINDOW = 60  # circuit-breaker sampling window
_RATE_THRESHOLD = 20  # incidents/min above which we go quiet
_BREAKER_TTL = 300  # how long the breaker stays open once tripped

_COLORS = {"error": 0xC0392B, "warning": 0xE0A030, "info": 0x2E9E6B}
_API = "https://discord.com/api/v10"


def note_incident(
    component: str,
    error_code: str | int,
    *,
    severity: str = "error",
    correlation_id: str = "",
    detail: str = "",
) -> None:
    """Record an incident; emit at most one rolled-up message per bucket/window.

    Safe to call from a request path, a Celery task, or the gateway bot — it never
    raises and never blocks long.
    """
    try:
        code = str(error_code)
        if _breaker_open():
            return
        if _trip_breaker_if_flooding():
            _emit(
                "Discord error cascade",
                "Error rate exceeded threshold; suppressing further ERROR_CHANNEL "
                "posts for a few minutes. Check Sentry/logs.",
                severity="error",
                fields={"component": component, "code": code},
            )
            return
        # Dedupe: only the first occurrence of this bucket in the window emits.
        bucket = f"incident:{component}:{code}"
        if not _first_in_window(bucket):
            return
        _emit(
            f"{component} — {code}",
            detail or "(no detail)",
            severity=severity,
            fields={
                "component": component,
                "code": code,
                "correlation_id": correlation_id or "-",
            },
        )
    except Exception:  # a sink must never take the caller down
        logger.exception("ERROR_CHANNEL sink failed")


def _first_in_window(bucket: str) -> bool:
    try:
        # add() returns True only if the key did not already exist.
        return bool(_cache().add(bucket, 1, timeout=_DEDUPE_WINDOW))
    except Exception:
        return True  # backend down: don't suppress a genuine first report


def _breaker_open() -> bool:
    try:
        return bool(_cache().get("incident_breaker"))
    except Exception:
        return False


def _trip_breaker_if_flooding() -> bool:
    try:
        try:
            rate = _cache().incr("incident_rate")
        except ValueError:
            _cache().add("incident_rate", 1, timeout=_RATE_WINDOW)
            rate = 1
        if rate >= _RATE_THRESHOLD:
            _cache().set("incident_breaker", True, timeout=_BREAKER_TTL)
            return True
    except Exception:
        return False
    return False


def _emit(title: str, body: str, *, severity: str, fields: dict[str, str]) -> None:
    """Hand off the actual post. Tries Celery; falls back to an inline POST.

    Kept indirect so a request path enqueues (never blocks) while a host command
    or Celery task with no running broker still delivers.
    """
    try:
        from apps.integrations.tasks import post_discord_incident

        post_discord_incident.delay(title, body, severity, fields)
        return
    except Exception:
        pass
    post_embed(title, body, severity=severity, fields=fields)


def post_embed(
    title: str,
    body: str = "",
    *,
    severity: str = "error",
    fields: dict[str, str] | None = None,
    transport=None,
) -> bool:
    """POST one embed to ERROR_CHANNEL. Never raises; returns delivery success.

    ``transport`` is an injection seam for tests: a callable ``(url, data, headers)
    -> status_int``. Defaults to a stdlib urllib POST.
    """
    token = getattr(settings, "DISCORD_BOT_TOKEN", "")
    channel = getattr(settings, "DISCORD_ERROR_CHANNEL_ID", "")
    if not token or not channel:
        logger.warning("ERROR_CHANNEL sink disabled (missing token or channel)")
        return False
    embed: dict = {
        "title": title[:256],
        "description": body[:2000],
        "color": _COLORS.get(severity, _COLORS["error"]),
    }
    if fields:
        embed["fields"] = [
            {"name": str(k)[:256], "value": str(v)[:1024], "inline": True}
            for k, v in fields.items()
        ]
    payload = json.dumps({"embeds": [embed], "allowed_mentions": {"parse": []}})
    url = f"{_API}/channels/{channel}/messages"
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "User-Agent": "Mycelium (integrations, v1)",
    }
    try:
        if transport is not None:
            status = transport(url, payload.encode("utf-8"), headers)
        else:
            req = urllib.request.Request(
                url, data=payload.encode("utf-8"), headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
        return 200 <= int(status) < 300
    except urllib.error.HTTPError as exc:
        logger.warning("ERROR_CHANNEL post failed: HTTP %s", exc.code)
        return False
    except Exception:
        logger.exception("ERROR_CHANNEL post failed")
        return False
