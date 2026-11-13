"""Who may be observed at all — resolved *before* anything is buffered.

Three promises meet in one function. A person is only ever observed when

1. the **surface** consented (a lab or department head turned listening on for
   that server — and while they have it off, nothing a member does turns it on),
2. the **person** opted in on that platform, default off, and did not keep this
   server out (:class:`~.models.RecordingExclusion`), and
3. their **effective tier is paid** and their platform identity is linked.

A person can also keep one **project** out: a message in a channel tied to that
project is not recorded (:func:`project_excluded_here`, checked on arrival
beside :func:`observable`), and the project is never an attribution candidate
for them (:func:`excluded_project_ids`).

One platform is different by the owner's decision (Mylo agent plan, D-3):
**Mylo chat** (``agent_chat``), conversations a person has with Mylo in the
app. There the person chose to talk to Mylo, so learning is on unless they
turned it off: a missing ``ListeningConsent`` row reads as *on*. Its master
switch is the agent tool's own ``tools.agent.learning``, not
``features.ambient``, and it is off whenever the agent tool is not loaded.
Discord, Slack, Teams and transcripts keep "off by construction".

Point 3 is resolved exactly the way the profile caps are — through
:func:`apps.billing.entitlements.effective_tier`, so a member of a paid lab is
paid even on a free personal plan. A server member without a Mycelium account
never resolves to a user at all, which is why :func:`observable` refuses a
``None`` speaker rather than treating it as anonymous evidence.

The check runs on arrival, on the backend, with no cached verdict at the edge:
a person who opts out stops being recorded on the next message, not on the next
cache expiry.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth.models import User

from apps.billing.entitlements import effective_tier

from .models import ListeningConsent, RecordingExclusion, Source


@dataclass(frozen=True)
class Verdict:
    """Whether a message may be observed, and the one reason it may not.

    ``reason`` is a stable slug meant for counters and logs, never for a person
    to read. It is empty when ``allowed`` is true.
    """

    allowed: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.allowed


ALLOWED = Verdict(True)


def ambient_enabled() -> bool:
    """The deployment master switch. Ships off; nothing is collected until set."""
    return bool(getattr(settings, "AMBIENT_ENABLED", False))


def tier_is_paid(user: User) -> bool:
    """Whether the user's effective tier is a paid one.

    Deliberately not a :class:`~apps.billing.entitlements.Feature`: listening is
    not a capability a tier unlocks but a boundary on whose conversation is read
    at all, and it must hold regardless of the ``BILLING_ENFORCE_ENTITLEMENTS``
    switch, which grants every *feature* to everyone while it is off.
    """
    from apps.billing.entitlements import ambient_enabled as tier_has_ambient

    return tier_has_ambient(effective_tier(user))


#: Platforms where listening is on unless the person turned it off.
DEFAULT_ON_PLATFORMS = frozenset({"agent_chat"})


def person_opted_in(user: User, platform: str) -> bool:
    """Whether ``user`` has listening on for ``platform``. Absent row = off,
    except on a :data:`DEFAULT_ON_PLATFORMS` platform, where it is on."""
    row = ListeningConsent.objects.filter(user=user, platform=platform).first()
    if row is None:
        return platform in DEFAULT_ON_PLATFORMS
    return row.enabled


def excluded_from_source(user: User, source: Source) -> bool:
    """Whether ``user`` kept this one server (or workspace, or team) out."""
    return RecordingExclusion.objects.filter(user=user, source=source).exists()


def excluded_project_ids(user: User) -> set:
    """The projects ``user`` asked Mylo not to record them about."""
    return set(
        RecordingExclusion.objects.filter(
            user=user, project__isnull=False
        ).values_list("project_id", flat=True)
    )


def project_excluded_here(user: User | None, source: Source, place_id: str) -> bool:
    """Whether ``place_id`` is a channel tied to a project ``user`` excluded.

    A channel hint (:class:`~.models.ChannelHint`) says a channel, or a meeting,
    is about one project; a person who keeps that project out is not recorded
    there at all, rather than recorded and left unattributed.
    """
    if user is None or not place_id:
        return False
    from .models import ChannelHint

    hinted = ChannelHint.objects.filter(
        source=source, place_id=str(place_id)
    ).values_list("project_id", flat=True)
    return RecordingExclusion.objects.filter(
        user=user, project_id__in=list(hinted)
    ).exists()


def agent_chat_enabled() -> bool:
    """The master switch for learning from Mylo chats: the agent tool's
    ``tools.agent.learning``, published as ``AGENT_LEARNING`` only while the
    tool is loaded."""
    return bool(getattr(settings, "AGENT_LEARNING", False))


def listening_available(source: Source) -> bool:
    """The deployment switch that governs ``source``."""
    if source.kind == Source.Kind.AGENT_CHAT:
        return agent_chat_enabled()
    return ambient_enabled()


def questions_muted(user: User, platform: str) -> bool:
    """Whether ``user`` has told Mylo to shut off its questions on ``platform``."""
    return ListeningConsent.objects.filter(
        user=user, platform=platform, questions_muted=True
    ).exists()


def observable(user: User | None, source: Source) -> Verdict:
    """Whether a message from ``user`` on ``source`` may be recorded.

    Refusals are ordered cheapest-first and stop at the first one, so the reason
    names the outermost gate rather than every gate that would also have failed.
    """
    if not listening_available(source):
        return Verdict(False, "ambient_disabled")
    if user is None:
        # An unlinked member, a bot, or a webhook. Nothing is recorded about
        # them — not an observation, not a raw id, not a counter keyed to them.
        return Verdict(False, "speaker_unlinked")
    if not user.is_active:
        return Verdict(False, "speaker_inactive")
    if not source.listening:
        return Verdict(False, "source_not_consented")
    if not person_opted_in(user, source.platform):
        return Verdict(False, "person_not_opted_in")
    if excluded_from_source(user, source):
        return Verdict(False, "person_excluded_server")
    if not tier_is_paid(user):
        return Verdict(False, "tier_free")
    return ALLOWED
