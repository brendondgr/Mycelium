"""Thin Bot Framework Connector client (stdlib urllib): send an activity into
a conversation Mylo already has a reference to (ambient Plan 11)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


class TeamsError(Exception):
    def __init__(self, error: str, status: int = 0):
        super().__init__(error)
        self.error = error
        self.status = status

    @property
    def permanent(self) -> bool:
        return self.status in (400, 401, 403, 404)


#: Where the Bot Framework's service URLs live. The bot token is never sent
#: anywhere else, whatever an activity claims.
_SERVICE_HOSTS = ("trafficmanager.net", "botframework.com", "teams.microsoft.com")


def trusted_service_url(service_url: str) -> bool:
    parts = urllib.parse.urlsplit(service_url or "")
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(
        host == suffix or host.endswith("." + suffix) for suffix in _SERVICE_HOSTS
    )


def send_activity(
    service_url: str, conversation_id: str, *, token: str, text: str, attachments=None
) -> str:
    if not trusted_service_url(service_url):
        raise TeamsError("untrusted_service_url", 400)
    url = (
        f"{service_url.rstrip('/')}/v3/conversations/"
        f"{urllib.parse.quote(conversation_id, safe='')}/activities"
    )
    body = {"type": "message", "text": text}
    if attachments:
        body["attachments"] = attachments
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            return str(json.loads(response.read().decode() or "{}").get("id") or "")
    except urllib.error.HTTPError as exc:
        raise TeamsError(f"http_{exc.code}", exc.code) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise TeamsError("unreachable", 0) from exc
