"""Thin Discord REST client (stdlib urllib).

Only the calls this scope needs: the OAuth token exchange/refresh/revoke, the
authoritative ``/users/@me`` lookup, the DM reachability probe (open DM + post),
and the bot's guild list for reconciliation. No third-party HTTP dependency — these
are a handful of simple synchronous calls made from Celery tasks and request views.

Two error surfaces on purpose:

* Token/identity calls (``exchange_code``, ``get_current_user`` …) raise
  ``DiscordHTTPError`` on any non-2xx — the caller cannot proceed without them.
* ``create_message`` / ``open_dm_raw`` return the raw ``(status, json, retry_after)``
  so the reachability probe can branch on 200 / 403+50007 / 429 / 5xx per the plan.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from django.conf import settings

_API = "https://discord.com/api/v10"
_UA = "Mycelium (integrations, v1)"
_TIMEOUT = 15


class DiscordHTTPError(RuntimeError):
    def __init__(self, status: int, code: int | None = None, body: str = ""):
        self.status = status
        self.code = code
        self.body = body
        super().__init__(f"Discord HTTP {status} (code={code})")


@dataclass
class RawResponse:
    status: int
    json: dict
    retry_after: float | None = None


# --------------------------------------------------------------------------- #
# OAuth token endpoints (client-credential authenticated in the form body)
# --------------------------------------------------------------------------- #
def exchange_code(code: str, redirect_uri: str) -> dict:
    return _post_token(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }
    )


def refresh_access_token(refresh_token: str) -> dict:
    return _post_token(
        {"grant_type": "refresh_token", "refresh_token": refresh_token}
    )


def revoke_token(token: str) -> bool:
    try:
        _post_form(
            "/oauth2/token/revoke",
            {
                "client_id": settings.DISCORD_CLIENT_ID,
                "client_secret": settings.DISCORD_CLIENT_SECRET,
                "token": token,
            },
        )
        return True
    except DiscordHTTPError:
        return False


def _post_token(extra: dict) -> dict:
    data = {
        "client_id": settings.DISCORD_CLIENT_ID,
        "client_secret": settings.DISCORD_CLIENT_SECRET,
        **extra,
    }
    return _post_form("/oauth2/token", data)


# --------------------------------------------------------------------------- #
# Identity + guild (bearer / bot authenticated)
# --------------------------------------------------------------------------- #
def get_current_user(access_token: str) -> dict:
    """Authoritative snowflake for a bearer token. Never trust a supplied name."""
    resp = _request("GET", "/users/@me", auth=("Bearer", access_token))
    if resp.status != 200:
        raise DiscordHTTPError(resp.status, _err_code(resp.json))
    return resp.json


def get_bot_guilds() -> list[dict]:
    resp = _request("GET", "/users/@me/guilds", auth=("Bot", _bot_token()))
    if resp.status != 200:
        raise DiscordHTTPError(resp.status, _err_code(resp.json))
    # `json` is a list here; _request stashes list bodies under {"_list": [...]}.
    return resp.json.get("_list", [])


def open_dm_raw(recipient_id: str) -> RawResponse:
    return _request(
        "POST",
        "/users/@me/channels",
        auth=("Bot", _bot_token()),
        json_body={"recipient_id": str(recipient_id)},
    )


def create_message(
    channel_id: str,
    *,
    content: str = "",
    embed: dict | None = None,
    allowed_mentions: dict | None = None,
):
    """Post a message. ``allowed_mentions.parse`` is **always forced to ``[]``**.

    ``parse: []`` is non-negotiable and structural: reminder bodies interpolate
    *scraped third-party text*, and a title containing ``@everyone`` must never ping
    the server from a trusted bot. Callers may pass explicit ``users`` / ``roles`` id
    lists to ping specific members (``<@id>`` in the body then resolves), but the
    parse categories stay empty regardless of what is passed.
    """
    mentions: dict = {"parse": []}
    if allowed_mentions:
        if allowed_mentions.get("users"):
            mentions["users"] = [str(u) for u in allowed_mentions["users"]]
        if allowed_mentions.get("roles"):
            mentions["roles"] = [str(r) for r in allowed_mentions["roles"]]
    body: dict = {"allowed_mentions": mentions}
    if content:
        body["content"] = content
    if embed:
        body["embeds"] = [embed]
    return _request(
        "POST",
        f"/channels/{channel_id}/messages",
        auth=("Bot", _bot_token()),
        json_body=body,
    )


def _bot_token() -> str:
    token = getattr(settings, "DISCORD_BOT_TOKEN", "")
    if not token:
        raise DiscordHTTPError(0, None, "bot token not configured")
    return token


# --------------------------------------------------------------------------- #
# Transport
# --------------------------------------------------------------------------- #
def _post_form(path: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode("utf-8")
    resp = _request(
        "POST",
        path,
        raw_body=body,
        content_type="application/x-www-form-urlencoded",
    )
    if not (200 <= resp.status < 300):
        raise DiscordHTTPError(resp.status, _err_code(resp.json), json.dumps(resp.json))
    return resp.json


def _request(
    method: str,
    path: str,
    *,
    auth: tuple[str, str] | None = None,
    json_body: dict | None = None,
    raw_body: bytes | None = None,
    content_type: str = "application/json",
) -> RawResponse:
    """One HTTP round-trip. Returns status+json; only raises on transport failure."""
    url = _API + path
    headers = {"User-Agent": _UA, "Accept": "application/json"}
    if auth:
        headers["Authorization"] = f"{auth[0]} {auth[1]}"
    data = raw_body
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = content_type
    elif raw_body is not None:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return _parse(resp.status, resp.read(), resp.headers)
    except urllib.error.HTTPError as exc:
        return _parse(exc.code, exc.read(), exc.headers)
    except Exception as exc:  # DNS/timeout/connection — no HTTP status at all.
        raise DiscordHTTPError(0, None, str(exc)) from exc


def _parse(status: int, raw: bytes, headers) -> RawResponse:
    parsed: dict = {}
    if raw:
        try:
            loaded = json.loads(raw.decode("utf-8"))
            parsed = loaded if isinstance(loaded, dict) else {"_list": loaded}
        except ValueError:
            parsed = {}
    retry_after = None
    if status == 429:
        retry_after = parsed.get("retry_after")
        if retry_after is None and headers is not None:
            hdr = headers.get("Retry-After")
            retry_after = float(hdr) if hdr else None
    return RawResponse(status=status, json=parsed, retry_after=retry_after)


def _err_code(body: dict) -> int | None:
    code = body.get("code") if isinstance(body, dict) else None
    return int(code) if isinstance(code, int) else None
