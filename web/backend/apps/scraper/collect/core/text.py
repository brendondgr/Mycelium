"""Pure transformations shared by every collector: dates, HTML, and titles.

No network, no I/O, no clock reads except where a caller passes ``today`` in
explicitly — so every function here is directly testable.

Money parsing deliberately does *not* live here. An award ceiling is a funding
concept; conferences have no equivalent, and a shared module that grows a
domain-specific half stops being shared.
"""

from __future__ import annotations

import html
import json
import re
from datetime import date, datetime

# --- dates ---------------------------------------------------------------

#: Every shape the sources actually emit, probed rather than guessed.
_DATE_PATTERNS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%m-%d-%Y",  # NIH IC XML OpenDate, which is *not* ISO despite the dashes
    "%d/%m/%Y",  # only reached when the month slot is impossible
    "%Y-%m-%d-%H-%M-%S",  # Grants.gov *Str fields
    "%b %d, %Y %I:%M:%S %p %Z",  # "Nov 17, 2026 12:00:00 AM EST"
    "%b %d, %Y %I:%M:%S %p",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d %b %Y",
    "%d %B %Y",  # "20 October 2026" — Optica, European society calendars
    "%a, %d %b %Y %H:%M:%S %Z",  # RSS pubDate
    "%a, %d %b %Y %H:%M:%S",
)

_ISO_TZ = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ]")

#: Named US zone abbreviations a federal source might append after a clock
#: time ("Nov 17, 2026 12:00:00 AM EST", an NIH Guide date; an RSS pubDate's
#: trailing zone). Matched explicitly, not with a broad "trailing capitals"
#: pattern, so this can never eat real content — see the note in
#: ``to_iso_date`` about why ``%Z`` alone cannot be trusted to recognize them.
_TRAILING_NAMED_TZ = re.compile(
    r"\s+(?:UTC|GMT|EST|EDT|CST|CDT|MST|MDT|PST|PDT|AST|ADT|AKST|AKDT|HST|HDT)$"
)


def to_iso_date(value: object) -> str | None:
    """Return an ISO 8601 calendar date (YYYY-MM-DD), or None if unparseable.

    This reduces to a *date*, not an instant, and callers keep the original
    string alongside it. Where a source genuinely publishes an instant with a
    timezone basis — which conference deadlines do — that belongs in the
    conferences timezone module, not here.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "n/a", "tbd", "tba", "-"}:
        return None

    # ISO with a time and/or offset — take the date half and stop.
    iso_head = _ISO_TZ.match(text)
    if iso_head:
        return iso_head.group(1)

    # RSS pubDate sometimes carries a trailing offset ("+0000") datetime cannot
    # pair with %Z; strip it. Anchored to a preceding clock time so it cannot eat
    # the year off a bare "01-05-2025".
    text = re.sub(r"(?<=\d:\d\d)\s*[+-]\d{4}$", "", text).strip()

    for pattern in _DATE_PATTERNS:
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue

    # ``%Z`` only recognizes a name that appears in the running process's own
    # `time.tzname` — it is not a fixed table of world zone abbreviations. That
    # is fine standalone, where the host's local zone is whatever it is; it
    # breaks the moment this module runs inside Django, because `django.setup()`
    # calls `time.tzset()` with `TZ=UTC`, which replaces `time.tzname` with
    # `("UTC", "UTC")` and makes every `%b %d, %Y %I:%M:%S %p %Z` pattern above
    # stop matching "... EST" — silently turning a huge share of NIH's and
    # Grants.gov's real dates into ``None``. Not a 3.12-only quirk: reproduced
    # directly by importing this package after ``django.setup()``, which is
    # exactly what happens every time the backend process starts (plan D6 runs
    # this collector in-process, not as a separate interpreter). Retried once
    # more with a known trailing zone name stripped, so parsing this common
    # shape does not depend on which process happens to be asking.
    stripped = _TRAILING_NAMED_TZ.sub("", text).strip()
    if stripped != text:
        for pattern in _DATE_PATTERNS:
            try:
                return datetime.strptime(stripped, pattern).date().isoformat()
            except ValueError:
                continue
    return None


def is_past(iso_day: str | None, today: date) -> bool:
    """True when a date has strictly passed.

    A null date is *not* past — it means "no known deadline", never "expired".
    """
    if not iso_day:
        return False
    try:
        return date.fromisoformat(iso_day) < today
    except ValueError:
        return False


def soonest_future(dates: list[str | None], today: date) -> str | None:
    """The nearest date that has not passed, for recurring cycles."""
    future = []
    for value in dates:
        if not value:
            continue
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            continue
        if parsed >= today:
            future.append(parsed)
    return min(future).isoformat() if future else None


# --- text ----------------------------------------------------------------

_BLOCK_TAGS = r"p|div|br|li|tr|h[1-6]|section|article|blockquote|table|ul|ol|dl|dt|dd"
_SCRIPT = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_LIST_ITEM = re.compile(r"<li\b[^>]*>", re.IGNORECASE)
_BLOCK_OPEN = re.compile(rf"<(?:{_BLOCK_TAGS})\b[^>]*>", re.IGNORECASE)
_BLOCK_CLOSE = re.compile(rf"</(?:{_BLOCK_TAGS})\s*>", re.IGNORECASE)
_ANY_TAG = re.compile(r"<[^>]+>")
_BLANK_RUN = re.compile(r"\n{3,}")
_SPACE_RUN = re.compile(r"[ \t\u00a0]+")


def html_to_text(value: object) -> str:
    """Strip HTML to text while keeping paragraph breaks and list structure.

    Collapsing a CFP body to one line measurably degrades it — the descriptive
    text is the payload this system exists to collect, so structure stays.
    """
    if value is None:
        return ""
    text = str(value)
    if not text.strip():
        return ""

    text = _SCRIPT.sub(" ", text)
    text = _LIST_ITEM.sub("\n- ", text)
    text = _BLOCK_OPEN.sub("\n", text)
    text = _BLOCK_CLOSE.sub("\n", text)
    text = _ANY_TAG.sub("", text)
    text = html.unescape(text)

    lines = [_SPACE_RUN.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return _BLANK_RUN.sub("\n\n", text).strip()


def clean_text(value: object) -> str:
    """Whitespace-collapse a short field (titles, organisation names)."""
    if value is None:
        return ""
    return _SPACE_RUN.sub(" ", str(value).replace("\n", " ")).strip()


def join_description(*parts: object) -> str:
    """Concatenate every long-form field a source offers into one payload."""
    chunks: list[str] = []
    for part in parts:
        text = html_to_text(part)
        if text and text not in chunks:
            chunks.append(text)
    return "\n\n".join(chunks)


def normalize_title(value: object) -> str:
    """Lowercase alphanumeric title, for fuzzy comparison only."""
    text = clean_text(value).lower()
    return re.sub(r"[^a-z0-9 ]+", " ", text).strip()


def dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
