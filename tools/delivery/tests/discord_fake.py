"""A fake Discord REST API for the announcement tests.

Not named ``test_*`` so pytest treats this as a helper module, not a suite.
"""

from __future__ import annotations

import itertools

import pytest
from apps.integrations.services import discord_api
from apps.integrations.services.discord_api import RawResponse

_ids = itertools.count(9_000_000_000_000_000)


class FakeDiscord:
    """Enough of Discord's REST API for these flows, recording every call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self.threads: dict[str, dict] = {}

    def __call__(self, method, path, *, auth=None, json_body=None, **_kw):
        self.calls.append((method, path, json_body))
        if path == "/users/@me/channels":
            return RawResponse(200, {"id": "dm-chan"})
        if method == "POST" and path.endswith("/threads"):
            tid = str(next(_ids))
            self.threads[tid] = dict(json_body or {})
            return RawResponse(201, {"id": tid, "available_tags": []})
        if method == "GET" and path.startswith("/channels/"):
            return RawResponse(
                200, {"id": path.split("/")[2], "type": 15, "available_tags": []}
            )
        if method == "PATCH" and path.count("/") == 2:
            tags = (json_body or {}).get("available_tags")
            if tags is not None:
                return RawResponse(
                    200,
                    {
                        "available_tags": [
                            {**t, "id": t.get("id") or f"tag-{t['name']}"} for t in tags
                        ]
                    },
                )
            return RawResponse(200, {})
        if method == "POST" and path == "/guilds/g1/channels":
            body = json_body or {}
            out = {"id": str(next(_ids)), **body}
            if body.get("available_tags"):
                out["available_tags"] = [
                    {**t, "id": f"tag-{t['name']}"} for t in body["available_tags"]
                ]
            return RawResponse(201, out)
        if method == "PUT":
            return RawResponse(204, {})
        if method == "DELETE":
            return RawResponse(204, {})
        return RawResponse(200, {"id": str(next(_ids))})

    def paths(self, method):
        return [p for m, p, _b in self.calls if m == method]


@pytest.fixture
def fake(monkeypatch, settings):
    settings.DISCORD_BOT_TOKEN = "test-token"
    settings.CACHES = {
        name: {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": f"ann-{name}",
        }
        for name in ("default", "search", "scan", "discord")
    }
    from django.core.cache import caches

    for name in settings.CACHES:  # the gate's rate counters live here
        caches[name].clear()
    transport = FakeDiscord()
    monkeypatch.setattr(discord_api, "_request", transport)
    return transport
