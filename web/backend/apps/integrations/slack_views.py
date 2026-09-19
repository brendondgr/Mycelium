"""Slack's HTTP surface (ambient Plan 11), mounted under /api/integrations/slack/.

- ``events`` and ``interactions`` are called by Slack. They answer 404 while
  ``SLACK_ENABLED`` is off, refuse any request whose signature does not verify,
  and otherwise acknowledge quickly: the slow part, reading a DM as a dialogue
  turn, happens off the request.
- ``install`` and ``oauth/callback`` are the workspace install. It is
  browser-driven, for a signed-in user, with a session-bound ``state`` (the
  Discord flow's own helper).
- ``link-code`` (a person) and ``lab-code`` (a lab manager) issue the codes
  that carry Mycelium authority into Slack. ``status`` says what is linked.
  ``unlink`` drops a person's identity. ``listening`` is a lab manager's
  switch for the workspace.
"""

from __future__ import annotations

import json
import urllib.parse

from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import slack_events, slack_link, slack_resolve

_SCOPES = ",".join(
    [
        "channels:history",
        "groups:history",
        "im:history",
        "chat:write",
        "im:write",
    ]
)


def _enabled() -> bool:
    return bool(getattr(settings, "SLACK_ENABLED", False))


def _verified(request) -> bool:
    return slack_events.verify(
        timestamp=request.headers.get("X-Slack-Request-Timestamp", ""),
        signature=request.headers.get("X-Slack-Signature", ""),
        body=request.body,
    )


@method_decorator(csrf_exempt, name="dispatch")
class SlackEventsView(View):
    def post(self, request):
        if not _enabled():
            raise Http404
        if not _verified(request):
            return HttpResponse(status=401)
        try:
            payload = json.loads(request.body.decode() or "{}")
        except ValueError:
            return HttpResponse(status=400)
        if payload.get("type") == "url_verification":
            return JsonResponse({"challenge": payload.get("challenge", "")})
        if payload.get("type") == "event_callback":
            # Slack retries an event it thinks failed. One that was handled is
            # only acknowledged — a DM read twice could answer a second open
            # question — and one whose first attempt failed is handled now.
            # Taking a message twice is harmless (the ledger dedupes it).
            from django.core.cache import cache

            done = f"slack-event:{payload.get('event_id') or ''}"
            if payload.get("event_id") and cache.get(done):
                return HttpResponse(status=200)
            slack_events.handle_event(payload)
            if payload.get("event_id"):
                cache.set(done, 1, 24 * 3600)
        return HttpResponse(status=200)


@method_decorator(csrf_exempt, name="dispatch")
class SlackInteractionsView(View):
    def post(self, request):
        if not _enabled():
            raise Http404
        if not _verified(request):
            return HttpResponse(status=401)
        raw = request.POST.get("payload", "")
        try:
            payload = json.loads(raw or "{}")
        except ValueError:
            return HttpResponse(status=400)
        slack_events.handle_interaction(payload)
        return HttpResponse(status=200)


class SlackInstallView(APIView):
    """Send a signed-in user to Slack's install screen."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .services import state

        if not _enabled() or not settings.SLACK_CLIENT_ID:
            raise Http404
        if not request.session.session_key:
            request.session.save()
        nonce = state.issue_state(
            request.session.session_key, {"flow": "slack_install"}
        )
        query = urllib.parse.urlencode(
            {
                "client_id": settings.SLACK_CLIENT_ID,
                "scope": _SCOPES,
                "state": nonce,
                "redirect_uri": _redirect_uri(request),
            }
        )
        return HttpResponseRedirect(f"https://slack.com/oauth/v2/authorize?{query}")


def _redirect_uri(request) -> str:
    return request.build_absolute_uri("/api/integrations/slack/oauth/callback")


class SlackOAuthCallbackView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .services import slack_api, state

        if not _enabled():
            raise Http404
        payload = state.consume_state(
            request.GET.get("state", ""), request.session.session_key or ""
        )
        if payload is None or payload.get("flow") != "slack_install":
            return Response(
                {"detail": "invalid state"}, status=status.HTTP_400_BAD_REQUEST
            )
        code = request.GET.get("code", "")
        if not code:
            return HttpResponseRedirect("/app/profile?slack=cancelled")
        try:
            body = slack_api.oauth_access(
                code,
                client_id=settings.SLACK_CLIENT_ID,
                client_secret=settings.SLACK_CLIENT_SECRET,
                redirect_uri=_redirect_uri(request),
            )
        except slack_api.SlackError:
            return HttpResponseRedirect("/app/profile?slack=failed")
        team = body.get("team") or {}
        slack_resolve.install_workspace(
            team_id=str(team.get("id") or ""),
            name=str(team.get("name") or ""),
            bot_token=str(body.get("access_token") or ""),
            bot_user_id=str(body.get("bot_user_id") or ""),
            installed_by=request.user,
        )
        return HttpResponseRedirect("/app/profile?slack=installed")


class SlackLinkCodeView(APIView):
    """A code the signed-in person DMs to Mylo in Slack to link themselves."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _enabled():
            raise Http404
        return Response(
            {
                "code": slack_link.issue(user=request.user),
                "expires_in": int(settings.SLACK_LINK_CODE_MINUTES) * 60,
            }
        )


def _managed_lab(request):
    from .services import resolve

    slug = request.data.get("lab") or request.GET.get("lab") or ""
    lab = resolve.get_lab_by_slug(slug) if slug else None
    if lab is None or not resolve.web_user_can_manage_lab(request.user, lab):
        return None
    return lab


class SlackLabCodeView(APIView):
    """A lab manager's code: mention Mylo with it in the channel for reports."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _enabled():
            raise Http404
        lab = _managed_lab(request)
        if lab is None:
            return Response(status=status.HTTP_403_FORBIDDEN)
        return Response(
            {
                "code": slack_link.issue(user=request.user, lab=lab),
                "expires_in": int(settings.SLACK_LINK_CODE_MINUTES) * 60,
            }
        )


class SlackStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.ambient.service import workspace_source

        identities = slack_resolve.identities_for(request.user)
        names = slack_resolve.team_names()
        lab = _managed_lab(request)
        workspace = slack_resolve.workspace_for_lab(lab) if lab else None
        source = workspace_source(workspace.team_id) if workspace else None
        return Response(
            {
                "enabled": _enabled(),
                "installable": _enabled() and bool(settings.SLACK_CLIENT_ID),
                "identities": [
                    {
                        "team_id": i.team_id,
                        "team": names.get(i.team_id, ""),
                        "linked_at": i.linked_at,
                    }
                    for i in identities
                ],
                "lab_workspace": (
                    {
                        "team_id": workspace.team_id,
                        "name": workspace.name,
                        "has_channel": bool(workspace.updates_channel_id),
                        "listening": bool(source and source.listening),
                        "primary": workspace.reports_primary,
                    }
                    if workspace
                    else None
                ),
            }
        )


class SlackUnlinkView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        team_id = str(request.data.get("team_id") or "")
        return Response({"unlinked": slack_resolve.unlink(request.user, team_id)})


class SlackListeningView(APIView):
    """A lab manager's switches for the lab's workspace: ``on`` (listening)
    and ``primary`` (the lab's posts go to Slack rather than Discord)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.ambient.service import set_workspace_listening

        if not _enabled():
            raise Http404
        lab = _managed_lab(request)
        if lab is None:
            return Response(status=status.HTTP_403_FORBIDDEN)
        workspace = slack_resolve.workspace_for_lab(lab)
        if workspace is None:
            return Response(
                {"detail": "Link a Slack workspace to this lab first."},
                status=status.HTTP_409_CONFLICT,
            )
        out = {}
        if "on" in request.data:
            out.update(
                set_workspace_listening(
                    workspace.team_id,
                    on=bool(request.data.get("on")),
                    changed_by=request.user,
                    lab=lab,
                )
            )
        if "primary" in request.data:
            # Where the lab's posts go when it is on both platforms (rule 15).
            slack_resolve.set_reports_primary(workspace, request.data.get("primary"))
        out["primary"] = workspace.reports_primary
        return Response(out)
