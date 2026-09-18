"""The one door the Mylo gateway calls through.

The gateway runs Django in process (``mylo/mycelium.py``) and every
Discord-originated database touch goes through a single boundary module, the way
``integrations.services.resolve`` already works for linking and ``/setup``.
This is that module for listening. ``mylo/listening.py`` calls these functions
through ``mycelium.db(...)`` and imports no model of its own.

Everything here is **synchronous** and runs in a worker thread. Nothing here
talks to Discord — posting a notice or a marker is the cog's job, because the
gateway holds the connection and this side holds the data.

Three rules the shape enforces:

* **Eligibility is resolved here, on arrival, every time.** The gateway forwards
  a snowflake and nothing else about identity; whether that person may be
  listened to is a database question, answered now, so an opt-out or a lapsed
  subscription takes effect on the very next message rather than on the next
  cache expiry.
* **A refusal leaves a count, never a name.** "Forty-one messages were dropped
  here because their senders have not opted in" is an operational fact. "This
  person's messages were dropped" is a record of somebody who asked not to be
  recorded.
* **Nothing here reads meaning.** Plan 04 does that, later, from a window.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.utils import timezone

from . import activity, filters, reconcile
from .adapters.base import PlatformEvent
from .adapters.discord import DiscordAdapter, DiscordDirectMessageAdapter
from .eligibility import ambient_enabled
from .models import (
    ListeningConsent,
    MemberNotice,
    PlaceKind,
    Platform,
    Source,
    SourceActivity,
)

logger = logging.getLogger(__name__)

_GUILD = DiscordAdapter()
_DM = DiscordDirectMessageAdapter()

#: Which activity counter a refusal reason lands in. A reason with no column of
#: its own lands in ``dropped_other`` rather than being lost.
_COUNTER_BY_REASON = {
    "person_not_opted_in": "dropped_not_opted_in",
    "speaker_unlinked": "dropped_unlinked",
    "speaker_inactive": "dropped_unlinked",
    "tier_free": "dropped_free_tier",
    "excluded_channel": "dropped_excluded_channel",
    "social_channel": "dropped_excluded_channel",
    "too_short": "dropped_too_short",
    "empty": "dropped_too_short",
    "bot": "dropped_bot",
}


@dataclass(frozen=True)
class Heard:
    """What happened to one message, in terms the gateway can act on."""

    stored: bool
    reason: str = ""
    #: True when this person should be told, once, that the server is listening.
    notify_member: bool = False

    def __bool__(self) -> bool:
        return self.stored


def _bump(source: Source, field_name: str, *, heard: bool = True) -> None:
    activity.bump(source, field_name, heard=heard)


def guild_source(guild_id: str) -> Source | None:
    """The listening surface for a Discord server, if one was ever created."""
    return Source.objects.filter(
        kind=Source.Kind.DISCORD_GUILD, external_id=str(guild_id)
    ).first()


def listening_state(guild_id: str) -> dict:
    """What `/setup` and `/mylo health` need to render, in one hop."""
    source = guild_source(guild_id)
    if source is None:
        return {
            "known": False,
            "available": ambient_enabled(),
            "listening": False,
            "excluded": [],
            "social": [],
            "marker_channel_id": "",
        }
    today = timezone.localdate()
    today_row = SourceActivity.objects.filter(source=source, day=today).first()
    return {
        "known": True,
        "available": ambient_enabled(),
        "listening": source.listening,
        "lab_name": source.lab.name if source.lab_id else "",
        "excluded": [str(one) for one in (source.excluded_place_ids or [])],
        "social": [str(one) for one in (source.social_place_ids or [])],
        "marker_channel_id": source.marker_channel_id,
        "marker_message_id": source.marker_message_id,
        "heard_today": today_row.heard if today_row else 0,
        "stored_today": today_row.stored if today_row else 0,
    }


def set_guild_listening(guild_id: str, *, on: bool, changed_by=None, lab=None) -> dict:
    """Turn listening on or off for a server, creating the surface on first use.

    Turning it off purges the raw buffer for that source at once: consent
    withdrawn is not consent to keep what has already been heard for another
    six hours.

    Turning it **on** is refused while the deployment's ``AMBIENT_ENABLED`` is
    off. The server would otherwise read "listening" and post a public notice
    saying so while nothing is recorded — a notice that is false in the
    reassuring direction today and in the alarming one the day somebody flips
    the switch without anyone in that server being told again.
    """
    if on and not ambient_enabled():
        return {**listening_state(guild_id), "refused": "unavailable"}
    source = guild_source(guild_id)
    if source is None:
        if not on:
            return listening_state(guild_id)
        source = Source.objects.create(
            kind=Source.Kind.DISCORD_GUILD,
            external_id=str(guild_id),
            lab=lab,
            label=getattr(lab, "name", "") or "",
            consent_state=Source.Consent.PENDING,
        )

    if on:
        source.consent_state = Source.Consent.ACTIVE
        source.consent_changed_at = timezone.now()
        source.consent_changed_by = changed_by
        if lab is not None and source.lab_id is None:
            source.lab = lab
        source.save(
            update_fields=[
                "consent_state",
                "consent_changed_at",
                "consent_changed_by",
                "lab",
            ]
        )
    else:
        reconcile.revoke_source(source)
        source.consent_changed_by = changed_by
        source.save(update_fields=["consent_changed_by"])
    return listening_state(guild_id)


def set_channel_rule(guild_id: str, channel_id: str, *, rule: str, on: bool) -> dict:
    """Add or remove a channel from the excluded or social list.

    ``rule`` is ``"excluded"`` or ``"social"``. Both stop a channel being read;
    they are kept apart so a manager can tell which of their settings is why a
    channel went quiet.
    """
    source = guild_source(guild_id)
    if source is None:
        return listening_state(guild_id)
    field_name = (
        "excluded_place_ids" if rule == "excluded" else "social_place_ids"
    )
    current = [str(one) for one in (getattr(source, field_name) or [])]
    channel = str(channel_id)
    if on and channel not in current:
        current.append(channel)
    elif not on and channel in current:
        current.remove(channel)
    setattr(source, field_name, current)
    source.save(update_fields=[field_name])
    return listening_state(guild_id)


def set_member_listening(discord_user_id: str, *, on: bool) -> dict:
    """One person's opt-in for Discord. The absent row means off."""
    from apps.integrations.services import resolve

    user = resolve.resolve_user(str(discord_user_id))
    if user is None:
        return {"linked": False, "enabled": False, "available": ambient_enabled()}
    consent, _ = ListeningConsent.objects.get_or_create(
        user=user, platform=Platform.DISCORD
    )
    consent.enabled = bool(on)
    if on:
        consent.enabled_at = timezone.now()
    else:
        consent.disabled_at = timezone.now()
    consent.save(update_fields=["enabled", "enabled_at", "disabled_at"])
    return {
        "linked": True,
        "enabled": consent.enabled,
        "available": ambient_enabled(),
    }


def member_state(discord_user_id: str) -> dict:
    """Whether this person is linked, listening, and being asked questions."""
    from apps.integrations.services import resolve

    user = resolve.resolve_user(str(discord_user_id))
    if user is None:
        return {
            "linked": False,
            "enabled": False,
            "questions_muted": False,
            "available": ambient_enabled(),
        }
    consent = ListeningConsent.objects.filter(
        user=user, platform=Platform.DISCORD
    ).first()
    return {
        "linked": True,
        "enabled": bool(consent and consent.enabled),
        "questions_muted": bool(consent and consent.questions_muted),
        "available": ambient_enabled(),
    }


def _needs_notice(source: Source, discord_user_id: str) -> bool:
    """Whether this person has never been told this server is listening."""
    from apps.integrations.services import resolve

    user = resolve.resolve_user(str(discord_user_id))
    if user is None:
        return False
    return not MemberNotice.objects.filter(
        user=user, source=source, kind=MemberNotice.Kind.SERVER_LISTENING
    ).exists()


def record_notice(source_external_id: str, discord_user_id: str, *, delivered: bool):
    """Record that somebody was told, once, that a server is listening."""
    from apps.integrations.services import resolve

    user = resolve.resolve_user(str(discord_user_id))
    source = guild_source(source_external_id)
    if user is None or source is None:
        return None
    notice, created = MemberNotice.objects.get_or_create(
        user=user,
        source=source,
        kind=MemberNotice.Kind.SERVER_LISTENING,
        defaults={"delivered": delivered},
    )
    if not created and notice.delivered != delivered:
        notice.delivered = delivered
        notice.save(update_fields=["delivered"])
    return notice


def set_marker(guild_id: str, *, channel_id: str, message_id: str) -> None:
    """Remember the pinned "Mylo is listening" post so it is edited, not repeated."""
    source = guild_source(guild_id)
    if source is None:
        return
    source.marker_channel_id = str(channel_id)
    source.marker_message_id = str(message_id)
    source.save(update_fields=["marker_channel_id", "marker_message_id"])


def heard(
    *,
    guild_id: str,
    message_id: str,
    text: str,
    sent_at,
    author_id: str,
    place_kind: str = PlaceKind.CHANNEL,
    place_id: str = "",
    place_label: str = "",
    attachment_urls=None,
    is_bot: bool = False,
    from_mylo: bool = False,
    explicit: bool = False,
    is_dm: bool = False,
    mention_ids=None,
) -> Heard:
    """One message from Discord. The whole of what the gateway asks of us.

    Returns quickly and never raises: a failure to record a message must not
    take down the connection that is receiving the next one.
    """
    if not ambient_enabled():
        return Heard(False, "ambient_disabled")

    attachments = list(attachment_urls or [])
    try:
        if is_dm:
            return _heard_dm(
                message_id=message_id,
                text=text,
                sent_at=sent_at,
                author_id=author_id,
                attachments=attachments,
                is_bot=is_bot,
                from_mylo=from_mylo,
            )

        source = guild_source(guild_id)
        if source is None or not source.listening:
            return Heard(False, "source_not_consented")

        verdict = filters.worth_keeping(
            text,
            source=source,
            place_id=place_id,
            is_bot=is_bot,
            from_mylo=from_mylo,
            explicit=explicit,
            has_attachment=bool(attachments),
        )
        if not verdict:
            _bump(source, _COUNTER_BY_REASON.get(verdict.reason, "dropped_other"))
            return Heard(False, verdict.reason)

        outcome = _GUILD.deliver(
            PlatformEvent(
                source_external_id=str(guild_id),
                message_external_id=str(message_id),
                text=filters.truncate(text or ""),
                sent_at=sent_at,
                author_external_id=str(author_id),
                place_kind=place_kind,
                place_id=str(place_id),
                place_label=place_label,
                attachment_urls=attachments,
                from_mylo=from_mylo,
                explicit=explicit,
                mention_external_ids=[str(one) for one in (mention_ids or [])],
            )
        )
        if outcome.stored:
            _bump(source, "stored")
            return Heard(True)

        _bump(source, _COUNTER_BY_REASON.get(outcome.reason, "dropped_other"))
        return Heard(
            False,
            outcome.reason,
            notify_member=(
                outcome.reason == "person_not_opted_in"
                and _needs_notice(source, author_id)
            ),
        )
    except Exception:  # pragma: no cover - never take the gateway down
        logger.exception("ambient: failed to record a message")
        return Heard(False, "error")


def _heard_dm(
    *, message_id, text, sent_at, author_id, attachments, is_bot, from_mylo
) -> Heard:
    """A conversation with Mylo. Its surface is the person, not a server.

    A DM is always explicit — somebody chose to say this to Mylo — and always
    personal, which is why it gets its own source with no lab attached rather
    than being folded into whichever server they happen to share with Mylo.
    """
    if is_bot and not from_mylo:
        return Heard(False, "bot")
    key = str(author_id)
    source, _ = Source.objects.get_or_create(
        kind=Source.Kind.DISCORD_DM,
        external_id=key,
        defaults={"consent_state": Source.Consent.ACTIVE, "label": "Direct message"},
    )
    if not source.listening:
        return Heard(False, "source_not_consented")

    outcome = _DM.deliver(
        PlatformEvent(
            source_external_id=key,
            message_external_id=str(message_id),
            text=filters.truncate(text or ""),
            sent_at=sent_at,
            author_external_id=key,
            place_kind=PlaceKind.DM,
            attachment_urls=attachments,
            from_mylo=from_mylo,
            explicit=True,
        )
    )
    if outcome.stored:
        _bump(source, "stored")
        return Heard(True)
    _bump(source, _COUNTER_BY_REASON.get(outcome.reason, "dropped_other"))
    return Heard(False, outcome.reason)


def message_edited(guild_id: str, message_id: str, text: str, *, is_dm=False) -> int:
    """Forwarded from ``on_raw_message_edit``. Plan 01 reconciles it."""
    source = (
        Source.objects.filter(
            kind=Source.Kind.DISCORD_DM, external_id=str(guild_id)
        ).first()
        if is_dm
        else guild_source(guild_id)
    )
    if source is None:
        return 0
    return reconcile.message_edited(source, str(message_id), text or "")


def message_deleted(guild_id: str, message_id: str, *, is_dm=False) -> bool:
    """Forwarded from ``on_raw_message_delete``. The evidence goes with it."""
    source = (
        Source.objects.filter(
            kind=Source.Kind.DISCORD_DM, external_id=str(guild_id)
        ).first()
        if is_dm
        else guild_source(guild_id)
    )
    if source is None:
        return False
    reconcile.message_deleted(source, str(message_id))
    return True
