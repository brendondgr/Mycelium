"""Who may be found, by whom, and how often (plan CN-04, design §7).

Two settings that sound alike are kept apart:

* **who can find me** — the candidate's audience, set once in their settings;
* **where I want to look** — the seeker's scope, chosen per search (CN-05).

A person may appear only when both allow it: their audience includes the
seeker **and** the seeker's scope includes them, both judged on verified
affiliations. On top of that, the **appearance cap** limits how many distinct
seekers see the same person in a week, so the most sought-after people are not
flooded into switching the setting off.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .affiliation import refresh
from .models import Appearance, Audience, CollaborationSetting, OpenTo

#: Scopes from narrowest to widest; a seeker's scope and a candidate's audience
#: use the same three words.
ORDER = [Audience.INSTITUTION, Audience.COUNTRY, Audience.ANYWHERE]


class ConsentRefused(ValueError):
    """The requested setting is not allowed; nothing was changed."""


@dataclass(frozen=True)
class Place:
    """A verified affiliation, reduced to what scope comparisons need."""

    domain: str = ""
    country: str = ""


def place_of(user) -> Place | None:
    """A verified place for the user, or ``None`` if their email is unverified."""
    row = refresh(user)
    if row is None:
        return None
    return Place(domain=row.domain, country=row.country)


def allowed_audiences(place: Place | None) -> list[str]:
    """Audiences a person may choose: nothing without a verified email; only
    ``anywhere`` without a verified institution (a personal address)."""
    if place is None:
        return []
    if not place.domain:
        return [Audience.ANYWHERE]
    return list(ORDER)


def within(a: Place | None, b: Place | None, scope: str) -> bool:
    """Whether ``b`` falls inside ``a``'s ``scope``. Unverified is never inside."""
    if a is None or b is None:
        return False
    if scope == Audience.ANYWHERE:
        return True
    if scope == Audience.COUNTRY:
        return bool(a.country) and a.country == b.country
    return bool(a.domain) and a.domain == b.domain


def mutually_visible(
    candidate: Place | None,
    candidate_audience: str,
    seeker: Place | None,
    seeker_scope: str,
) -> bool:
    """Both sides allow it: the candidate's audience includes the seeker, and the
    seeker's scope includes the candidate (design §7)."""
    return within(candidate, seeker, candidate_audience) and within(
        seeker, candidate, seeker_scope
    )


def update(user, *, open: bool, audience: str, open_to=(), renew: bool = False):
    """Change a person's setting. Raises :class:`ConsentRefused` on a bad choice.

    Turning it on (or renewing) starts a fresh ``COLLAB_OPEN_MONTHS`` period;
    changing the audience or types while open keeps the current expiry.
    """
    if audience not in Audience.values:
        raise ConsentRefused(f"unknown audience {audience!r}")
    bad = [value for value in open_to if value not in OpenTo.values]
    if bad:
        raise ConsentRefused(f"unknown kinds of collaboration: {bad}")
    place = place_of(user)
    if open:
        choices = allowed_audiences(place)
        if not choices:
            raise ConsentRefused("verify your email before you can be found")
        if audience not in choices:
            raise ConsentRefused(
                "your verified email is not at an institution, so only "
                "'anywhere' is available"
            )
    setting, _ = CollaborationSetting.objects.get_or_create(user=user)
    now = timezone.now()
    starting = open and (not setting.is_open(now) or renew)
    setting.open = open
    setting.audience = audience
    setting.open_to = sorted(set(open_to))
    if starting:
        setting.expires_at = now + timedelta(days=30 * settings.COLLAB_OPEN_MONTHS)
        setting.renewal_notified_at = None
    if not open:
        setting.expires_at = None
    setting.save()
    return setting


def is_open(user, now=None) -> bool:
    setting = CollaborationSetting.objects.filter(user=user).first()
    return bool(setting and setting.is_open(now))


# --- the appearance cap ----------------------------------------------------


def iso_week(now=None) -> str:
    year, week, _ = (now or timezone.now()).isocalendar()
    return f"{year}-W{week:02d}"


def may_appear(candidate, seeker, now=None) -> bool:
    """Whether this seeker may see this candidate this week.

    A seeker who has already seen them keeps seeing them; a new seeker is let
    in only while the candidate has been shown to fewer than the cap.
    """
    week = iso_week(now)
    seen = Appearance.objects.filter(candidate=candidate, week=week)
    if seen.filter(seeker=seeker).exists():
        return True
    return seen.count() < settings.COLLAB_APPEARANCE_CAP


def record_appearance(candidate, seeker, now=None) -> None:
    try:
        with transaction.atomic():
            Appearance.objects.get_or_create(
                candidate=candidate, seeker=seeker, week=iso_week(now)
            )
    except IntegrityError:  # pragma: no cover - a concurrent search won the race
        pass


def prune_appearances(now=None) -> int:
    """Drop appearance rows older than eight weeks."""
    cutoff = (now or timezone.now()) - timedelta(weeks=8)
    return Appearance.objects.filter(created_at__lt=cutoff).delete()[0]
