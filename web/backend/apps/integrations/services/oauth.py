"""OAuth flow orchestration for Path A (user link) and Path C (guild install).

Pure of the ORM and of Django's request object: builds authorize URLs, performs the
server-side code exchange, reads the authoritative identity/guild from Discord, and
binds through ``resolve``. Views own the ``state`` nonce and the HTTP redirects.

Path A grants DM rights via ``applications.commands`` under ``integration_type=1``
(USER_INSTALL) — no shared server needed. Path C uses the code-grant bot install
(``response_type=code`` + ``integration_require_code_grant`` ON): the binding comes
only from the ``guild`` object in the token-exchange response; the redirect's
``guild_id``/``permissions`` are forgeable hints and are ignored entirely.
"""

from __future__ import annotations

import urllib.parse
from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.utils import timezone

from . import discord_api, resolve

if TYPE_CHECKING:  # annotations only — never imported at runtime (boundary rule)
    from ..models import DiscordIdentity

_AUTHORIZE = "https://discord.com/oauth2/authorize"
_USER_SCOPES = ["identify", "applications.commands"]
_GUILD_SCOPES = ["bot", "applications.commands"]

# Paths of the two callback views (apps.integrations.urls). Kept here as constants
# rather than reversed, because they are also half of a redirect_uri that Discord
# matches byte-for-byte — the no-slash form is the canonical registered one.
USER_CALLBACK_PATH = "/api/integrations/discord/callback"
GUILD_CALLBACK_PATH = "/api/integrations/discord/guild-callback"


def user_redirect_uri(request=None) -> str:
    return _redirect_uri(request, settings.DISCORD_OAUTH_REDIRECT_URI,
                         USER_CALLBACK_PATH)


def guild_redirect_uri(request=None) -> str:
    return _redirect_uri(request, settings.DISCORD_GUILD_REDIRECT_URI,
                         GUILD_CALLBACK_PATH)


def _redirect_uri(request, pinned: str, path: str) -> str:
    """Where Discord sends the browser back — the origin it is already on.

    OAuth2 requires an absolute redirect_uri, so this cannot be a relative link;
    deriving it from the live request is the equivalent, and keeps a deployment
    from having to name its own hostname twice. ``request.get_host()`` is already
    validated against ALLOWED_HOSTS, so a forged Host header cannot point the
    callback at someone else's origin (don't set ALLOWED_HOSTS to "*").

    An explicit setting wins, for stacks that must pin one registered origin, and
    the configured base URL is the fallback when there is no request at all.
    """
    if pinned:
        return pinned
    if request is not None:
        return request.build_absolute_uri(path)
    return f"{settings.DISCORD_APP_BASE_URL}{path}"


class BotServerRequired(Exception):
    """Raised when installing Mylo into a guild for a lab without the add-on.

    ``BOT_SERVER`` is granted by a :class:`~apps.billing.models.SubscriptionAddOn`
    on the lab (or its department), never by a tier — so the invite is refused
    with an upgrade prompt rather than silently joining the server.
    """

    def __init__(self, lab):
        self.lab = lab
        slug = getattr(lab, "slug", lab)
        super().__init__(f"lab {slug} lacks the Mylo-server add-on")


def user_authorize_url(state: str, *, request=None) -> str:
    params = {
        "client_id": settings.DISCORD_CLIENT_ID,
        "response_type": "code",
        "scope": " ".join(_USER_SCOPES),
        "integration_type": 1,  # USER_INSTALL — grants DM rights
        "redirect_uri": user_redirect_uri(request),
        "state": state,
        "prompt": "consent",
    }
    return f"{_AUTHORIZE}?{urllib.parse.urlencode(params)}"


def guild_authorize_url(state: str, *, request=None) -> str:
    params = {
        "client_id": settings.DISCORD_CLIENT_ID,
        "response_type": "code",  # NOT the callback-less bot flow
        "scope": " ".join(_GUILD_SCOPES),
        "permissions": settings.DISCORD_INSTALL_PERMISSIONS,
        "integration_type": 0,  # GUILD_INSTALL
        "redirect_uri": guild_redirect_uri(request),
        "state": state,
    }
    return f"{_AUTHORIZE}?{urllib.parse.urlencode(params)}"


def complete_user_link(user, code: str, *, actor=None, request=None) -> DiscordIdentity:
    """Exchange the code, read the authoritative snowflake, bind the identity.

    The exchange must repeat the same redirect_uri the authorize step sent. It is
    rebuilt from ``request`` rather than remembered: Discord only ever redirects
    the browser to the URI we handed it, so the callback arrives on that very
    origin and rebuilding there yields the identical string.

    Raises ``resolve.IdentityConflict`` if the snowflake belongs to another user,
    ``discord_api.DiscordHTTPError`` on any Discord failure.
    """
    token = discord_api.exchange_code(code, user_redirect_uri(request))
    profile = discord_api.get_current_user(token["access_token"])

    return resolve.bind_identity(
        user,
        profile["id"],  # authoritative — never a user-supplied username
        method=resolve.LINK_OAUTH,
        scopes=_scopes_from(token),
        tokens={
            "access_token": token.get("access_token", ""),
            "refresh_token": token.get("refresh_token", ""),
            "expires_at": _expires_at(token),
        },
        username=profile.get("username", ""),
        global_name=profile.get("global_name", "") or "",
        actor=actor or user,
    )


def complete_guild_link(lab, code: str, *, installed_by=None, request=None):
    """Exchange the code and bind the guild from the authoritative ``guild`` object.

    Raises ``resolve.GuildConflict`` if the guild/lab is already otherwise bound,
    ``discord_api.DiscordHTTPError`` on a Discord failure, or ``ValueError`` if the
    exchange returned no guild (code grant not actually completed).
    """
    # The Mylo-server capability is an add-on on the lab's subscription (A4); a lab
    # without it may not have the bot join its guild.
    from apps.billing.entitlements import Feature, lab_has_feature

    if not lab_has_feature(lab, Feature.BOT_SERVER):
        raise BotServerRequired(lab)

    token = discord_api.exchange_code(code, guild_redirect_uri(request))
    guild = token.get("guild")
    if not guild or not guild.get("id"):
        raise ValueError("token exchange returned no guild object")
    link = resolve.bind_guild(lab, guild, installed_by=installed_by)
    _post_setup_nudge(guild)
    return link


def _post_setup_nudge(guild: dict) -> None:
    """Best-effort: post the 'run /activate-lab' nudge to the guild system channel."""
    channel_id = guild.get("system_channel_id")
    if not channel_id:
        return
    try:
        discord_api.create_message(
            str(channel_id),
            embed={
                "title": "Mylo joined this server",
                "description": (
                    "To connect this server to your Mycelium lab, a lab lead clicks "
                    "**Activate Lab** in the lab's settings for a code, then runs "
                    "`/activate-lab code:<code>` here."
                ),
                "color": 0x5E7A3E,
            },
        )
    except Exception:  # never let a missing-permission nudge fail the install
        pass


def refresh_identity(identity: DiscordIdentity) -> bool:
    """Refresh an identity's OAuth tokens. Returns False on invalid_grant (revoked)."""
    try:
        token = discord_api.refresh_access_token(identity.refresh_token)
    except discord_api.DiscordHTTPError as exc:
        if exc.status in (400, 401):  # invalid_grant — the user deauthorized us
            resolve.mark_identity_revoked(identity.discord_user_id)
            return False
        raise
    resolve.update_identity_tokens(
        identity,
        access_token=token.get("access_token", ""),
        refresh_token=token.get("refresh_token", identity.refresh_token),
        expires_at=_expires_at(token),
    )
    return True


def _scopes_from(token: dict) -> list[str]:
    scope = token.get("scope") or ""
    return [s for s in scope.split(" ") if s]


def _expires_at(token: dict):
    seconds = token.get("expires_in")
    if not seconds:
        return None
    return timezone.now() + timedelta(seconds=int(seconds))
