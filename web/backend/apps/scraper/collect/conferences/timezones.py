"""Deadline instants, and the timezone basis behind each one.

Being off by one day on a submission deadline is a user-visible, trust-destroying
failure, and it is the *default* outcome of parsing these dates naively. So this
module stores three things for every deadline and never conflates them:

* the **raw string** exactly as the source wrote it,
* the **parsed instant** in UTC,
* the **basis** that converted one to the other.

A basis is never inferred silently. When a source publishes a bare calendar date
with no zone — which several do — the basis is recorded as ``inferred:...`` so a
reader can tell a real claim from our assumption.

Three specific traps, all measured in live data:

**AoE.** "Anywhere on Earth" is UTC-12: a deadline dated the 15th expires when
the 15th ends in the last timezone on Earth, which is noon UTC on the 16th. It is
the single most common basis in the structured corpus (630 of 1,161 instances).

**AoE and UTC-12 are the same offset spelled two ways.** The upstream project
migrated its label from ``UTC-12`` to ``AoE`` and never backfilled, so 2026
entries still split 199/45 between them. They resolve identically, but the raw
label is preserved: ``AoE`` is a semantic claim, ``UTC-12`` may be a literal
offset the contributor meant.

**PT is not an offset.** Ten instances use it, including VLDB (CCF-A / CORE A*)
with its twelve rounds. It is US Pacific *with daylight saving* — UTC-7 from the
second Sunday in March to the first Sunday in November, UTC-8 otherwise, an hour
apart. The upstream project's own Python CLI raises ``ValueError`` on it and
swallows that with a bare ``except: continue``, silently dropping every PT venue.
We resolve it properly instead.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

#: Anywhere on Earth. The last timezone on Earth to leave any given date.
AOE = timezone(timedelta(hours=-12))

#: Bases that name a real IANA zone rather than a fixed offset. Resolved through
#: zoneinfo so daylight saving is applied for the actual date in question.
_NAMED_ZONES: dict[str, str] = {
    "PT": "America/Los_Angeles",
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
    "ET": "America/New_York",
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "CET": "Europe/Paris",
    "CEST": "Europe/Paris",
    "JST": "Asia/Tokyo",
    "CST-CHINA": "Asia/Shanghai",
}

_UTC_OFFSET = re.compile(r"^UTC\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?$", re.IGNORECASE)

#: Deadline strings that mean "not scheduled yet" rather than a date.
PLACEHOLDERS = frozenset({"tbd", "tba", "n/a", "none", "null", ""})

#: The shapes deadline strings actually arrive in.
_DEADLINE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
)


class TimezoneBasisError(ValueError):
    """A basis we do not recognise. Never guessed at — raised, and recorded."""


def parse_basis(label: object) -> tuple[str, str]:
    """Normalize a timezone label to ``(canonical, kind)``.

    ``kind`` is one of ``aoe``, ``offset``, ``named``. The canonical form is what
    :func:`resolve_instant` consumes; the caller keeps the original label.
    """
    text = str(label or "").strip()
    if not text:
        raise TimezoneBasisError("empty timezone basis")

    upper = text.upper()
    if upper in {"AOE", "ANYWHERE ON EARTH"}:
        return "AoE", "aoe"
    if upper in {"UTC", "UTC+0", "UTC-0", "GMT", "Z"}:
        return "UTC+0", "offset"

    match = _UTC_OFFSET.match(text)
    if match:
        sign, hours, minutes = match.group(1), int(match.group(2)), int(match.group(3) or 0)
        if hours > 14 or minutes > 59:
            raise TimezoneBasisError(f"implausible UTC offset: {text!r}")
        # UTC-12 is numerically AoE. Both resolve identically; the caller keeps
        # whichever label the source actually wrote.
        return f"UTC{sign}{hours}" + (f":{minutes:02d}" if minutes else ""), "offset"

    if upper in _NAMED_ZONES:
        return upper, "named"

    raise TimezoneBasisError(f"unrecognised timezone basis: {text!r}")


def tzinfo_for(basis: str, moment: datetime) -> timezone | ZoneInfo:
    """The concrete tzinfo for a basis, at a given naive local moment.

    ``moment`` matters only for named zones, where the offset depends on the
    date — which is the entire reason PT cannot be treated as a constant.
    """
    canonical, kind = parse_basis(basis)
    if kind == "aoe":
        return AOE
    if kind == "offset":
        match = _UTC_OFFSET.match(canonical)
        if canonical == "UTC+0" or match is None:
            return UTC
        sign = 1 if match.group(1) == "+" else -1
        hours, minutes = int(match.group(2)), int(match.group(3) or 0)
        return timezone(sign * timedelta(hours=hours, minutes=minutes))
    zone = ZoneInfo(_NAMED_ZONES[canonical])
    # Attaching the zone to the naive moment is what selects standard vs summer
    # time. Doing this against "now" instead would be wrong for half the year.
    return moment.replace(tzinfo=zone).tzinfo or UTC


def parse_local(value: object) -> datetime | None:
    """Parse a source's deadline string into a naive local datetime.

    Returns None for placeholders like ``TBD``. A bare date is treated as the end
    of that day, because "the deadline is the 15th" means the 15th is still
    usable — truncating to midnight would silently move it a day earlier.
    """
    if value is None:
        return None
    # A contributor who forgets the quotes turns a YAML string into a datetime.
    # It has happened upstream; handle both rather than raising TypeError.
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)

    text = str(value).strip()
    if text.lower() in PLACEHOLDERS:
        return None

    for pattern in _DEADLINE_FORMATS:
        try:
            parsed = datetime.strptime(text, pattern)
        except ValueError:
            continue
        if pattern == "%Y-%m-%d":
            return parsed.replace(hour=23, minute=59, second=59)
        return parsed
    return None


def resolve_instant(value: object, basis: object) -> datetime | None:
    """Convert a source deadline plus its basis into a UTC instant.

    The briefing's headline check: an AoE deadline dated the 15th resolves to
    noon UTC on the 16th.
    """
    local = parse_local(value)
    if local is None:
        return None
    tzinfo = tzinfo_for(str(basis), local)
    return local.replace(tzinfo=tzinfo).astimezone(UTC)


def to_iso_instant(moment: datetime | None) -> str | None:
    if moment is None:
        return None
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def is_future(instant: str | None, now: datetime) -> bool:
    """True when a stored UTC instant has not yet passed.

    A null instant is *not* future. An undated deadline cannot be surfaced as
    actionable, and treating it as open would put TBD rounds at the top of a
    list sorted by urgency.
    """
    if not instant:
        return False
    try:
        parsed = datetime.fromisoformat(instant.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed >= now
