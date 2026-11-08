"""Who Mylo pushes to on Discord today, and at what hour their morning is.

Cadence existed as a stored preference long before anything read it. ``cadence``
has been on :class:`~apps.accounts.models.WatchPreference` and
:class:`~apps.accounts.models.LabWatchPreference` since onboarding first asked for
it, and the profile editor, the lab editor and the API have all been writing it —
but ``select_users``, ``eligible_recipients`` and ``eligible_labs`` never looked at
it, so everyone linked to Discord got a post every single day regardless of what
they chose. This module is the read side that was missing.

Two rules, and they are deliberately narrow:

**Cadence governs push, never computation** (plan D2). The nightly run still scores
every scheduled-eligible person and lab, still writes their briefing, still fires
their alerts and bell notifications, every day, whatever their cadence. What
cadence decides is only whether a Discord message leaves the building. A
weekly-cadence reader opening the web app on a Wednesday sees exactly what a
daily-cadence reader sees; they simply were not interrupted about it.

**The stored choice is the whole rule.** Onboarding asks one question — "Daily
digest" or "Weekly digest", under the promise *"Mylo messages you on Discord daily
or weekly"* — and this module honours exactly that. Daily means every day,
weekends included. Weekly means Monday, and nothing else.

Two earlier rules sat on top of that choice and are gone, because between them they
made "Daily" mean four days out of seven. A weekend blackout dropped Saturday and
Sunday for everyone, and a "Monday is the weekly, for everybody" rule replaced a
daily subscriber's Monday with a weekly they had not chosen — so someone who asked
for a daily digest got dailies Tuesday through Friday plus one weekly. The setting
they picked is the only thing that decides now.

The one crack in "weekly means Monday" is :data:`URGENT` (open decision OD2): an
opt-in, off by default, for the single case where waiting until Monday is a real
loss — a deadline moving on something the reader saved that is due inside their
buffer. It is not a second daily with a different name, and
:func:`tools.delivery.alerts` is the only thing allowed to raise one.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone

#: What a push can be. These are the *shapes* of delivery, not outbox kinds — one
#: shape may queue two rows (the weekly's embed and its attached PDF).
DAILY = "daily"
WEEKLY = "weekly"
URGENT = "urgent"

#: The two stored cadence values (``accounts.WatchCadence``), repeated here so a
#: caller reasoning about delivery does not have to import the accounts app.
CADENCE_DAILY = "daily"
CADENCE_WEEKLY = "weekly"

#: ``date.weekday()`` value. Monday is 0 — the one day the weekly goes out.
MONDAY = 0

#: Fallbacks when a target has no watch row yet, or an unreadable zone name. The
#: user default is 8 and the lab default is 9 (open decision OD3): a lab channel
#: post lands in the middle of people's morning, a DM opens it.
DEFAULT_TIMEZONE = "America/New_York"
DEFAULT_USER_SEND_HOUR = 8
DEFAULT_LAB_SEND_HOUR = 9


def normalise_cadence(value: str | None) -> str:
    """A stored cadence, or :data:`CADENCE_DAILY` when it is missing or unknown.

    Daily is the default (plan D1) and also the conservative fallback: it is what
    every existing row has been *receiving*, whatever it stored, so a target whose
    watch row has not been written yet keeps the experience it already had.
    """
    text = (value or "").strip().casefold()
    return CADENCE_WEEKLY if text == CADENCE_WEEKLY else CADENCE_DAILY


def push_kinds(
    cadence: str | None,
    local_date: date,
    *,
    urgent_opt_in: bool = False,
) -> set[str]:
    """What may be pushed to Discord for this cadence on this local date.

    An empty set means "nothing leaves the building today", which is a complete
    answer and not a failure — the web report was still written.

    ``local_date`` is the **recipient's** local date, not the server's. A target in
    UTC+11 is already on Monday while the run host is still on Sunday, and the
    weekly is a Monday-morning artefact in the reader's week, not the server's.
    """
    if normalise_cadence(cadence) == CADENCE_DAILY:
        # Daily means daily. The weekend is not an exception, and Monday is not
        # one either — a daily subscriber never receives the weekly.
        return {DAILY}
    if local_date.weekday() == MONDAY:
        return {WEEKLY}
    # Weekly cadence, between Mondays: silent unless they asked to hear about a
    # deadline that moved (OD2).
    return {URGENT} if urgent_opt_in else set()


def user_cadence(user) -> str:
    return normalise_cadence(getattr(getattr(user, "watch", None), "cadence", None))


def lab_cadence(lab) -> str:
    return normalise_cadence(getattr(getattr(lab, "watch", None), "cadence", None))


def user_urgent_alerts(user) -> bool:
    """Whether this person opted into between-Monday urgent alerts (OD2).

    Only meaningful on weekly cadence — a daily-cadence reader already hears about
    a moved deadline in the next morning's daily, so raising a second message for
    it would be the same news twice.
    """
    watch = getattr(user, "watch", None)
    return bool(getattr(watch, "urgent_alerts", False))


def zone_for(name: str | None) -> ZoneInfo:
    """An IANA zone, falling back to Eastern rather than raising.

    A bad zone name must not stop a report: the cost of the fallback is a send an
    hour or two off for one person, and the cost of the exception is that nobody in
    the batch after them gets anything at all.
    """
    try:
        return ZoneInfo(name or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def _schedule_for(target) -> tuple[ZoneInfo, int]:
    """``(zone, local send hour)`` for a user or a lab.

    A lab keeps its hour and zone on :class:`~apps.accounts.models.Lab` itself,
    where the reminder scheduler already reads them; a person keeps theirs on their
    watch row, which is where every other delivery preference of theirs lives.
    """
    from apps.accounts.models import Lab

    if isinstance(target, Lab):
        hour = getattr(target, "send_hour_local", None)
        return (
            zone_for(getattr(target, "timezone", None)),
            DEFAULT_LAB_SEND_HOUR if hour is None else int(hour),
        )
    watch = getattr(target, "watch", None)
    hour = getattr(watch, "send_hour_local", None)
    return (
        zone_for(getattr(watch, "timezone", None)),
        DEFAULT_USER_SEND_HOUR if hour is None else int(hour),
    )


def local_today(target, *, now: datetime | None = None) -> date:
    """The target's own current date — what :func:`push_kinds` must be asked about."""
    now = now or timezone.now()
    zone, _hour = _schedule_for(target)
    return now.astimezone(zone).date()


def send_time(target, local_date: date) -> datetime:
    """When today's push should reach ``target`` — an aware UTC instant.

    Handed to ``enqueue_*(not_before=…)``, which sets the ``next_attempt_at`` the
    drain already filters on. A send hour in the past is returned as-is rather than
    clamped: :func:`apps.integrations.services.resolve.enqueue_outbox` treats a past
    ``not_before`` as due immediately, so a run that finishes after the recipient's
    morning delivers at once instead of holding a finished report for a day.

    Day-granular, like the reminder scheduler: the hour is a local wall-clock hour,
    so it stays 8am across a daylight-saving boundary rather than drifting.
    """
    zone, hour = _schedule_for(target)
    hour = min(max(hour, 0), 23)
    return datetime.combine(local_date, time(hour=hour), tzinfo=zone).astimezone(UTC)


# --------------------------------------------------------------------------- #
# Dedupe keys
# --------------------------------------------------------------------------- #
#: Every Discord post Mylo makes is idempotent on its dedupe key (invariant 11),
#: which the outbox enforces as a uniqueness constraint rather than an application
#: check. The existing three keys are reproduced here verbatim — changing one would
#: re-send today's report to everyone who already has it — and the weekly's two are
#: new. Built in one place so a producer cannot invent a near-miss spelling.
DAILY_REPORT_KEY = "daily_report:{target}:{on}"
WEEKLY_REPORT_KEY = "weekly_report:{target}:{on}"
LAB_DIGEST_KEY = "lab_digest:{target}:{on}"
LAB_REPORT_KEY = "lab_report:{target}:{on}"
LAB_WEEKLY_KEY = "lab_weekly:{target}:{on}"
URGENT_ALERT_KEY = "urgent_alert:{target}:{subject}"


def _on(value: date) -> str:
    return value.isoformat()


def daily_report_key(user, on: date) -> str:
    return DAILY_REPORT_KEY.format(target=user.id, on=_on(on))


def weekly_report_key(user, on: date) -> str:
    """Keyed on the **Monday** the week starts, not the day it was compiled.

    A weekly re-run on Tuesday after a Monday outage must re-find Monday's row
    rather than queue a second copy of the same week.
    """
    return WEEKLY_REPORT_KEY.format(target=user.id, on=_on(on))


def lab_digest_key(lab, on: date) -> str:
    return LAB_DIGEST_KEY.format(target=lab.id, on=_on(on))


def lab_report_key(lab, on: date) -> str:
    return LAB_REPORT_KEY.format(target=lab.id, on=_on(on))


def lab_weekly_key(lab, on: date) -> str:
    return LAB_WEEKLY_KEY.format(target=lab.id, on=_on(on))


def urgent_alert_key(user, subject: str) -> str:
    """One urgent alert per (person, subject) forever — never per day.

    The subject is the alert's own identity (item and trigger), so a deadline that
    moves twice raises two alerts and a deadline that is re-read every night raises
    one.
    """
    return URGENT_ALERT_KEY.format(target=user.id, subject=subject)
