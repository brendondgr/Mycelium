"""Teams' HTTP surface (ambient Plan 11), under /api/integrations/teams/.

- ``messages`` is the Bot Framework messaging endpoint. It answers 404 while
  ``TEAMS_ENABLED`` is off, 401 unless the bearer token verifies, and
  otherwise acknowledges at once; the dialogue reading runs off the request.
- ``link-code`` / ``lab-code`` issue codes good on Teams only. ``status`` says
  what is linked. ``lab`` holds a lab manager's switches for the team
  (``on``: listening; ``primary``: the lab's posts go to Teams).
"""

from __future__ import annotations

import json

from django.conf import settings
from django.http import Http404, HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import capabilities as caps

from .services import slack_link, teams_auth, teams_events, teams_resolve


def _enabled() -> bool:
    return bool(getattr(settings, "TEAMS_ENABLED", False))


@method_decorator(csrf_exempt, name="dispatch")
class TeamsMessagesView(View):
    def post(self, request):
        if not _enabled():
            raise Http404
        try:
            activity = json.loads(request.body.decode() or "{}")
        except ValueError:
            return HttpResponse(status=400)
        try:
            teams_auth.verify(
                request.headers.get("Authorization", ""),
                service_url=str(activity.get("serviceUrl") or ""),
            )
        except teams_auth.InvalidToken:
            return HttpResponse(status=401)
        teams_events.handle_activity(activity)
        return HttpResponse(status=200)


def _managed_lab(request):
    from .services import resolve

    slug = request.data.get("lab") or request.GET.get("lab") or ""
    lab = resolve.get_lab_by_slug(slug) if slug else None
    if lab is None or not resolve.web_user_can_manage_lab(request.user, lab):
        return None
    return lab


class TeamsLinkCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _enabled():
            raise Http404
        return Response(
            {
                "code": slack_link.issue(user=request.user, platform="teams"),
                "expires_in": int(settings.SLACK_LINK_CODE_MINUTES) * 60,
            }
        )


class TeamsLabCodeView(APIView):
    capabilities = {"POST": caps.SERVERS_MANAGE}

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _enabled():
            raise Http404
        lab = _managed_lab(request)
        if lab is None:
            return Response(status=status.HTTP_403_FORBIDDEN)
        return Response(
            {
                "code": slack_link.issue(user=request.user, lab=lab, platform="teams"),
                "expires_in": int(settings.SLACK_LINK_CODE_MINUTES) * 60,
            }
        )


class TeamsStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.ambient.service import team_source

        lab = _managed_lab(request)
        link = teams_resolve.link_for_lab(lab) if lab else None
        source = team_source(link.team_id) if link else None
        return Response(
            {
                "enabled": _enabled(),
                "identities": [
                    {"tenant_id": i.tenant_id, "linked_at": i.linked_at}
                    for i in teams_resolve.identities_for(request.user)
                ],
                "lab_team": (
                    {
                        "team_id": link.team_id,
                        "name": link.name,
                        "has_channel": bool(link.updates_conversation_id),
                        "listening": bool(source and source.listening),
                        "primary": link.reports_primary,
                    }
                    if link
                    else None
                ),
            }
        )


class TeamsUnlinkView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tenant_id = str(request.data.get("tenant_id") or "")
        return Response({"unlinked": teams_resolve.unlink(request.user, tenant_id)})


class TeamsLabView(APIView):
    capabilities = {"POST": caps.SERVERS_MANAGE}

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.ambient.service import set_team_listening

        if not _enabled():
            raise Http404
        lab = _managed_lab(request)
        if lab is None:
            return Response(status=status.HTTP_403_FORBIDDEN)
        link = teams_resolve.link_for_lab(lab)
        if link is None:
            return Response(
                {"detail": "Link a Teams team to this lab first."},
                status=status.HTTP_409_CONFLICT,
            )
        out = {}
        if "on" in request.data:
            out.update(
                set_team_listening(
                    link.team_id,
                    on=bool(request.data.get("on")),
                    changed_by=request.user,
                    lab=lab,
                )
            )
        if "primary" in request.data:
            teams_resolve.set_reports_primary(link, request.data.get("primary"))
        out["primary"] = link.reports_primary
        return Response(out)
