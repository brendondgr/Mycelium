"""HTTP surface for the Discord integration (all under /api/integrations/discord/).

Two audiences:

* **Portal, authenticated (session + CSRF):** start a link, read status, issue a
  Path B code, disconnect, start a guild install. JSON in/out.
* **Discord browser redirects (GET callbacks):** the OAuth code lands here. These
  are AllowAny + rely on the SameSite=Lax session cookie for the user's identity;
  they redirect back into the portal on success and return a status code on a
  client error (tampered state → 400, snowflake/guild already bound → 409) so the
  behaviour is testable.

No model is imported here — every DB touch goes through ``services.resolve``. Slash
commands (``/activate``, ``/activate-lab``, ``/setup``, ``/mylo status``) are NOT
here; they are delivered over the Mylo gateway (mylo/bot), which calls the same
services.
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponseRedirect
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import DiscordGuildStatusSerializer, DiscordStatusSerializer
from .services import audit, discord_api, oauth, resolve, state
from .services.state import StateBackendError


def _return(outcome: str) -> HttpResponseRedirect:
    sep = "&" if "?" in settings.DISCORD_PORTAL_RETURN_URL else "?"
    return HttpResponseRedirect(
        f"{settings.DISCORD_PORTAL_RETURN_URL}{sep}discord={outcome}"
    )


def _session_key(request) -> str:
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key or ""


def _enqueue_probe(identity_id: int) -> None:
    try:
        from .tasks import probe_identity

        probe_identity.delay(identity_id)
    except Exception:
        # No broker (e.g. tests / host command): run inline, best-effort.
        try:
            from .services import probe

            identity = resolve.get_identity(identity_id)
            if identity is not None:
                probe.run_probe(identity)
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Path A — user OAuth link
# --------------------------------------------------------------------------- #
class DiscordStartView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            nonce = state.issue_state(_session_key(request), {"kind": "user"})
        except StateBackendError:
            return Response(
                {"detail": "link temporarily unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        audit.discord_audit(action="discord.link.oauth_started", actor=request.user)
        return Response({"authorize_url": oauth.user_authorize_url(nonce)})


class DiscordCallbackView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        if not request.user.is_authenticated:
            return _return("login_required")

        payload = state.consume_state(
            request.GET.get("state", ""), request.session.session_key or ""
        )
        if payload is None:
            return Response(
                {"detail": "invalid state"}, status=status.HTTP_400_BAD_REQUEST
            )
        code = request.GET.get("code", "")
        if not code:
            return Response(
                {"detail": "missing code"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            identity = oauth.complete_user_link(request.user, code, actor=request.user)
        except resolve.IdentityConflict:
            return Response(
                {"detail": "This Discord account is already linked to another "
                 "Mycelium user."},
                status=status.HTTP_409_CONFLICT,
            )
        except discord_api.DiscordHTTPError:
            from .services import errors

            errors.note_incident("oauth", "exchange_failed")
            return _return("error")

        _enqueue_probe(identity.id)
        return _return("linked")


# --------------------------------------------------------------------------- #
# Status + disconnect
# --------------------------------------------------------------------------- #
class DiscordStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        identity = resolve.get_identity_for_user(request.user)
        if identity is None:
            return Response(DiscordStatusSerializer.empty())
        return Response(DiscordStatusSerializer(identity).data)


class DiscordProbeView(APIView):
    """Re-run the DM reachability probe on demand ("Test" button on the card).

    Synchronous (not the Celery path) so the portal gets the fresh result to
    render. Returns the same status shape as ``DiscordStatusView`` with the
    updated ``dm_ok``/``dm_checked_at``. A transient Discord failure leaves the
    prior value; ``404`` if the caller has no linked identity.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        identity = resolve.get_identity_for_user(request.user)
        if identity is None:
            return Response(
                {"detail": "not linked"}, status=status.HTTP_404_NOT_FOUND
            )
        from .services import probe

        probe.run_probe(identity)
        identity = resolve.get_identity_for_user(request.user)
        return Response(DiscordStatusSerializer(identity).data)


class DiscordDisconnectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tokens = resolve.pop_identity_tokens_and_delete(request.user)
        for key in ("access_token", "refresh_token"):
            tok = tokens.get(key)
            if tok:
                try:
                    discord_api.revoke_token(tok)
                except Exception:
                    pass
        return Response({"detail": "disconnected"})


# --------------------------------------------------------------------------- #
# Path B — issue an activation code
# --------------------------------------------------------------------------- #
class DiscordActivationCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .services import activation

        code = activation.issue_code(request.user)
        return Response(
            {
                "code": code,
                "expires_in": settings.DISCORD_ACTIVATION_TTL_SECONDS,
                "activation_channel": settings.DISCORD_ACTIVATION_CHANNEL_ID or None,
            }
        )


# --------------------------------------------------------------------------- #
# Path C — guild install
# --------------------------------------------------------------------------- #
def _manager_lab_or_error(request):
    """Resolve ?lab=<slug> and enforce lab-manager authority.

    Returns ``(lab, None)`` on success or ``(None, Response)`` with the right
    status (404 unknown lab, 403 not a manager) — the same gate the guild
    install uses, so read and write share one authority check.
    """
    slug = request.GET.get("lab", "")
    lab = resolve.get_lab_by_slug(slug) if slug else None
    if lab is None:
        return None, Response(
            {"detail": "unknown lab"}, status=status.HTTP_404_NOT_FOUND
        )
    if not resolve.web_user_can_manage_lab(request.user, lab):
        return None, Response(
            {"detail": "not a manager of this lab"},
            status=status.HTTP_403_FORBIDDEN,
        )
    return lab, None


class DiscordLabActivationCodeView(APIView):
    """Issue a 10-digit lab activation code (the website half of `/activate-lab`).

    Manager-only (the same ``?lab=<slug>`` authority gate the guild install uses).
    The code is shown once; only its sha256 is stored. Redeemed in Discord via
    ``/activate-lab code:`` to bind that server to this lab.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        lab, error = _manager_lab_or_error(request)
        if error is not None:
            return error
        from .services import lab_activation

        code = lab_activation.issue_code(request.user, lab)
        return Response(
            {"code": code, "expires_in": settings.DISCORD_ACTIVATION_TTL_SECONDS}
        )


class DiscordGuildStatusView(APIView):
    """Is this Lab's Discord server synced? Drives the Manage & Invite badge."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        lab, error = _manager_lab_or_error(request)
        if error is not None:
            return error
        link = resolve.get_guild_link_for_lab(lab)
        if link is None:
            return Response(DiscordGuildStatusSerializer.empty())
        return Response(DiscordGuildStatusSerializer(link).data)


class DiscordGuildStartView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        lab, error = _manager_lab_or_error(request)
        if error is not None:
            return error
        # D-6 guard: an installer should already be linked, so someone can claim
        # the guild afterward — otherwise it can sit in PENDING_SETUP forever.
        if resolve.get_identity_for_user(request.user) is None:
            return Response(
                {"detail": "link your own Discord account first",
                 "code": "link_required"},
                status=status.HTTP_409_CONFLICT,
            )
        try:
            nonce = state.issue_state(
                _session_key(request),
                {"kind": "guild", "lab_id": str(lab.id), "user_id": request.user.id},
            )
        except StateBackendError:
            return Response(
                {"detail": "install temporarily unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"authorize_url": oauth.guild_authorize_url(nonce)})


class DiscordGuildCallbackView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        payload = state.consume_state(
            request.GET.get("state", ""), request.session.session_key or ""
        )
        if payload is None or payload.get("kind") != "guild":
            return Response(
                {"detail": "invalid state"}, status=status.HTTP_400_BAD_REQUEST
            )
        code = request.GET.get("code", "")
        if not code:
            return Response(
                {"detail": "missing code"}, status=status.HTTP_400_BAD_REQUEST
            )
        lab = resolve.get_lab_by_id(payload.get("lab_id"))
        if lab is None:
            return Response(
                {"detail": "unknown lab"}, status=status.HTTP_400_BAD_REQUEST
            )
        installer = resolve.get_user_by_id(payload.get("user_id"))
        try:
            oauth.complete_guild_link(lab, code, installed_by=installer)
        except oauth.BotServerRequired:
            # The lab has no Mylo-server add-on — bounce back with an upgrade cue.
            return _return("bot_server_required")
        except resolve.GuildConflict:
            return Response(
                {"detail": "This server is already linked to another lab."},
                status=status.HTTP_409_CONFLICT,
            )
        except (ValueError, discord_api.DiscordHTTPError):
            from .services import errors

            errors.note_incident("guild", "install_failed")
            return _return("install_error")
        return _return("installed")
