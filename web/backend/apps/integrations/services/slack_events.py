"""Slack's Events API and interactivity, verified and dispatched (Plan 11).

Every request is verified before a byte of it is read as data: Slack signs
``v0:<timestamp>:<body>`` with the app's signing secret (HMAC-SHA256), and a
request older than ``SLACK_REQUEST_MAX_AGE_SECONDS`` is refused so a captured
request cannot be replayed.

What each event does:

- a message in a channel the app is in → the ledger, through
  ``apps.ambient.service.slack_heard`` (the same filters, eligibility and
  buffer as Discord). A mention of Mylo carrying a lab link code binds the
  workspace to that lab and makes the channel its updates channel;
- a DM to Mylo → a person link code binds that Slack user, anything else goes
  to the ledger and then, off the request, to the Plan 06 dialogue;
- an edit or a deletion → reconciled, like Discord's;
- the app uninstalled or its tokens revoked → the workspace stops listening
  and its buffer is purged;
- a button press on one of Mylo's questions → the answer, and the question's
  message replaced by Mylo's reply.

``app_mention`` is ignored: the ``message`` event already carries every
mention, and taking both would record a mention twice.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import UTC, datetime

from django.conf import settings

logger = logging.getLogger(__name__)

#: Message subtypes that are ordinary messages. Everything else — joins,
#: topic changes, bot_add — is not conversation.
_MESSAGE_SUBTYPES = {None, "", "thread_broadcast", "file_share", "me_message"}


def verify(
    *, timestamp: str, signature: str, body: bytes, now: float | None = None
) -> bool:
    secret = str(getattr(settings, "SLACK_SIGNING_SECRET", "") or "")
    if not secret or not timestamp or not signature:
        return False
    try:
        age = abs((now or time.time()) - int(timestamp))
    except ValueError:
        return False
    if age > int(settings.SLACK_REQUEST_MAX_AGE_SECONDS):
        return False
    base = b"v0:" + timestamp.encode() + b":" + body
    expected = "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _sent_at(ts: str):
    try:
        return datetime.fromtimestamp(float(ts), tz=UTC)
    except (TypeError, ValueError):
        return datetime.now(tz=UTC)


def _mentions(text: str) -> list[str]:
    import re

    return re.findall(r"<@([A-Z0-9]+)(?:\|[^>]*)?>", text or "")


def handle_event(payload: dict) -> dict:
    """One ``event_callback``. Returns a small summary (for logs and tests)."""
    from apps.ambient import service

    from ..models import SlackWorkspace
    from . import slack_link, slack_outbox

    team_id = str(payload.get("team_id") or "")
    event = payload.get("event") or {}
    kind = event.get("type")
    workspace = SlackWorkspace.objects.filter(team_id=team_id, active=True).first()

    if kind in ("app_uninstalled", "tokens_revoked"):
        if workspace is not None:
            workspace.active = False
            workspace.save(update_fields=["active", "updated_at"])
        service.slack_workspace_removed(team_id)
        return {"handled": "removed"}
    if kind != "message" or workspace is None:
        return {"handled": "ignored"}

    channel = str(event.get("channel") or "")
    is_dm = event.get("channel_type") == "im"
    subtype = event.get("subtype")

    if subtype == "message_changed":
        message = event.get("message") or {}
        service.slack_edited(
            team_id,
            channel,
            str(message.get("ts") or ""),
            message.get("text") or "",
            is_dm=is_dm,
        )
        return {"handled": "edited"}
    if subtype == "message_deleted":
        ts = str(
            event.get("deleted_ts")
            or (event.get("previous_message") or {}).get("ts")
            or ""
        )
        service.slack_deleted(team_id, channel, ts, is_dm=is_dm)
        return {"handled": "deleted"}
    if subtype not in _MESSAGE_SUBTYPES and subtype != "bot_message":
        return {"handled": "ignored"}

    user = str(event.get("user") or "")
    text = event.get("text") or ""
    ts = str(event.get("ts") or "")
    from_mylo = bool(workspace.bot_user_id) and user == workspace.bot_user_id
    is_bot = bool(event.get("bot_id")) or subtype == "bot_message"
    mentioned = _mentions(text)
    to_mylo = bool(workspace.bot_user_id) and workspace.bot_user_id in mentioned

    code = slack_link.find_code(text) if not from_mylo else None
    if code and is_dm:
        result = slack_link.redeem_person(code, team_id=team_id, slack_user_id=user)
        reply = (
            "Linked — this Slack account is now yours on Mycelium. Turn listening on "
            "in Mylo & you if you want Mylo to learn from your conversations here."
            if result.ok
            else "That code didn't work — it may have expired. Make a new one on "
            "your Mycelium profile."
        )
        slack_outbox.enqueue_reply(
            team_id=team_id,
            channel_id=channel,
            dedupe_key=f"slack-link:{channel}:{ts}",
            kind="slack_link",
            text=reply,
        )
        return {"handled": "link_person", "ok": result.ok}
    if code and to_mylo:
        result = slack_link.redeem_lab(code, team_id=team_id, channel_id=channel)
        reply = (
            "Linked to the lab — its Mylo reports will be posted in this channel."
            if result.ok
            else "That lab code didn't work — a lab manager can make a new one in the "
            "lab's settings."
        )
        slack_outbox.enqueue_reply(
            team_id=team_id,
            channel_id=channel,
            dedupe_key=f"slack-lab-link:{channel}:{ts}",
            kind="slack_link",
            text=reply,
        )
        return {"handled": "link_lab", "ok": result.ok}

    heard = service.slack_heard(
        team_id=team_id,
        channel_id=channel,
        ts=ts,
        text=text,
        sent_at=_sent_at(ts),
        slack_user_id=user,
        is_dm=is_dm,
        is_bot=is_bot and not from_mylo,
        from_mylo=from_mylo,
        explicit=is_dm or to_mylo,
        mention_user_ids=[one for one in mentioned if one != workspace.bot_user_id],
        thread_ts=str(event.get("thread_ts") or ""),
        attachment_urls=[
            f.get("url_private")
            for f in (event.get("files") or [])
            if f.get("url_private")
        ],
    )
    if is_dm and not from_mylo and not is_bot:
        from ..tasks import slack_dialogue

        slack_dialogue.delay(team_id, user, channel, ts, text)
    return {"handled": "heard", "stored": bool(heard.stored), "reason": heard.reason}


def dialogue(
    team_id: str, slack_user_id: str, channel_id: str, ts: str, text: str
) -> str:
    """Off the request: read the DM as a dialogue turn and queue the reply."""
    from apps.ambient import service

    from . import slack_outbox

    reply = service.slack_dialogue_turn(team_id, slack_user_id, text)
    if reply:
        slack_outbox.enqueue_reply(
            team_id=team_id,
            channel_id=channel_id,
            dedupe_key=f"slack-dialogue:{channel_id}:{ts}",
            kind="ambient_reply",
            text=reply,
        )
    return reply


def handle_interaction(payload: dict, *, respond=None) -> str:
    """A Block Kit button press. Only ``ambient:<id>:<choice>`` is Mylo's."""
    from apps.ambient import service

    team_id = str((payload.get("team") or {}).get("id") or "")
    slack_user_id = str((payload.get("user") or {}).get("id") or "")
    actions = payload.get("actions") or []
    if payload.get("type") != "block_actions" or not actions:
        return ""
    action_id = str(actions[0].get("action_id") or "")
    prefix, _, rest = action_id.partition(":")
    suggestion_id, _, choice = rest.partition(":")
    if prefix != "ambient" or not suggestion_id or not choice:
        return ""
    line = service.slack_answer_button(team_id, slack_user_id, suggestion_id, choice)
    response_url = str(payload.get("response_url") or "")
    if response_url and line:
        (respond or _respond)(response_url, line)
    return line


def _respond(response_url: str, text: str) -> None:
    """Replace the question's message with Mylo's reply (buttons gone)."""
    import urllib.request

    if not response_url.startswith("https://hooks.slack.com/"):
        return  # never post anywhere but Slack's own response endpoint
    body = json.dumps({"replace_original": True, "text": text}).encode()
    request = urllib.request.Request(
        response_url, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(request, timeout=5).read()  # noqa: S310
    except Exception:  # noqa: BLE001 - the answer is recorded either way
        logger.warning("slack: could not replace the question message")
