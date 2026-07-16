"""Shared test config for the Discord integration.

The real ``discord`` cache is Redis; tests swap every cache to LocMem so nonce and
lockout logic runs without a broker, and pin the Discord app credentials so flow
code has something to build URLs / auth headers from. Real Discord HTTP is always
mocked (patch ``apps.integrations.services.discord_api``), so no test touches the
network.
"""

from __future__ import annotations

from django.core.cache import caches
from django.test import override_settings

_LOCMEM = {
    name: {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": f"test-{name}",
    }
    for name in ("default", "search", "scan", "discord")
}

discord_test_settings = override_settings(
    CACHES=_LOCMEM,
    DISCORD_CLIENT_ID="test-client-id",
    DISCORD_CLIENT_SECRET="test-client-secret",
    DISCORD_BOT_TOKEN="test-bot-token",
    DISCORD_APP_ID="test-app-id",
    DISCORD_ERROR_CHANNEL_ID="999000",
    DISCORD_TOKEN_ENC_KEY="",  # derive from SECRET_KEY
    DISCORD_OAUTH_REDIRECT_URI="http://testserver/api/integrations/discord/callback",
    DISCORD_GUILD_REDIRECT_URI=(
        "http://testserver/api/integrations/discord/guild-callback"
    ),
    DISCORD_PORTAL_RETURN_URL="http://testserver/app/profile",
)


def clear_discord_cache() -> None:
    for name in _LOCMEM:
        caches[name].clear()
