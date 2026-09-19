"""Who may be observed at all — resolved *before* anything is buffered.

Three promises meet in one function. A person is only ever observed when

1. the **surface** consented (a lab manager turned listening on for that guild),
2. the **person** opted in on that platform, default off, and
3. their **effective tier is paid** and their platform identity is linked.

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

from .models import ListeningConsent, Source


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


def person_opted_in(user: User, platform: str) -> bool:
    """Whether ``user`` turned listening on for ``platform``. Absent row = off."""
    return ListeningConsent.objects.filter(
        user=user, platform=platform, enabled=True
    ).exists()


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
    if not ambient_enabled():
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
    if not tier_is_paid(user):
        return Verdict(False, "tier_free")
    return ALLOWED
