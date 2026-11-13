"""The public demo's door: ``/api/demo/<x>`` is ``/api/<x>``, as the demo viewer.

The demo is not a second backend. A request under :data:`PREFIX` is rewritten
onto the ordinary route and served by the ordinary view, with ``request.user``
set to the demo world's viewer — so every permission check, serializer and
query the app relies on applies unchanged, and the viewer can see only what a
member of the demo lab and department can see.

What this door adds is three refusals and one budget:

* **Off means absent.** With ``demo.enabled`` off, or no world built, every
  demo route answers 404 — an off demo does not advertise itself.
* **Read-only, deny by default.** ``GET``/``HEAD``/``OPTIONS`` pass. Any other
  method is refused with ``403 demo_read_only`` unless its route is in
  :data:`WRITE_ALLOWED` (asking Mylo). A route added to the app later is
  refused here until someone deliberately allows it; a test sweeps every URL
  pattern to hold that.
* **No identity leaks either way.** The visitor never gets a login: the
  viewer is set per request, the visitor's own session (if they have one) is
  swapped out for the request and put back untouched, and an
  ``Authorization`` header is dropped so no other authenticator can win.
* Mylo's question budget is spent in the agent's message route
  (``apps.demo.budget``); this door only identifies the visitor, by a random id
  in a signed cookie, and their network address, by a keyed hash.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from importlib import import_module

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.urls import Resolver404, resolve

from . import world as demo_world

PREFIX = "/api/demo/"
STATUS = ("status", "status/")
VISITOR_COOKIE = "mycelium_demo_v"
VISITOR_SALT = "apps.demo.visitor"
VISITOR_MAX_AGE = 60 * 60 * 24 * 365
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

#: (method, route) pairs a demo visitor may write to, routes as Django names
#: them with any trailing slash removed. Everything else unsafe is refused.
WRITE_ALLOWED = frozenset(
    {
        ("POST", "api/tools/agent/threads"),
        ("POST", "api/tools/agent/threads/<uuid:thread_id>/messages"),
        ("POST", "api/tools/agent/threads/<uuid:thread_id>/answer"),
        ("POST", "api/tools/agent/threads/<uuid:thread_id>/cancel"),
    }
)

#: Route prefixes refused whatever the method: signing in or out, the account's
#: own secrets, and the staff surfaces.
ALWAYS_REFUSED = (
    "api/auth/login",
    "api/auth/logout",
    "api/auth/register",
    "api/auth/password",
    "api/auth/email",
    "api/admin",
)

#: ``detail`` first: the app's form errors show the first string they find.
READ_ONLY = {
    "detail": "This is a demo, so nothing here can be changed.",
    "fix": "Sign up to do this in a workspace of your own.",
    "code": "demo_read_only",
}


@dataclass(frozen=True)
class DemoContext:
    """Who is looking: the visitor's cookie id and a keyed hash of their address."""

    visitor: str
    ip_hash: str
    world: object


def client_ip(request) -> str:
    """The visitor's address as the front door saw it.

    The one rule every per-client control uses
    (:func:`apps.accounts.client_ip.client_ip`): the hop nginx set. A
    ``CF-Connecting-IP`` or left-most ``X-Forwarded-For`` is whatever the client
    typed, and reading it let one visitor be a new visitor on every request.
    """
    from apps.accounts.client_ip import client_ip as _client_ip

    return _client_ip(request)


def ip_hash(ip: str) -> str:
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, f"demo-ip:{ip}".encode(), hashlib.sha256).hexdigest()[:32]


def _visitor(request) -> tuple[str, bool]:
    """The visitor's id from the signed cookie, or a new one (and ``True``)."""
    value = request.get_signed_cookie(VISITOR_COOKIE, default=None, salt=VISITOR_SALT)
    if value and len(value) <= 64:
        return value, False
    return secrets.token_urlsafe(18), True


def _set_visitor(response, visitor: str) -> None:
    response.set_signed_cookie(
        VISITOR_COOKIE,
        visitor,
        salt=VISITOR_SALT,
        max_age=VISITOR_MAX_AGE,
        # "/" rather than /api/demo/: the server render of a /demo page
        # forwards the browser's cookies to /api/demo/auth/me/, and must name
        # the same visitor the browser's own calls do.
        path="/",
        httponly=True,
        samesite="Lax",
        secure=bool(getattr(settings, "SESSION_COOKIE_SECURE", False)),
    )


def _not_found() -> JsonResponse:
    return JsonResponse({"detail": "Not found."}, status=404)


def _throttled(ip_key: str) -> bool:
    """A fixed one-hour window per address (``DEFAULT_THROTTLE_RATES['demo']``)."""
    rate = settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {}).get("demo")
    if not rate:
        return False
    try:
        limit = int(str(rate).split("/")[0])
    except ValueError:
        return False
    key = f"demo-throttle:{ip_key}"
    count = cache.get_or_set(key, 0, timeout=3600)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=3600)
        count = 1
    return count > limit


def refusal_for(method: str, route: str) -> dict | None:
    """Why the demo refuses ``method`` on ``route`` (a Django route pattern),
    or ``None`` when it lets it through. Pure, so the sweep test can call it."""
    route = route.rstrip("/")
    if any(route == p or route.startswith(p + "/") for p in ALWAYS_REFUSED):
        return READ_ONLY
    if method in SAFE_METHODS:
        return None
    if (method, route) in WRITE_ALLOWED:
        return None
    return READ_ONLY


class DemoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        if not (path.startswith(PREFIX) or path == PREFIX.rstrip("/")):
            return self.get_response(request)
        if not demo_world.is_enabled():
            return _not_found()
        world = demo_world.current_world()
        if world is None:
            return _not_found()

        rest = path[len(PREFIX) :]
        visitor, new_visitor = _visitor(request)
        ctx = DemoContext(
            visitor=visitor, ip_hash=ip_hash(client_ip(request)), world=world
        )

        if rest in STATUS:
            response = self._status(ctx)
        elif _throttled(ctx.ip_hash):
            response = JsonResponse(
                {
                    "code": "demo_throttled",
                    "detail": "Too many requests. Wait a minute.",
                },
                status=429,
            )
        else:
            response = self._through(request, "/api/" + rest, ctx)
        if new_visitor:
            _set_visitor(response, visitor)
        return response

    def _status(self, ctx) -> JsonResponse:
        from . import budget

        world = ctx.world
        return JsonResponse(
            {
                "enabled": True,
                "lab": world.lab.slug,
                "entry": f"/demo/overview?ws={world.lab.slug}",
                **budget.summary(ctx),
            }
        )

    def _through(self, request, target: str, ctx: DemoContext):
        try:
            match = resolve(target)
        except Resolver404:
            # What APPEND_SLASH would do, which it cannot here: the demo prefix
            # is not in the URLconf, so CommonMiddleware never sees a match.
            if target.endswith("/"):
                return _not_found()
            target += "/"
            try:
                match = resolve(target)
            except Resolver404:
                return _not_found()
        why = refusal_for(request.method, match.route)
        if why is not None:
            return JsonResponse(why, status=403)

        request.path_info = target
        request.META.pop("HTTP_AUTHORIZATION", None)
        own_session = getattr(request, "session", None)
        request.session = import_module(settings.SESSION_ENGINE).SessionStore()
        request.user = ctx.world.viewer
        request._cached_user = ctx.world.viewer
        request.demo = ctx
        try:
            return self.get_response(request)
        finally:
            # SessionMiddleware runs after us on the way out: hand it back the
            # visitor's own session, unread and unmodified, so it neither saves
            # nor deletes their cookie.
            if own_session is not None:
                request.session = own_session
