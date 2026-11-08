"""society_pages: one hand-maintained "Dates and Deadlines" page per society per
year, the richest non-CS deadline data found anywhere in the whole survey.

**Why this exists.** Every other society source in this codebase is a
*calendar*, keyed on event date -- so by the time a meeting is "upcoming" any
deadline it happens to mention has already closed (see ``ams_mathcal.py``'s
88-events-2-mentioned-both-past measurement). A "Dates and Deadlines" page is
the opposite shape: organisers write it *as* a deadline list, typed and
multi-round, because it is the page their own members use to plan a
submission. SfN's page carries 4 tables, ~12 typed rows, a regular round and a
late-breaking round, with explicit local timezones ("2 p.m. EDT", "5 p.m.
EST") -- structurally the same richness as ``ccf_deadlines``, just outside CS.

**Registry, not discovery.** There is no crawlable index of "societies with a
dates page" -- each one is found by a human, once, and the URL, acronym and
year are checked into ``society_registry.json`` alongside the date the row was
verified reachable. A registry row whose URL rotated silently between visits
is worse than no row: it reports a healthy fetch and returns nothing. Better
three verified rows than ten guessed ones.

**Three fetch modes, because the pages don't all forgive a plain GET.** SfN's
page is server-rendered and answers a polite ``PoliteClient`` directly
(``mode="http"``). Two other rows in the registry -- ISMRM, AIAA AVIATION --
are JS-heavy landing pages where recon found no typed table in the plain-HTTP
payload; they are seeded anyway, with that honestly recorded, as the reason
``mode="captured"`` (read an ``*.html`` a human saved from their own browser,
zero network) exists as the universal fallback, and ``mode="browser"``
(optional Playwright render) exists for anything captured mode can't cover
either. Never spoof a User-Agent to get past a wall meant to keep bots out --
if a host refuses the honest ``PoliteClient`` UA, that row is ``captured`` or
``browser``, not a fight.

**Parsing is generic, not per-society.** One regex-based table walker handles
every registry row: pull (date-cell text, label text, optional time-and-zone
text) out of every ``<table>``/``<tr>``, classify the label into a
``Deadline`` kind, and refuse to guess on the three traps SfN's own page
contains for free -- "submission opens" is a window opening, not a deadline;
"Early August" is not a specific day; "November 14-18 | ... meeting dates" is
the event, not a deadline.
"""

from __future__ import annotations

import importlib.util
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from tools.retrieval.collect.conferences.adapters.base import BaseConferenceAdapter
from tools.retrieval.collect.conferences.record import (
    ConferenceInstance,
    ConferenceSeries,
    Deadline,
)
from tools.retrieval.collect.conferences.timezones import (
    TimezoneBasisError,
    resolve_instant,
    to_iso_instant,
)
from tools.retrieval.collect.core.http import FetchError, PoliteClient
from tools.retrieval.collect.core.rawstore import RawBundle, new_run_id, utc_now
from tools.retrieval.collect.core.text import (
    clean_text,
    dedupe_preserving_order,
    html_to_text,
)

REGISTRY_PATH = Path(__file__).parent / "society_registry.json"
DEFAULT_CAPTURE_DIR = Path("data/collect/captures/society_pages")

LICENSE = "site content; per-society terms"

#: One request per registry row. A society's own site is a smaller, more
#: fragile host than a CDN-backed aggregator -- SfN's real page measures
#: 158,996 bytes; anything dramatically smaller is a soft-404 or a bot-wall
#: interstitial (see ``PoliteClient._validate``'s SPIE/ieee.org/sfn.org note),
#: not the page.
MIN_PAGE_BYTES = 20_000

#: What ``available()`` says when Playwright is not installed. Named here so
#: the test asserting the message and the message itself cannot drift apart.
BROWSER_EXTRA_HINT = "install the optional 'browser' extra: pip install '.[browser]'"

_MODES = ("http", "captured", "browser")


# --- table extraction (stdlib only: re + html, no beautifulsoup4/lxml) ----

_TABLE_BLOCK = re.compile(r"<table\b[^>]*>(.*?)</table>", re.IGNORECASE | re.DOTALL)
_TR_BLOCK = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_CELL_BLOCK = re.compile(r"<(?:td|th)\b[^>]*>(.*?)</(?:td|th)>", re.IGNORECASE | re.DOTALL)
_LI_BLOCK = re.compile(r"<li\b[^>]*>(.*?)</li>", re.IGNORECASE | re.DOTALL)

#: A row whose label names the meeting itself, not a deadline -- SfN's own
#: example: "November 14-18 | Neuroscience 2026 meeting dates". These must
#: never become a ``Deadline``; they feed ``event_dates_text`` instead.
_EVENT_DATE_LABEL = re.compile(r"\bmeeting dates\b", re.IGNORECASE)

#: "Submission opens" (or "registration opens", "... opens at noon EDT") names
#: a window *opening*, not a deadline. Skipped outright, per the briefing --
#: except for the rebuttal/author-response family, where "opens" is itself a
#: real, distinct kind (``rebuttal_open``) rather than a trap to avoid.
_OPENS = re.compile(r"\bopen(?:s|ing)?\b", re.IGNORECASE)
_REBUTTAL_WORD = re.compile(r"\brebuttal\b|\bauthor response\b", re.IGNORECASE)

#: Zone tokens this source actually writes, restricted to ``timezones.py``'s
#: own recognised vocabulary so every basis this module ever emits is one
#: ``resolve_instant`` can actually resolve. Ordered longest-first so "EST"
#: is not swallowed by a looser "ET"-shaped pattern (moot with \b, but kept
#: explicit because a future addition could break that invariant silently).
_ZONE_TOKEN = re.compile(r"\b(EST|EDT|ET|PST|PDT|PT|CEST|CET|JST|AOE|UTC)\b")

#: "2 p.m." / "2:00 p.m." / "11:59 p.m." / "noon" / "midnight".
_CLOCK_TIME = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?\b", re.IGNORECASE
)
_NOON = re.compile(r"\bnoon\b", re.IGNORECASE)
_MIDNIGHT = re.compile(r"\bmidnight\b", re.IGNORECASE)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}
_MONTH_ALT = "|".join(_MONTHS)
#: "September 15", "September 15,", trailing punctuation stripped upstream.
_SINGLE_DAY = re.compile(rf"^({_MONTH_ALT})\s+(\d{{1,2}})$", re.IGNORECASE)
#: "November 14-18" -- a range. First day is the meeting's start, not a
#: deadline in its own right; kept only so the event-dates row can still
#: report a month for the year-inference check below.
_DAY_RANGE = re.compile(rf"^({_MONTH_ALT})\s+(\d{{1,2}})\s*[-–—]\s*(\d{{1,2}})$", re.IGNORECASE)
#: "Early August", "Late September", "Mid-October" -- a real month, deliberately
#: no specific day. Must never become an instant (briefing's explicit trap).
_VAGUE_MONTH = re.compile(rf"^(early|mid|late)[- ]?({_MONTH_ALT})$", re.IGNORECASE)

#: Longest/most specific phrase first so "camera-ready" never falls through to
#: the looser "submission" rule below it. The abstract rule is deliberately a
#: *contiguous phrase* match ("abstract submission", "abstract deadline") --
#: not "abstract" and "deadline" merely co-occurring anywhere in the sentence
#: -- because SfN's own page has two administrative rows that mention both
#: words without being an abstract deadline at all ("Deadline for abstract
#: presenters to switch from virtual-only to in-person presentation"). A
#: looser co-occurrence rule misclassifies exactly those as "abstract".
_KIND_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # Commercial participation, matched *first* because these rows are worded
    # exactly like author deadlines. SfN alone carries three: "Exhibit
    # Application Submission Closes (Group A)", the same for Group B, and "Art
    # of Neuroscience application submission closes". Only `abstract` and
    # `submission` decide whether a venue reads as open, so classifying a booth
    # application as a submission tells an author the call is open months after
    # the paper deadline passed -- the same class of error as filtering on the
    # event date.
    (
        re.compile(
            r"exhibit|booth|sponsor|advertis|vendor|housing|hotel|travel award|"
            r"art of |volunteer",
            re.IGNORECASE,
        ),
        "registration",
    ),
    (re.compile(r"camera[- ]?ready|final version|final manuscript", re.IGNORECASE), "camera_ready"),
    (re.compile(r"notif|acceptance status", re.IGNORECASE), "notification"),
    (re.compile(r"\bregistration\b|early[- ]bird", re.IGNORECASE), "registration"),
    (re.compile(r"\babstract\s+(?:submission|deadline)\b", re.IGNORECASE), "abstract"),
    (re.compile(r"\b(submission|paper|proposal|manuscript)s?\b", re.IGNORECASE), "submission"),
)

#: Distinguishing words the briefing calls out by name. Matched as substrings
#: of the lower-cased label and stored verbatim in ``Deadline.round_label``.
_ROUND_HINTS = ("late-breaking", "extended")


@dataclass(frozen=True)
class SocietyRegistryRow:
    """One checked-in registry entry: one page, one society, one year."""

    society: str
    conference: str
    acronym: str
    year: int
    url: str
    discipline: str = ""
    country: str = ""
    event_dates: str = ""
    notes: str = ""
    #: Pins this row to one fetch mode, overriding the adapter default. A row
    #: whose deadline table is not in the plain HTTP payload belongs on
    #: ``captured`` — otherwise it fetches cleanly and contributes nothing,
    #: which is indistinguishable from a working source with no open calls.
    mode: str = ""

    @property
    def key(self) -> str:
        """``<registry-key>`` -- the filename ``captured`` mode reads."""
        return _slug(f"{self.acronym}-{self.year}")

    @property
    def series_key(self) -> str:
        return f"gen:society:{_slug(self.acronym)}"


class SocietyPagesAdapter(BaseConferenceAdapter):
    name = "society_pages"
    #: The society's own maintained page, not a transcription.
    venue_native = True
    phase = 4
    license = LICENSE

    def __init__(
        self,
        mode: str = "http",
        *,
        capture_dir: Path | str | None = None,
        registry_path: Path | str | None = None,
    ) -> None:
        if mode not in _MODES:
            raise ValueError(f"unknown mode: {mode!r}, expected one of {_MODES}")
        self.mode = mode
        self.capture_dir = Path(capture_dir) if capture_dir is not None else DEFAULT_CAPTURE_DIR
        self.registry_path = Path(registry_path) if registry_path is not None else REGISTRY_PATH

    # -- contract -----------------------------------------------------

    def available(self) -> tuple[bool, str]:
        if self.mode == "browser":
            if importlib.util.find_spec("playwright") is None:
                return False, f"playwright not installed -- {BROWSER_EXTRA_HINT}"
            return True, ""
        return True, ""

    def fetch(self, client: PoliteClient, *, limit: int | None = None) -> RawBundle:
        """One request per registry row (http mode); zero for the others.

        A per-row fetch failure never sinks the run -- it is recorded in
        ``meta["fetch_warnings"]`` and that row is simply absent from
        ``records``, the same degrade-gracefully contract ``ccf_deadlines``
        applies to its optional ``types.yml`` fetch.
        """
        rows = load_registry(self.registry_path)
        if limit is not None:
            rows = rows[:limit]

        records: list[dict[str, Any]] = []
        warnings: list[str] = []
        for row in rows:
            try:
                html = self._fetch_one(client, row)
            except FetchError as exc:
                warnings.append(f"{row.key}: {exc}")
                continue
            if html is None:
                warnings.append(f"{row.key}: no {self.mode} payload available")
                continue
            records.append({**_row_to_dict(row), "key": row.key, "html": html})

        return self.bundle(
            self.name, new_run_id(), utc_now(), records,
            mode=self.mode, fetch_warnings=warnings,
        )

    def parse(
        self, bundle: RawBundle
    ) -> tuple[list[ConferenceSeries], list[ConferenceInstance]]:
        series_by_key: dict[str, ConferenceSeries] = {}
        instances: list[ConferenceInstance] = []

        for record in bundle.records:
            if not isinstance(record, dict) or not record.get("html"):
                continue
            row = _dict_to_row(record)
            instance = self._parse_page(row, record["html"])
            instances.append(instance)
            series_by_key.setdefault(
                row.series_key,
                ConferenceSeries(
                    series_key=row.series_key,
                    acronym=row.acronym,
                    full_name=row.conference,
                    field_codes=[row.discipline] if row.discipline else [],
                    contributing_sources=[self.name],
                    license=self.license,
                ),
            )

        return list(series_by_key.values()), instances

    # -- fetch modes ----------------------------------------------------

    def _fetch_one(self, client: PoliteClient, row: SocietyRegistryRow) -> str | None:
        # A row may pin its own mode. Two seeded rows are reachable over HTTP
        # but do not expose a deadline table in the plain payload, so fetching
        # them over HTTP produces a record with no deadlines and no warnings —
        # a silent nothing that looks like a healthy fetch. Honest prose in
        # `notes` is not enforceable state; the mode is.
        mode = row.mode or self.mode
        if mode == "http":
            response = client.get(
                row.url,
                min_bytes=MIN_PAGE_BYTES,
                # Same reasoning as the WikiCFP guard: a byte floor alone is
                # cleared by any bot wall or redesigned page. The parser reads
                # tables, so require one — a site-wide failure then reports
                # itself instead of reading as "no deadlines today".
                expect=lambda body: b"<table" in body.lower(),
            )
            return response.text()
        if mode == "captured":
            path = self.capture_dir / f"{row.key}.html"
            if not path.exists():
                return None
            return path.read_text(encoding="utf-8")
        # mode == "browser"
        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason)
        return _render_with_playwright(row.url)

    # -- parse internals --------------------------------------------------

    def _parse_page(self, row: SocietyRegistryRow, page_html: str) -> ConferenceInstance:
        rows = _extract_rows(page_html)
        event_month = _month_from_text(row.event_dates)

        deadlines: list[Deadline] = []
        warnings: list[str] = []
        event_dates_text = row.event_dates
        # Some rows appear verbatim in two tables on one page (SfN repeats its
        # exhibitor housing deadline), which would otherwise emit the same
        # deadline twice.
        seen_rows: set[tuple[str, str]] = set()

        for date_text, label_text in rows:
            if (date_text, label_text) in seen_rows:
                continue
            seen_rows.add((date_text, label_text))

            if _EVENT_DATE_LABEL.search(label_text):
                # The meeting's own dates, never a deadline. Prefer the
                # page's own words over the registry's if the page has them.
                if date_text:
                    event_dates_text = f"{date_text}, {row.year}"
                continue

            if _is_window_opening(label_text):
                # "Submission opens" / "registration opens" -- a window
                # opening, not a deadline. The briefing is explicit that this
                # must never become ``kind="submission"``; skipping it
                # outright (rather than emitting an ``unknown`` no-op record)
                # keeps the deadline list free of non-deadline noise.
                continue

            deadline, row_warnings = _build_deadline(
                date_text, label_text, row.year, event_month, self.name
            )
            deadlines.append(deadline)
            warnings.extend(row_warnings)

        _disambiguate_identities(deadlines)
        deadlines.sort(key=lambda d: (d.instant or "9999", d.kind))

        return ConferenceInstance(
            source=self.name,
            source_record_id=row.key,
            series_key=row.series_key,
            record_kind="conference",
            title=row.conference,
            acronym=row.acronym,
            year_label=str(row.year),
            event_dates_text=event_dates_text,
            country_code=row.country,
            url=row.url,
            source_url=row.url,
            topics=[row.discipline] if row.discipline else [],
            deadlines=deadlines,
            quality_warnings=dedupe_preserving_order(warnings),
            contributing_sources=[self.name],
            license=self.license,
            raw={"society": row.society, "notes": row.notes},
        )


# --- registry --------------------------------------------------------------


def load_registry(path: Path) -> list[SocietyRegistryRow]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path}: expected a JSON array of registry rows")
    return [_dict_to_row(row) for row in payload]


def _row_to_dict(row: SocietyRegistryRow) -> dict[str, Any]:
    return {
        "society": row.society, "conference": row.conference, "acronym": row.acronym,
        "year": row.year, "url": row.url, "discipline": row.discipline,
        "country": row.country, "event_dates": row.event_dates, "notes": row.notes,
    }


def _dict_to_row(payload: dict[str, Any]) -> SocietyRegistryRow:
    return SocietyRegistryRow(
        society=clean_text(payload.get("society")),
        conference=clean_text(payload.get("conference")),
        acronym=clean_text(payload.get("acronym")),
        year=int(payload["year"]),
        url=clean_text(payload.get("url")),
        discipline=clean_text(payload.get("discipline")),
        country=clean_text(payload.get("country")),
        event_dates=clean_text(payload.get("event_dates")),
        notes=clean_text(payload.get("notes")),
    )


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# --- browser mode: Playwright is an optional extra, imported nowhere else --


def _render_with_playwright(url: str) -> str:
    """Render ``url`` with a real browser and return the DOM's HTML.

    Imported here, and only here, so a plain ``import society_pages`` never
    requires Playwright to be installed at all -- ``available()`` is the
    gate, this is what it gates.
    """
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(url, wait_until="networkidle")
            return page.content()
        finally:
            browser.close()


# --- generic table walker ---------------------------------------------------


def _extract_rows(page_html: str) -> list[tuple[str, str]]:
    """Every (date-cell text, item text) pair across every ``<table>`` on the
    page, one entry per ``<li>`` (or per cell, where the source writes a
    plain sentence instead of a list) -- SfN writes several deadlines under
    one shared date cell, e.g. three ``<li>`` under "October 5", and each is
    a distinct candidate deadline sharing that one date.
    """
    pairs: list[tuple[str, str]] = []
    for table_html in _TABLE_BLOCK.findall(page_html):
        for tr_html in _TR_BLOCK.findall(table_html):
            cells = _CELL_BLOCK.findall(tr_html)
            if len(cells) < 2:
                continue
            date_text = clean_text(html_to_text(cells[0]))
            if not date_text:
                continue
            content_html = cells[1]
            items = _LI_BLOCK.findall(content_html)
            item_texts = (
                [clean_text(html_to_text(item)) for item in items]
                if items
                else [clean_text(html_to_text(content_html))]
            )
            for item_text in item_texts:
                if item_text:
                    pairs.append((date_text, item_text))
    return pairs


def _is_window_opening(label_text: str) -> bool:
    if _REBUTTAL_WORD.search(label_text):
        # Opening a rebuttal/author-response period is itself a real,
        # distinct kind (``rebuttal_open``), not a non-deadline to skip.
        return False
    return bool(_OPENS.search(label_text))


def _classify_kind(label_text: str) -> str:
    lowered = label_text
    if _REBUTTAL_WORD.search(lowered):
        return "rebuttal_open" if _OPENS.search(lowered) else "rebuttal_close"
    for pattern, kind in _KIND_RULES:
        if pattern.search(lowered):
            return kind
    return "unknown"


def _round_label(label_text: str) -> str:
    lowered = label_text.lower()
    for hint in _ROUND_HINTS:
        if hint in lowered:
            return hint
    return ""


def _extract_zone(label_text: str) -> str:
    match = _ZONE_TOKEN.search(label_text)
    return match.group(1) if match else ""


def _extract_clock_time(label_text: str) -> tuple[int, int] | None:
    if _NOON.search(label_text):
        return 12, 0
    if _MIDNIGHT.search(label_text):
        return 0, 0
    match = _CLOCK_TIME.search(label_text)
    if not match:
        return None
    hour = int(match.group(1)) % 12
    minute = int(match.group(2) or 0)
    if match.group(3).lower() == "p":
        hour += 12
    return hour, minute


def _month_from_text(text: str) -> int | None:
    if not text:
        return None
    match = re.search(_MONTH_ALT, text, re.IGNORECASE)
    return _MONTHS.get(match.group(0).lower()) if match else None


def _parse_date_cell(date_text: str, year: int) -> tuple[str | None, int | None]:
    """(iso_date, month). ``iso_date`` is only set for a single, specific
    calendar day -- a range or a vague qualifier reports its month (for the
    year-inference check) but never a day, which is the whole point of the
    "Early August must not become an instant" guard downstream.
    """
    text = date_text.strip()

    single = _SINGLE_DAY.match(text)
    if single:
        month = _MONTHS[single.group(1).lower()]
        day = int(single.group(2))
        # f-string int formatting never validates a calendar day, so building
        # the string and hoping is dead code: "February 30" yields
        # "2026-02-30", which then raises out of strptime further down and
        # takes every other registry row with it. These are hand-maintained
        # pages; a typo is exactly the input this has to survive.
        try:
            return date(year, month, day).isoformat(), month
        except ValueError:
            return None, month

    day_range = _DAY_RANGE.match(text)
    if day_range:
        month = _MONTHS[day_range.group(1).lower()]
        return None, month  # a range is the event span, never a single deadline day

    vague = _VAGUE_MONTH.match(text)
    if vague:
        month = _MONTHS[vague.group(2).lower()]
        return None, month

    return None, None


def _disambiguate_identities(deadlines: list[Deadline]) -> None:
    """Make every entry's ``(kind, round_label)`` unique, touching only clashes.

    Deadline identity is what ``store.merge_deadlines`` matches on, so two
    entries sharing one identity means the second run treats the second as an
    *extension* of the first: one is overwritten, the other destroyed, and the
    record never settles to ``unchanged``.

    These pages repeat a label across days as a matter of course — SfN lists
    "Badge pickup on-site" on five consecutive dates and "Exhibitor Move-Out" on
    two. Only the clashing entries are touched, so a label that was already
    unique keeps its clean name, and the date is what separates them because the
    date is genuinely what differs.
    """
    seen: dict[tuple[str, str], int] = {}
    for deadline in deadlines:
        identity = deadline.identity
        count = seen.get(identity, 0)
        seen[identity] = count + 1
        if count == 0:
            continue
        # Prefer the row's own date; fall back to an ordinal if even that
        # repeats, so this can never leave two entries sharing an identity.
        marker = (deadline.raw.split(":", 1)[0] or f"#{count + 1}").strip()
        deadline.round_label = clean_text(f"{deadline.round_label} [{marker}]")[:120]
        if deadline.identity in seen:
            deadline.round_label = clean_text(
                f"{deadline.round_label} #{count + 1}"
            )[:120]
        seen[deadline.identity] = 1


def _build_deadline(
    date_text: str, label_text: str, year: int, event_month: int | None, source: str
) -> tuple[Deadline, list[str]]:
    warnings: list[str] = []
    kind = _classify_kind(label_text)
    raw = clean_text(f"{date_text}: {label_text}")

    # A deadline's identity is (kind, round_label), and store.merge_deadlines
    # matches on it. These pages carry dozens of rows that share a kind --
    # SfN's live page yields 56 deadlines across only 7 (kind, "") pairs -- so
    # without a distinguishing label the second store run treats each as an
    # *extension* of the last: entries are overwritten, others destroyed, and
    # one row reached extension_count=15, which this codebase documents as a
    # predatory red flag. Exactly the defect fixed in miccai, in a different
    # adapter. The row's own label is what distinguishes it, so it is the round.
    round_label = _round_label(label_text) or clean_text(label_text)[:80]

    iso_date, month = _parse_date_cell(date_text, year)

    if month is not None and event_month is not None and month > event_month:
        # A naive reader might assume a month numerically before the event
        # month rolls to *next* year (the briefing's explicit warning); the
        # opposite case -- a month genuinely *after* the meeting -- is the one
        # that is actually ambiguous, so it is the one flagged rather than
        # silently kept at ``year``.
        warnings.append(
            f"{date_text!r} falls after the event month; year kept as {year} "
            "without confirmation"
        )

    zone = _extract_zone(label_text)

    if iso_date is None:
        # Either no day-level date at all, or an explicit range/vague
        # qualifier ("Early August", "November 14-18"). Never fabricate an
        # instant for either.
        # Deliberately *not* `zone or ...`. The zone is read from the label
        # while the date is read from the cell, so a row whose label happens to
        # repeat "EST" would claim a real timezone basis while carrying no
        # instant at all -- and store._downgrades_basis reads a real basis as
        # more trustworthy than an inferred one. Two identically-shaped rows
        # ended up with different bases purely on label wording.
        basis = "inferred:date-only"
        warnings.append(f"non-specific date, no instant recorded: {date_text!r}")
        return Deadline(
            kind=kind, raw=raw, instant=None, basis=basis,
            round_label=round_label, source=source,
        ), warnings

    if zone:
        clock = _extract_clock_time(label_text)
        value = f"{iso_date} {clock[0]:02d}:{clock[1]:02d}:00" if clock else iso_date
        try:
            instant = to_iso_instant(resolve_instant(value, zone))
            basis = zone
        except TimezoneBasisError:
            instant = None
            basis = zone
            warnings.append(f"unrecognised timezone basis: {zone!r}")
    else:
        # No zone stated anywhere in the source. Recording an instant here
        # at all is *our* assumption (end of that calendar day, UTC), not a
        # claim the page makes -- which is exactly why the basis reads
        # "inferred:date-only" rather than a real zone name. Mirrors
        # ``miccai._deadline_instant``'s identical call for the same reason.
        basis = "inferred:date-only"
        day = datetime.strptime(iso_date, "%Y-%m-%d")
        instant = to_iso_instant(day.replace(hour=23, minute=59, second=59, tzinfo=UTC))

    return Deadline(
        kind=kind, raw=raw, instant=instant, basis=basis,
        round_label=round_label, source=source,
    ), warnings
