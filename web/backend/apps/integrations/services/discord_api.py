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
import uuid
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


def get_guild_channels(guild_id: str) -> list[dict]:
    """The bot's view of a guild's channels (for the reminder channel picker)."""
    resp = _request(
        "GET", f"/guilds/{guild_id}/channels", auth=("Bot", _bot_token())
    )
    if resp.status != 200:
        raise DiscordHTTPError(resp.status, _err_code(resp.json))
    return resp.json.get("_list", [])


def get_guild_roles(guild_id: str) -> list[dict]:
    """The guild's roles, for the alert mention picker."""
    resp = _request("GET", f"/guilds/{guild_id}/roles", auth=("Bot", _bot_token()))
    if resp.status != 200:
        raise DiscordHTTPError(resp.status, _err_code(resp.json))
    return resp.json.get("_list", [])


def get_guild_members(guild_id: str, *, limit: int = 200) -> list[dict]:
    """The guild's members, for the alert mention picker.

    Needs the **Server Members** privileged intent to be enabled for the
    application; without it Discord answers 403 and the caller degrades to an
    empty list with a reason rather than pretending the server has no members.

    ``limit`` is Discord's own page size (max 1000). A single page is taken
    deliberately: this feeds a picker a human scrolls, and paginating a whole
    large guild into one API response would trade a lot of latency for names
    nobody is going to scroll to.
    """
    resp = _request(
        "GET",
        f"/guilds/{guild_id}/members?limit={int(limit)}",
        auth=("Bot", _bot_token()),
    )
    if resp.status != 200:
        raise DiscordHTTPError(resp.status, _err_code(resp.json))
    return resp.json.get("_list", [])


def open_dm_raw(recipient_id: str) -> RawResponse:
    return _request(
        "POST",
        "/users/@me/channels",
        auth=("Bot", _bot_token()),
        json_body={"recipient_id": str(recipient_id)},
    )


#: Discord caps ``nonce`` at 25 characters (documented on Create Message).
NONCE_MAX_LENGTH = 25


def _nonce_fields(nonce: str) -> dict:
    """``nonce`` + ``enforce_nonce`` for an idempotent retry, if one was supplied.

    With ``enforce_nonce`` set, Discord checks the nonce for uniqueness over the last
    few minutes and, if this author already sent a message carrying it, returns *that*
    message instead of creating a second one. That is what makes retrying a send whose
    response we never saw safe rather than a coin flip.

    A nonce longer than the documented limit is dropped rather than sent: an
    over-length value would be rejected by Discord, turning a recoverable retry into a
    hard failure — worse than simply losing the deduplication.
    """
    if not nonce or len(nonce) > NONCE_MAX_LENGTH:
        return {}
    return {"nonce": nonce, "enforce_nonce": True}


def create_message(
    channel_id: str,
    *,
    content: str = "",
    embed: dict | None = None,
    allowed_mentions: dict | None = None,
    nonce: str = "",
    components: list | None = None,
):
    """Post a message. ``parse`` is ``[]`` unless a human explicitly asked otherwise.

    ``parse: []`` is the default and it is structural, not stylistic: reminder
    bodies interpolate *scraped third-party text*, and a conference title
    containing ``@everyone`` must never ping a server from a trusted bot.
    Callers pass explicit ``users`` / ``roles`` id lists to ping specific
    members (``<@id>`` in the body then resolves); ids cannot be forged out of
    scraped text, so those never widen what a scrape can do.

    ``@everyone`` is the one thing that has no id, so it can only be expressed
    as a parse category. It is therefore gated on an explicit
    ``allowed_mentions["everyone"]`` from the caller, which
    :mod:`tools.delivery.reminders_discord` sets only when a lab manager chose it
    for that alert. Scraped text stays escaped either way
    (``escape_mentions``), so even with the category enabled the ping can only
    come from the operator's own choice and never from ingested content.

    The bot additionally needs the **Mention Everyone** permission in the guild;
    without it Discord accepts the message and simply does not ping, which is
    the right failure — the reminder still arrives.

    ``nonce`` opts into Discord-side deduplication — see :func:`_nonce_fields`.
    """
    mentions: dict = {"parse": []}
    if allowed_mentions:
        if allowed_mentions.get("users"):
            mentions["users"] = [str(u) for u in allowed_mentions["users"]]
        if allowed_mentions.get("roles"):
            mentions["roles"] = [str(r) for r in allowed_mentions["roles"]]
        if allowed_mentions.get("everyone"):
            mentions["parse"] = ["everyone"]
    body: dict = {"allowed_mentions": mentions, **_nonce_fields(nonce)}
    if content:
        body["content"] = content
    if embed:
        body["embeds"] = [embed]
    if components:
        body["components"] = components
    return _request(
        "POST",
        f"/channels/{channel_id}/messages",
        auth=("Bot", _bot_token()),
        json_body=body,
    )


def _mentions(allowed_mentions: dict | None) -> dict:
    """The same ``parse: []`` rule as :func:`create_message`: only named users."""
    mentions: dict = {"parse": []}
    if allowed_mentions and allowed_mentions.get("users"):
        mentions["users"] = [str(u) for u in allowed_mentions["users"]]
    return mentions


def _message_body(content, embed, components, allowed_mentions) -> dict:
    body: dict = {"allowed_mentions": _mentions(allowed_mentions)}
    if content:
        body["content"] = content
    if embed:
        body["embeds"] = [embed]
    if components is not None:
        body["components"] = components
    return body


def create_forum_thread(
    forum_id: str,
    *,
    name: str,
    applied_tags: list[str] | None = None,
    content: str = "",
    embed: dict | None = None,
    components: list | None = None,
    allowed_mentions: dict | None = None,
) -> RawResponse:
    """Start a thread in a forum channel; its opening post is the message. The
    response is the thread (a channel), whose ``id`` is also the post's id."""
    body = {
        "name": name[:100],
        "message": _message_body(content, embed, components, allowed_mentions),
    }
    if applied_tags:
        body["applied_tags"] = [str(t) for t in applied_tags][:5]
    return _request(
        "POST",
        f"/channels/{forum_id}/threads",
        auth=("Bot", _bot_token()),
        json_body=body,
    )


def edit_message(
    channel_id: str,
    message_id: str,
    *,
    content: str | None = None,
    embed: dict | None = None,
    components: list | None = None,
    allowed_mentions: dict | None = None,
) -> RawResponse:
    body = _message_body(content, embed, components, allowed_mentions)
    if content == "":
        body["content"] = ""
    return _request(
        "PATCH",
        f"/channels/{channel_id}/messages/{message_id}",
        auth=("Bot", _bot_token()),
        json_body=body,
    )


def modify_channel(channel_id: str, fields: dict) -> RawResponse:
    """PATCH a channel or thread: ``name``, ``applied_tags``, ``archived``,
    ``available_tags``, ``default_sort_order`` and so on."""
    return _request(
        "PATCH",
        f"/channels/{channel_id}",
        auth=("Bot", _bot_token()),
        json_body=fields,
    )


def delete_channel(channel_id: str) -> RawResponse:
    return _request("DELETE", f"/channels/{channel_id}", auth=("Bot", _bot_token()))


def get_channel(channel_id: str) -> RawResponse:
    return _request("GET", f"/channels/{channel_id}", auth=("Bot", _bot_token()))


def create_guild_channel(guild_id: str, fields: dict) -> RawResponse:
    return _request(
        "POST",
        f"/guilds/{guild_id}/channels",
        auth=("Bot", _bot_token()),
        json_body=fields,
    )


def set_permission_overwrite(
    channel_id: str, overwrite_id: str, *, kind: int, allow: int, deny: int
) -> RawResponse:
    """``kind`` 0 = role, 1 = member."""
    return _request(
        "PUT",
        f"/channels/{channel_id}/permissions/{overwrite_id}",
        auth=("Bot", _bot_token()),
        json_body={"type": kind, "allow": str(allow), "deny": str(deny)},
    )


def create_message_with_attachment(
    channel_id: str,
    *,
    filename: str,
    file_bytes: bytes,
    content: str = "",
    embed: dict | None = None,
    allowed_mentions: dict | None = None,
    file_content_type: str = "application/pdf",
    nonce: str = "",
):
    """Post a message with a single file attachment (``multipart/form-data``).

    ``parse`` is **unconditionally** ``[]`` here, unlike :func:`create_message`,
    which now takes an explicit ``everyone`` opt-in. This variant carries the
    daily report and lab digest PDFs — scheduled, unattended posts nobody chose
    per-send — and there is no product reason for one to ping a whole server.
    The body may interpolate scraped titles, so the mention parse categories stay
    empty regardless of what is passed. The file is sent as ``files[0]`` and declared
    in ``attachments[0]`` (id 0), the pairing Discord requires. Used for the daily
    "Mylo Report" PDF DM.
    """
    mentions: dict = {"parse": []}
    if allowed_mentions:
        if allowed_mentions.get("users"):
            mentions["users"] = [str(u) for u in allowed_mentions["users"]]
        if allowed_mentions.get("roles"):
            mentions["roles"] = [str(r) for r in allowed_mentions["roles"]]
    payload: dict = {
        "allowed_mentions": mentions,
        "attachments": [{"id": 0, "filename": filename}],
        **_nonce_fields(nonce),
    }
    if content:
        payload["content"] = content
    if embed:
        payload["embeds"] = [embed]
    body, content_type = _multipart_body(
        payload, filename, file_bytes, file_content_type
    )
    return _request(
        "POST",
        f"/channels/{channel_id}/messages",
        auth=("Bot", _bot_token()),
        raw_body=body,
        content_type=content_type,
    )


def _multipart_body(
    payload: dict, filename: str, file_bytes: bytes, file_content_type: str
) -> tuple[bytes, str]:
    """Build a two-part multipart body: a ``payload_json`` field + one file part."""
    boundary = "----mycelium" + uuid.uuid4().hex
    bnd = boundary.encode("ascii")
    crlf = b"\r\n"
    safe_name = filename.replace('"', "").replace("\r", "").replace("\n", "")
    file_disposition = (
        f'Content-Disposition: form-data; name="files[0]"; filename="{safe_name}"'
    )
    parts = [
        b"--" + bnd + crlf,
        b'Content-Disposition: form-data; name="payload_json"' + crlf,
        b"Content-Type: application/json" + crlf + crlf,
        json.dumps(payload).encode("utf-8") + crlf,
        b"--" + bnd + crlf,
        file_disposition.encode("utf-8") + crlf,
        f"Content-Type: {file_content_type}".encode("ascii") + crlf + crlf,
        file_bytes,
        crlf,
        b"--" + bnd + b"--" + crlf,
    ]
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


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
