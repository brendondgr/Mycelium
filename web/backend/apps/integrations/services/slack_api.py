"""Thin Slack Web API client (stdlib urllib), like ``discord_api``.

Only the calls Mylo makes: post a message, open a DM, update a message, and
exchange an OAuth code at install. Every call returns the parsed body or
raises :class:`SlackError` with Slack's own error string, which the outbox
classifies (retry on rate limits and server errors, give up on auth errors).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

_API = "https://slack.com/api"

#: Errors a retry cannot fix.
PERMANENT = frozenset(
    {
        "invalid_auth",
        "account_inactive",
        "token_revoked",
        "not_authed",
        "channel_not_found",
        "not_in_channel",
        "is_archived",
        "user_not_found",
        "cannot_dm_bot",
        "invalid_blocks",
        "msg_too_long",
    }
)


class SlackError(Exception):
    def __init__(self, error: str, status: int = 200):
        super().__init__(error)
        self.error = error
        self.status = status

    @property
    def permanent(self) -> bool:
        return self.error in PERMANENT


def _call(
    method: str, *, token: str = "", payload: dict | None = None, form=None
) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    else:
        data = json.dumps(payload or {}).encode()
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = urllib.request.Request(f"{_API}/{method}", data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            body = json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        raise SlackError(
            "ratelimited" if exc.code == 429 else f"http_{exc.code}", exc.code
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SlackError("unreachable", 0) from exc
    if not body.get("ok"):
        raise SlackError(str(body.get("error") or "unknown"))
    return body


def post_message(token: str, channel: str, *, text: str, blocks=None) -> str:
    """Post and return the message's ``ts``."""
    payload = {"channel": channel, "text": text, "unfurl_links": False}
    if blocks:
        payload["blocks"] = blocks
    return str(_call("chat.postMessage", token=token, payload=payload).get("ts") or "")


def update_message(
    token: str, channel: str, ts: str, *, text: str, blocks=None
) -> None:
    payload = {"channel": channel, "ts": ts, "text": text, "blocks": blocks or []}
    _call("chat.update", token=token, payload=payload)


def open_dm(token: str, slack_user_id: str) -> str:
    body = _call("conversations.open", token=token, payload={"users": slack_user_id})
    return str((body.get("channel") or {}).get("id") or "")


def oauth_access(
    code: str, *, client_id: str, client_secret: str, redirect_uri: str
) -> dict:
    return _call(
        "oauth.v2.access",
        form={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
    )
