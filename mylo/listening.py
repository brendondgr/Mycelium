"""Async listening operations the listen cog calls.

Every function here is a thin async wrapper over
``apps.ambient.service`` — the backend's single ORM boundary for listening —
run off the event loop through :func:`mylo.mycelium.db`. This module imports no
Django model, exactly like :mod:`mylo.linking`, and the cog imports no backend
module at all.

Two rules the shape is there to keep:

* **Nothing here decides anything.** Whether a person may be listened to is a
  database question answered on the backend, on arrival, every time. The cog
  forwards a snowflake and never caches a verdict, so somebody opting out is
  ignored from their very next message rather than from the next cache expiry.
* **Nothing here raises.** A listener that throws takes the gateway's event loop
  with it, and losing the connection is a worse failure than losing a message.
  Every call returns a plain value and swallows what it cannot do, having logged
  it.
"""

from __future__ import annotations

import logging

from . import mycelium

log = logging.getLogger(__name__)


async def heard(**fields) -> dict:
    """Forward one message to the ledger.

    Returns ``{"stored": bool, "reason": str, "notify_member": bool}``.
    ``notify_member`` is the backend asking the gateway to tell this person,
    once, that the server they are in is listening — something only the gateway
    can do, because only it holds the connection.
    """
    try:
        outcome = await mycelium.db(_heard_sync, fields)
    except Exception:  # noqa: BLE001 — never kill the gateway over one message
        log.exception("could not record a message")
        return {"stored": False, "reason": "error", "notify_member": False}
    return outcome


async def message_edited(guild_id: str, message_id: str, text: str, *, is_dm=False):
    try:
        return await mycelium.db(
            _edited_sync, str(guild_id), str(message_id), text or "", bool(is_dm)
        )
    except Exception:  # noqa: BLE001
        log.exception("could not reconcile an edit")
        return 0


async def message_deleted(guild_id: str, message_id: str, *, is_dm=False):
    try:
        return await mycelium.db(
            _deleted_sync, str(guild_id), str(message_id), bool(is_dm)
        )
    except Exception:  # noqa: BLE001
        log.exception("could not reconcile a deletion")
        return False


async def listening_state(guild_id: str) -> dict:
    try:
        return await mycelium.db(_state_sync, str(guild_id))
    except Exception:  # noqa: BLE001
        log.exception("could not read listening state for %s", guild_id)
        return {"known": False, "listening": False, "excluded": [], "social": []}


async def set_guild_listening(
    discord_user_id: str, guild_id: str, *, on: bool
) -> tuple[str, dict]:
    """Turn listening on or off for a server.

    Authority is checked on the backend against the same manager rule `/setup`
    uses: the server must be activated and the caller a linked lab manager.
    """
    try:
        return await mycelium.db(
            _set_listening_sync, str(discord_user_id), str(guild_id), bool(on)
        )
    except Exception:  # noqa: BLE001
        log.exception("could not change listening for %s", guild_id)
        return ("error", {"message": "Something went wrong. Nothing was changed."})


async def set_channel_rule(
    discord_user_id: str, guild_id: str, channel_id: str, *, rule: str, on: bool
) -> tuple[str, dict]:
    try:
        return await mycelium.db(
            _set_channel_sync,
            str(discord_user_id),
            str(guild_id),
            str(channel_id),
            str(rule),
            bool(on),
        )
    except Exception:  # noqa: BLE001
        log.exception("could not change a channel rule for %s", guild_id)
        return ("error", {"message": "Something went wrong. Nothing was changed."})


async def note(discord_user_id: str, text: str, *, guild_id: str = "") -> dict:
    """``/mylo note`` and the message action — an explicit thing to remember.

    The same raw message as anything overheard, marked explicit so Plan 04 can
    weigh being told above being overheard. A convenience, never the way the
    system is meant to be fed.
    """
    try:
        return await mycelium.db(
            _note_sync, str(discord_user_id), text or "", str(guild_id)
        )
    except Exception:  # noqa: BLE001
        log.exception("could not record a note")
        return {"stored": False, "reason": "error"}


async def member_state(discord_user_id: str) -> dict:
    try:
        return await mycelium.db(_member_state_sync, str(discord_user_id))
    except Exception:  # noqa: BLE001
        log.exception("could not read listening state for a member")
        return {"linked": False, "enabled": False, "questions_muted": False}


async def set_member_listening(discord_user_id: str, *, on: bool) -> dict:
    try:
        return await mycelium.db(
            _set_member_sync, str(discord_user_id), bool(on)
        )
    except Exception:  # noqa: BLE001
        log.exception("could not change a member's listening setting")
        return {"linked": False, "enabled": False}


async def record_notice(guild_id: str, discord_user_id: str, *, delivered: bool):
    try:
        return await mycelium.db(
            _notice_sync, str(guild_id), str(discord_user_id), bool(delivered)
        )
    except Exception:  # noqa: BLE001
        log.exception("could not record a listening notice")
        return None


async def set_marker(guild_id: str, *, channel_id: str, message_id: str) -> None:
    try:
        await mycelium.db(
            _marker_sync, str(guild_id), str(channel_id), str(message_id)
        )
    except Exception:  # noqa: BLE001
        log.exception("could not record the listening marker")


async def dialogue(discord_user_id: str, text: str, *, reply_to_id: str = "") -> str:
    """A DM read as a turn of the confirmation dialogue (Plan 06).

    Returns what Mylo should reply, or "" when the message was ordinary
    conversation and the dialogue has nothing to say.
    """
    try:
        return await mycelium.db(
            _dialogue_sync, str(discord_user_id), text or "", str(reply_to_id or "")
        )
    except Exception:  # noqa: BLE001
        log.exception("could not run a dialogue turn")
        return ""


async def answer_button(discord_user_id: str, suggestion_id: str, choice: str) -> str:
    try:
        return await mycelium.db(
            _button_sync, str(discord_user_id), str(suggestion_id), str(choice)
        )
    except Exception:  # noqa: BLE001
        log.exception("could not record a button answer")
        return "Something went wrong — nothing was changed."


# --------------------------------------------------------------------------- #
# Synchronous bodies (run in a worker thread with Django configured)
# --------------------------------------------------------------------------- #
def _dialogue_sync(discord_user_id: str, text: str, reply_to_id: str) -> str:
    from apps.ambient import service

    return service.dialogue_turn(discord_user_id, text, reply_to_id=reply_to_id)


def _button_sync(discord_user_id: str, suggestion_id: str, choice: str) -> str:
    from apps.ambient import service

    return service.answer_button(discord_user_id, suggestion_id, choice)

def _heard_sync(fields: dict) -> dict:
    from apps.ambient import service

    outcome = service.heard(**fields)
    return {
        "stored": outcome.stored,
        "reason": outcome.reason,
        "notify_member": outcome.notify_member,
    }


def _edited_sync(guild_id: str, message_id: str, text: str, is_dm: bool) -> int:
    from apps.ambient import service

    return service.message_edited(guild_id, message_id, text, is_dm=is_dm)


def _deleted_sync(guild_id: str, message_id: str, is_dm: bool) -> bool:
    from apps.ambient import service

    return service.message_deleted(guild_id, message_id, is_dm=is_dm)


def _state_sync(guild_id: str) -> dict:
    from apps.ambient import service

    return service.listening_state(guild_id)


def _member_state_sync(discord_user_id: str) -> dict:
    from apps.ambient import service

    return service.member_state(discord_user_id)


def _note_sync(discord_user_id: str, text: str, guild_id: str) -> dict:
    from django.utils import timezone

    from apps.ambient import service

    outcome = service.heard(
        guild_id=guild_id,
        message_id=f"note:{discord_user_id}:{timezone.now().timestamp():.0f}",
        text=text,
        sent_at=timezone.now(),
        author_id=discord_user_id,
        explicit=True,
        is_dm=True,
    )
    return {"stored": outcome.stored, "reason": outcome.reason}


def _set_member_sync(discord_user_id: str, on: bool) -> dict:
    from apps.ambient import service

    return service.set_member_listening(discord_user_id, on=on)


def _notice_sync(guild_id: str, discord_user_id: str, delivered: bool):
    from apps.ambient import service

    return service.record_notice(guild_id, discord_user_id, delivered=delivered)


def _marker_sync(guild_id: str, channel_id: str, message_id: str) -> None:
    from apps.ambient import service

    service.set_marker(guild_id, channel_id=channel_id, message_id=message_id)


def _manager_gate(guild_id: str, discord_user_id: str):
    """``(lab, None)`` when the caller may configure this server, else a refusal.

    Deliberately the *same* gate `/setup` terminates in, reached the same way:
    the server must be activated, and the caller must clear
    ``gate.authorize`` for the ``listening`` action, which the one
    authorization table holds to the management right and the bot add-on.
    Turning listening on for a whole server is the most consequential switch
    the bot has, so it is not a looser gate than choosing a channel — and it
    cannot drift from `/setup` without somebody editing that table on purpose.
    """
    from apps.integrations.services import resolve

    link = resolve.get_guild_link(guild_id)
    if link is None or link.state != resolve.GUILD_ACTIVE:
        return (
            None,
            (
                "not_active",
                {
                    "message": "This server isn't connected to a lab yet. A lab "
                    "admin or PI runs `/activate-lab code:<code>` first. (Listening "
                    "works in a server that holds exactly one lab.)"
                },
            ),
        )

    from apps.integrations.services import gate

    verdict = gate.authorize(
        discord_user_id=discord_user_id,
        action="listening",
        guild_id=link.guild_id,
    )
    if not verdict.ok:
        return (None, (str(verdict.denial), {"message": verdict.message}))
    return (verdict.lab, None)


def _set_listening_sync(
    discord_user_id: str, guild_id: str, on: bool
) -> tuple[str, dict]:
    from apps.ambient import service

    lab, refusal = _manager_gate(guild_id, discord_user_id)
    if refusal is not None:
        return refusal
    state = service.set_guild_listening(
        guild_id, on=on, changed_by=None, lab=lab
    )
    if state.get("refused") == "unavailable":
        return (
            "unavailable",
            {
                "message": "Listening isn't switched on for Mycelium yet, so "
                "there is nothing to turn on here. Nothing was changed and no "
                "notice was posted."
            },
        )
    return ("ok", state)


def _set_channel_sync(
    discord_user_id: str, guild_id: str, channel_id: str, rule: str, on: bool
) -> tuple[str, dict]:
    from apps.ambient import service

    _, refusal = _manager_gate(guild_id, discord_user_id)
    if refusal is not None:
        return refusal
    return ("ok", service.set_channel_rule(guild_id, channel_id, rule=rule, on=on))
