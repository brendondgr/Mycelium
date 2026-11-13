"""``GET api/admin/setup-status/``: what a new instance still needs, from real checks.

The first admin lands on an empty overview. This answers the "Getting started"
checklist there, one fact per step, each read from the thing itself rather than
from a flag someone could forget to set:

- ``model``: the default model server answers, or ``llm.enabled = false`` says
  the instance runs without one on purpose;
- ``collection``: the corpus holds items (per kind, so the page can show the
  first collection filling it), plus the last nightly run's outcome;
- ``profile``: the asking admin's own research interests are filled in;
- ``people``: anyone else has an account, or an invitation exists;
- ``discord``: optional; a Discord server has Mylo installed.

Staff-only and read-only. Collecting is started from the host (``make
nightly``), which is the one path that also runs the browser-based sources.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsStaffOrSuperuser

#: Written by the nightly runner on the host (mylo/runstate.py), visible here
#: through the bind-mounted data/ directory.
RUN_STATE_PATH = (
    Path(settings.BASE_DIR).parent.parent / "data" / "logs" / "mylo-last-run.json"
)

CONTENT_KINDS = ("paper", "grant", "conference", "fellowship")


def _model(app_label: str, name: str):
    """A model by label, or None when its app (a tool) is not installed."""
    try:
        return apps.get_model(app_label, name)
    except LookupError:
        return None


def model_status() -> dict:
    if not getattr(settings, "LLM_ENABLED", True):
        return {"state": "skipped", "detail": "llm.enabled = false"}
    from apps.core import llm_servers

    try:
        table = llm_servers.table()
        answers, reason = llm_servers.health(table.default)
    except Exception as exc:  # noqa: BLE001 - the checklist never errors on this
        return {"state": "todo", "detail": f"{type(exc).__name__}: {exc}"}
    server = table.servers.get(table.default) or {}
    if not server.get("model"):
        return {"state": "todo", "detail": "no model is named (LLM_MODEL in .env)"}
    if answers:
        return {"state": "done", "detail": f"{server.get('model')} on {table.default}"}
    return {"state": "todo", "detail": reason or "the model server does not answer"}


def collection_status() -> dict:
    counts = {kind: 0 for kind in CONTENT_KINDS}
    item = _model("content", "ContentItem")
    if item is not None:
        rows = item.objects.values("type").order_by().annotate(n=Count("id"))
        for row in rows:
            if row["type"] in counts:
                counts[row["type"]] = row["n"]
    total = sum(counts.values())
    last_run = None
    try:
        state = json.loads(RUN_STATE_PATH.read_text(encoding="utf-8"))
        last_run = {
            "finished_at": state.get("finished_at"),
            "ok": bool(state.get("ok")),
        }
    except (OSError, ValueError):
        pass
    return {
        "state": "done" if total else "todo",
        "counts": counts,
        "total": total,
        "last_run": last_run,
        "command": "make nightly",
    }


def profile_status(user) -> dict:
    profile = getattr(user, "profile", None)
    interests = getattr(profile, "interests", None) or {}
    if isinstance(interests, dict):
        filled = any(bool(value) for value in interests.values())
    else:
        filled = bool(interests)
    return {"state": "done" if filled else "todo"}


def people_status(user) -> dict:
    others = get_user_model().objects.exclude(pk=user.pk).count()
    invite = _model("accounts", "OrgInvite")
    invites = invite.objects.count() if invite is not None else 0
    return {"state": "done" if others or invites else "todo",
            "users": others + 1, "invites": invites}


def discord_status() -> dict:
    guild = _model("integrations", "DiscordGuildLink")
    servers = guild.objects.count() if guild is not None else 0
    return {
        "state": "done" if servers else "optional",
        "servers": servers,
        "bot_configured": bool(getattr(settings, "DISCORD_BOT_TOKEN", "")),
    }


class SetupStatusView(APIView):
    """The Getting started checklist's facts, for staff."""

    permission_classes = [IsStaffOrSuperuser]

    def get(self, request: Request) -> Response:
        steps = {
            "model": model_status(),
            "collection": collection_status(),
            "profile": profile_status(request.user),
            "people": people_status(request.user),
            "discord": discord_status(),
        }
        required = ("model", "collection", "profile", "people")
        complete = all(steps[key]["state"] in ("done", "skipped") for key in required)
        return Response({"steps": steps, "complete": complete})
