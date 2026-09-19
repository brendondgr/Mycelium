"""Bot Framework activities from Teams, dispatched (ambient Plan 11, 6–8).

The endpoint has already verified the token (:mod:`.teams_auth`). Here:

- a message in a team channel → the ledger through
  ``apps.ambient.service.teams_heard``, the same gate as every platform. A
  mention of Mylo carrying a lab code binds the team to the lab, and the
  channel becomes the lab's updates conversation;
- a personal chat with Mylo → a person code links the person and remembers
  the chat, so Mylo can write to them later. An Adaptive Card choice answers
  a question. Anything else goes to the ledger and then, off the request, to
  the Plan 06 dialogue;
- edits and deletions → reconciled;
- the app installed in a team → the team is remembered; removed → it stops
  listening and its buffer is purged.

Group chats are not listened to: they are neither a team nor a person's chat
with Mylo, and nothing in Plan 02's consent model covers them.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime

_AT = re.compile(r"<at>.*?</at>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")


def plain(text: str) -> str:
    """Teams' message HTML as plain text, mentions removed."""
    return html.unescape(_TAG.sub(" ", _AT.sub(" ", text or ""))).strip()


def _when(value: str):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(tz=UTC)


def _mentions_mylo(activity: dict) -> bool:
    bot = str((activity.get("recipient") or {}).get("id") or "")
    return any(
        entity.get("type") == "mention"
        and str((entity.get("mentioned") or {}).get("id") or "") == bot
        for entity in activity.get("entities") or []
    )


def handle_activity(activity: dict) -> dict:
    import apps.ambient.service as service

    from . import slack_link, teams_outbox, teams_resolve

    kind = activity.get("type")
    data = activity.get("channelData") or {}
    tenant = str((data.get("tenant") or {}).get("id") or "")
    team = str((data.get("team") or {}).get("id") or "")
    channel = str((data.get("channel") or {}).get("id") or "")
    conversation = activity.get("conversation") or {}
    conversation_id = str(conversation.get("id") or "")
    personal = conversation.get("conversationType") == "personal"
    service_url = str(activity.get("serviceUrl") or "")
    sender = activity.get("from") or {}
    aad = str(sender.get("aadObjectId") or "")
    bot_id = str((activity.get("recipient") or {}).get("id") or "")
    message_id = str(activity.get("id") or "")

    if kind in ("conversationUpdate", "installationUpdate"):
        action = activity.get("action") or data.get("eventType") or ""
        if team and action in ("remove", "teamDeleted"):
            link = teams_resolve.team_link(team)
            if link is not None:
                teams_resolve.deactivate_team(link)
            service.teams_removed(team)
            return {"handled": "removed"}
        if team:
            teams_resolve.install_team(
                team_id=team,
                tenant_id=tenant,
                name=str((data.get("team") or {}).get("name") or ""),
                service_url=service_url,
            )
            return {"handled": "installed"}
        return {"handled": "ignored"}
    if kind == "messageUpdate":
        service.teams_edited(
            tenant,
            team,
            conversation_id,
            message_id,
            plain(activity.get("text") or ""),
            personal=personal,
        )
        return {"handled": "edited"}
    if kind == "messageDelete":
        service.teams_deleted(
            tenant, team, conversation_id, message_id, personal=personal
        )
        return {"handled": "deleted"}
    if kind != "message" or not aad:
        return {"handled": "ignored"}
    if not personal and conversation.get("conversationType") != "channel":
        return {"handled": "ignored"}  # group chats: no consent model covers them

    value = activity.get("value") or {}
    if personal and isinstance(value, dict) and value.get("ambient"):
        suggestion_id, _, choice = str(value["ambient"]).partition(":")
        line = service.teams_answer(tenant, aad, suggestion_id, choice)
        teams_outbox.enqueue(
            dedupe_key=f"teams-answer:{message_id}",
            kind="ambient_reply",
            service_url=service_url,
            conversation_id=conversation_id,
            text=line,
        )
        return {"handled": "answered"}

    text = plain(activity.get("text") or "")
    code = slack_link.find_code(text)
    if code and personal:
        ok = _link_person(
            code,
            tenant=tenant,
            aad=aad,
            service_url=service_url,
            conversation_id=conversation_id,
        )
        teams_outbox.enqueue(
            dedupe_key=f"teams-link:{message_id}",
            kind="teams_link",
            service_url=service_url,
            conversation_id=conversation_id,
            text=(
                "Linked — this Teams account is now yours on Mycelium. Turn "
                "listening on in Mylo & you if you want Mylo to learn from it."
                if ok
                else "That code didn't work — make a new one on your Mycelium profile."
            ),
        )
        return {"handled": "link_person", "ok": ok}
    if code and _mentions_mylo(activity) and team:
        ok = _link_lab(code, team=team, conversation_id=conversation_id)
        teams_outbox.enqueue(
            dedupe_key=f"teams-lab-link:{message_id}",
            kind="teams_link",
            service_url=service_url,
            conversation_id=conversation_id,
            text=(
                "Linked to the lab — its Mylo reports will be posted here."
                if ok
                else "That lab code didn't work — a lab manager can make a new one."
            ),
        )
        return {"handled": "link_lab", "ok": ok}

    heard = service.teams_heard(
        tenant_id=tenant,
        team_id=team,
        conversation_id=conversation_id,
        channel_id=channel,
        message_id=message_id,
        text=text,
        sent_at=_when(activity.get("timestamp") or ""),
        aad_object_id=aad,
        is_personal=personal,
        channel_label=str((data.get("channel") or {}).get("name") or ""),
        from_mylo=str(sender.get("id") or "") == bot_id,
        explicit=personal or _mentions_mylo(activity),
        reply_to_id=str(activity.get("replyToId") or ""),
    )
    if personal:
        from ..tasks import teams_dialogue

        teams_dialogue.delay(
            tenant, aad, service_url, conversation_id, message_id, text
        )
    return {"handled": "heard", "stored": bool(heard.stored), "reason": heard.reason}


def _link_person(code, *, tenant, aad, service_url, conversation_id) -> bool:
    from django.db import transaction

    from . import slack_link, slack_resolve, teams_resolve

    with transaction.atomic():
        row = slack_resolve.claim_code(
            slack_link._hash(code), "person", platform="teams"
        )
        if row is None:
            return False
        if teams_resolve.linked_elsewhere(tenant, aad, not_user=row.user):
            return False
        teams_resolve.bind_identity(
            row.user,
            tenant_id=tenant,
            aad_object_id=aad,
            service_url=service_url,
            conversation_id=conversation_id,
        )
        slack_resolve.use_code(row, tenant)
    return True


def _link_lab(code, *, team, conversation_id) -> bool:
    from django.db import transaction

    from . import slack_link, slack_resolve, teams_resolve

    with transaction.atomic():
        row = slack_resolve.claim_code(slack_link._hash(code), "lab", platform="teams")
        if row is None or row.lab_id is None:
            return False
        link = teams_resolve.team_link(team)
        if link is None or (link.lab_id and link.lab_id != row.lab_id):
            return False
        teams_resolve.bind_team_lab(link, row.lab_id, conversation_id)
        slack_resolve.use_code(row, team)
    return True


def dialogue(tenant, aad, service_url, conversation_id, message_id, text) -> str:
    import apps.ambient.service as service

    from . import teams_outbox

    reply = service.teams_dialogue_turn(tenant, aad, text)
    if reply:
        teams_outbox.enqueue(
            dedupe_key=f"teams-dialogue:{message_id}",
            kind="ambient_reply",
            service_url=service_url,
            conversation_id=conversation_id,
            text=reply,
        )
    return reply
