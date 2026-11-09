"""The agent's API at ``api/tools/agent/`` (D-4). Backend only: no UI here.

Every view builds the caller through the web surface adapter and goes
through ``service``; no view decides access itself.
"""

from __future__ import annotations

from django.http import StreamingHttpResponse
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from . import refs, service
from .service import ServiceError
from .surfaces import web


def _error(exc: ServiceError) -> Response:
    return Response(exc.as_dict(), status=exc.status)


def _thread_json(t) -> dict:
    return {
        "id": str(t.pk),
        "title": t.title,
        "purpose": t.purpose,
        "state": t.state,
        "scope": t.scope_kind,
        "scope_ref": (
            t.scope_lab.slug
            if t.scope_lab_id
            else str(t.scope_department_id or t.scope_project_id or "") or None
        ),
        "archived": t.archived,
        "pinned": t.pinned,
        "parent": str(t.parent_id) if t.parent_id else None,
        "fork_seq": t.fork_seq,
        "created_at": t.created_at.isoformat(),
        "last_activity_at": t.last_activity_at.isoformat(),
        "anchor": (t.settings or {}).get("anchor"),
        "todos": (t.settings or {}).get("todos", []),
        "references": (t.settings or {}).get("refs", []),
    }


class _Base(APIView):
    def handle_exception(self, exc):
        if isinstance(exc, ServiceError):
            return _error(exc)
        return super().handle_exception(exc)

    def thread(self, request, thread_id):
        return service.get_thread(request.user, thread_id)


class StatusView(_Base):
    def get(self, request):
        return Response(service.status())


class CatalogView(_Base):
    def get(self, request):
        scope = service.scope_from(
            request.user,
            request.query_params.get("scope"),
            request.query_params.get("ref"),
        )
        return Response(
            {"functions": service.catalog_view(web.caller(request, scope=scope))}
        )


class ThreadsView(_Base):
    def get(self, request):
        rows = service.list_threads(
            request.user,
            q=request.query_params.get("q", ""),
            archived=request.query_params.get("archived") in ("1", "true"),
            anchor=request.query_params.get("anchor") or None,
        )
        return Response({"threads": [_thread_json(t) for t in rows]})

    def post(self, request):
        web.caller(request)  # verified email
        scope = service.scope_from(
            request.user, request.data.get("scope"), request.data.get("ref")
        )
        thread = service.create_thread(
            request.user,
            scope=scope,
            surface="web",
            title=str(request.data.get("title", "")),
            anchor=request.data.get("anchor") or None,
        )
        return Response(_thread_json(thread), status=201)


class ThreadView(_Base):
    def get(self, request, thread_id):
        return Response(_thread_json(self.thread(request, thread_id)))

    def patch(self, request, thread_id):
        thread = service.update_thread(
            request.user,
            thread_id,
            title=request.data.get("title"),
            archived=request.data.get("archived"),
            pinned=request.data.get("pinned"),
        )
        return Response(_thread_json(thread))

    def delete(self, request, thread_id):
        service.delete_thread(request.user, thread_id)
        return Response(status=204)


class MessagesView(_Base):
    def post(self, request, thread_id):
        thread = self.thread(request, thread_id)
        caller = web.caller(request, thread)
        attachments = list(request.FILES.getlist("files")) + [
            str(x)
            for x in (
                request.data.getlist("attachments")
                if hasattr(request.data, "getlist")
                else request.data.get("attachments") or []
            )
        ]
        mentions = (
            request.data.getlist("mentions")
            if hasattr(request.data, "getlist") and not isinstance(request.data, dict)
            else request.data.get("mentions") or []
        )
        steer = str(request.data.get("steer", "")).lower() in ("1", "true")
        out = service.send(
            caller,
            thread,
            str(request.data.get("text", "")),
            mentions=mentions,
            attachments=attachments,
            steer=steer,
        )
        return Response(out, status=202)


class AnswerView(_Base):
    def post(self, request, thread_id):
        thread = self.thread(request, thread_id)
        return Response(
            service.answer(
                web.caller(request, thread), thread, str(request.data.get("text", ""))
            ),
            status=202,
        )


class CancelView(_Base):
    def post(self, request, thread_id):
        thread = self.thread(request, thread_id)
        return Response(service.cancel(web.caller(request, thread), thread), status=202)


class ForkView(_Base):
    def post(self, request, thread_id):
        try:
            seq = int(request.data.get("seq"))
        except (TypeError, ValueError):
            raise ServiceError("bad_seq", "Say where to fork from (seq).") from None
        return Response(
            _thread_json(service.fork_thread(request.user, thread_id, seq)), status=201
        )


class EventsView(_Base):
    def get(self, request, thread_id):
        thread = self.thread(request, thread_id)
        try:
            after = int(request.query_params.get("after", 0))
        except ValueError:
            after = 0
        events = service.thread_events(
            web.caller(request, thread),
            thread,
            after=after,
            view=request.query_params.get("view", "activity"),
        )
        return Response({"events": events, "state": thread.state})


class _EventStream(BaseRenderer):
    """Lets a client that asks for ``text/event-stream`` (every browser
    stream does) through content negotiation. The stream itself is a plain
    ``StreamingHttpResponse``; this only ever renders an error body."""

    media_type = "text/event-stream"
    format = "sse"
    charset = "utf-8"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return JSONRenderer().render(data)


class StreamView(_Base):
    """Server-sent events: stored events after ``Last-Event-ID`` (or
    ``?after=``), then live ones. ``?once=1`` replays and closes;
    ``?until_idle=1`` closes once the turn has ended. ``?view=activity``
    (default) is what a person may see; ``?view=raw`` is staff-only."""

    renderer_classes = [JSONRenderer, _EventStream]

    def get(self, request, thread_id):
        from . import stream

        thread = self.thread(request, thread_id)
        caller = web.caller(request, thread)
        try:
            after = int(
                request.headers.get("Last-Event-ID")
                or request.query_params.get("after")
                or 0
            )
        except ValueError:
            after = 0
        once = request.query_params.get("once") in ("1", "true")
        follow = service.subscribe(
            caller,
            thread,
            after=after,
            follow_live=not once,
            stop_when_idle=request.query_params.get("until_idle") in ("1", "true"),
            view=request.query_params.get("view", "activity"),
        )
        response = StreamingHttpResponse(
            (stream.sse_format(m) for m in follow), content_type="text/event-stream"
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class ExportView(_Base):
    def get(self, request, thread_id):
        from django.http import HttpResponse

        thread = self.thread(request, thread_id)
        # ``as``, not ``format``: DRF claims ``?format=`` for its renderers.
        fmt = request.query_params.get("as", "json")
        caller = web.caller(request, thread)
        if fmt in ("md", "markdown"):
            response = HttpResponse(
                service.export(caller, thread, fmt="md"),
                content_type="text/markdown; charset=utf-8",
            )
            response["Content-Disposition"] = (
                'attachment; filename="mylo-conversation.md"'
            )
            return response
        return Response(service.export(caller, thread, fmt="json"))


class RefSearchView(_Base):
    def get(self, request):
        thread_id = request.query_params.get("thread")
        thread = self.thread(request, thread_id) if thread_id else None
        caller = web.caller(request, thread)
        kinds = [k for k in request.query_params.get("kinds", "").split(",") if k]
        q = request.query_params.get("q", "").strip()
        if not q:
            return Response({"results": []})
        found = refs.search(caller, q, kinds=kinds or None, limit=10)
        return Response(
            {
                "results": [
                    {"ref": i.ref, "kind": i.kind, "title": i.title, "card": i.card}
                    for i in found
                ]
            }
        )


class PreferencesView(_Base):
    def _json(self, pref):
        return {
            "chat_enabled": pref.chat_enabled,
            "learning": service.learning_enabled(pref.user),
            "discord_allowed": pref.discord_allowed,
            "groups_off": pref.groups_off,
        }

    def get(self, request):
        return Response(self._json(service.get_preferences(request.user)))

    def patch(self, request):
        pref = service.set_preferences(
            request.user,
            **{
                k: v
                for k, v in request.data.items()
                if k in ("chat_enabled", "learning", "discord_allowed", "groups_off")
            },
        )
        return Response(self._json(pref))


class PolicyView(_Base):
    def _org(self, kind, ref):
        from apps.accounts.models import Department, Lab

        if kind not in ("lab", "department"):
            raise ServiceError(
                "not_found", "Policies exist for labs and departments.", status=404
            )
        try:
            obj = (
                Lab.objects.filter(slug=ref).first()
                if kind == "lab"
                else Department.objects.filter(pk=ref).first()
            )
        except Exception:  # a malformed id is simply not found
            obj = None
        if obj is None:
            raise ServiceError("not_found", f"No such {kind}.", status=404)
        return obj

    def _json(self, policy, kind, org):
        # The host's ceiling is read-only here: a lab can only go below it.
        guests = {
            "discord_guests_ceiling": service.guest_ceiling(),
            "discord_guests_in_force": service.guest_level_in_force(kind, org),
        }
        if policy is None:
            return {
                "groups_off": [],
                "discord_channels_off": [],
                "max_risk": "read",
                "members_inform_org": True,
                "discord_guests": "full",
                **guests,
                "set": False,
            }
        return {
            "groups_off": policy.groups_off,
            "discord_channels_off": policy.discord_channels_off,
            "max_risk": policy.max_risk,
            "members_inform_org": policy.members_inform_org,
            "discord_guests": policy.discord_guests,
            **guests,
            "set": True,
        }

    def get(self, request, kind, ref):
        org = self._org(kind, ref)
        return Response(
            self._json(service.get_org_policy(request.user, kind, org), kind, org)
        )

    def patch(self, request, kind, ref):
        org = self._org(kind, ref)
        policy = service.set_org_policy(
            request.user,
            kind,
            org,
            **{
                k: v
                for k, v in request.data.items()
                if k
                in (
                    "groups_off",
                    "discord_channels_off",
                    "max_risk",
                    "members_inform_org",
                    "discord_guests",
                )
            },
        )
        return Response(self._json(policy, kind, org))
