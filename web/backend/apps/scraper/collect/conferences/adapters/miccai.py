"""miccai: the MICCAI Society's "Key Dates" RSS feed, one request.

The only source found in the entire society-and-publisher-calendar survey that
publishes a deadline-first, forward-dated, machine-readable feed. Everything
else in that category is either behind a bot wall (ACM, SIAM, AGU, ...), keyed
on *event* date rather than deadline (so any deadline it mentions has already
passed by the time the event is "upcoming" -- see ``ams_mathcal.py``), or a
structured API that simply omits the date fields (AIAA).

**The whole calendar lives inside one XML tag.** WordPress renders a global
sidebar widget -- ``<aside class="sidemenu">``, ten ``<li>`` entries -- into
*every* Key Dates post's ``content:encoded``, so the first post in the feed
already carries the entire forward-looking list. No REST pagination, no
per-post follow-up.

**Only prefixed items are deadlines.** Each ``<li>`` reads
``<label-or-name> - <Month D, YYYY>``, and most of the ten have *no* label
prefix at all -- those are event dates, not deadlines. Treating the whole list
as deadlines is precisely the design error this codebase exists to avoid (see
``ConferenceInstance``'s docstring on why series/instance/deadline stay apart).
Measured 2026-08-16: 3 of 10 are real deadlines.

See ``docs/conferences/recon/society_calendars.md`` for the full recon.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from typing import Any

from apps.scraper.collect.conferences.adapters.base import BaseConferenceAdapter
from apps.scraper.collect.conferences.record import (
    ConferenceInstance,
    ConferenceSeries,
    Deadline,
)
from apps.scraper.collect.conferences.timezones import to_iso_instant
from apps.scraper.collect.core.http import PoliteClient
from apps.scraper.collect.core.rawstore import RawBundle, new_run_id, utc_now

FEED_URL = "https://miccai.org/category/events/key-dates/feed/"

#: Measured 61,116 bytes for the real 10-item feed. Anything dramatically
#: smaller is a WordPress error page or an empty category, not data.
MIN_FEED_BYTES = 4_000

LICENSE = "site content; Content-Signal use=reference"

_SIDEMENU_BLOCK = re.compile(r'<aside class="sidemenu">(.*?)</aside>', re.DOTALL)
_LI_ANCHOR = re.compile(r'<li>\s*<a href="([^"]+)"[^>]*>(.*?)</a>\s*</li>', re.DOTALL)
_TRAILING_PAREN = re.compile(r"\s*\([^)]*\)\s*$")
_EM_EN_DASH_SPLIT = re.compile(r"\s[–—]\s")
_YEAR_IN_TEXT = re.compile(r"\b(19|20)\d{2}\b")

#: The observed label vocabulary, longest/most-specific pattern first so
#: "Submission deadline extended:" never matches the shorter "Submission
#: deadline:" rule instead. Only these prefixes make an ``<li>`` a deadline --
#: everything else (including labels that merely *contain* a colon, like
#: "Path to Professorship: Insider Perspectives...") is an event date.
_LABEL_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^submission deadline extended:\s*", re.IGNORECASE), "submission"),
    (re.compile(r"^submission deadline:\s*", re.IGNORECASE), "submission"),
    (re.compile(r"^application deadline:\s*", re.IGNORECASE), "submission"),
    (re.compile(r"^applications due:\s*", re.IGNORECASE), "submission"),
    (re.compile(r"^early bird registration deadline:?\s*", re.IGNORECASE), "registration"),
    # Nominating someone else doesn't cleanly gate "is this still open to me",
    # so this is the one label kept as "unknown" rather than "submission" --
    # the label itself is preserved verbatim regardless.
    (re.compile(r"^nomination deadline:\s*", re.IGNORECASE), "unknown"),
)


class MICCAIAdapter(BaseConferenceAdapter):
    name = "miccai"
    # The society's own site, not a third-party transcription.
    venue_native = True
    phase = 4
    license = LICENSE

    def fetch(self, client: PoliteClient, *, limit: int | None = None) -> RawBundle:
        """One request. The raw payload is the feed XML, untouched, so parse
        can be re-run offline over the exact bytes."""
        response = client.get(
            FEED_URL,
            min_bytes=MIN_FEED_BYTES,
            # If MICCAI reskins the site the widget vanishes silently -- a
            # 200 with no "sidemenu" anywhere would otherwise cache as a
            # healthy fetch of zero conferences forever.
            expect=lambda body: b"sidemenu" in body,
        )
        return self.bundle(self.name, new_run_id(), utc_now(), [{"feed_xml": response.text()}], url=FEED_URL)

    def parse(
        self, bundle: RawBundle
    ) -> tuple[list[ConferenceSeries], list[ConferenceInstance]]:
        if not bundle.records or not isinstance(bundle.records[0], dict):
            return [], []
        feed_xml = bundle.records[0].get("feed_xml", "")

        match = _SIDEMENU_BLOCK.search(feed_xml)
        if match is None:
            # Belt and braces with the fetch-time content assertion: an
            # offline re-parse of a stale/corrupted cached payload should
            # fail loudly too, not report zero records silently.
            raise ValueError("miccai feed has no <aside class=\"sidemenu\"> widget")

        items = _parse_li_items(match.group(1))

        series_by_key: dict[str, ConferenceSeries] = {}
        event_by_stem: dict[str, ConferenceInstance] = {}
        instances: list[ConferenceInstance] = []

        # Pass 1: bare (unprefixed) entries are event dates -- real venues.
        for item in items:
            if item["kind"] is not None:
                continue
            instance = self._event_instance(item, series_by_key)
            instances.append(instance)
            event_by_stem.setdefault(_stem(item["head"]).lower(), instance)

        # Pass 2: prefixed entries are deadlines, joined to their event by a
        # shared title stem where possible.
        for item in items:
            if item["kind"] is None:
                continue
            instances.append(self._deadline_instance(item, event_by_stem, series_by_key))

        return list(series_by_key.values()), instances

    # -- internals ------------------------------------------------------

    def _event_instance(
        self, item: dict[str, Any], series_by_key: dict[str, ConferenceSeries]
    ) -> ConferenceInstance:
        stem = _stem(item["head"])
        series_key = _series_key_for(stem)
        series_by_key.setdefault(
            series_key,
            ConferenceSeries(
                series_key=series_key,
                acronym=stem,
                full_name=item["head"],
                contributing_sources=[self.name],
                license=self.license,
            ),
        )
        return ConferenceInstance(
            source=self.name,
            source_record_id=item["href"],
            series_key=series_key,
            record_kind="conference",
            title=item["head"],
            acronym=stem,
            year_label=_year_from(stem),
            event_start=_parse_month_day_year(item["date_text"]),
            event_dates_text=item["date_text"],
            url=item["href"],
            source_url=item["href"],
            contributing_sources=[self.name],
            license=self.license,
            raw={"label": item["head"], "date_text": item["date_text"]},
        )

    def _deadline_instance(
        self,
        item: dict[str, Any],
        event_by_stem: dict[str, ConferenceInstance],
        series_by_key: dict[str, ConferenceSeries],
    ) -> ConferenceInstance:
        stripped = _strip_label(item["head"])
        stem = _stem(stripped)
        parent = event_by_stem.get(stem.lower())

        event_date = _parse_month_day_year(item["date_text"])
        deadline = Deadline(
            kind=item["kind"],
            raw=item["date_text"],
            instant=_deadline_instant(event_date),
            # Bare calendar dates, no time, no zone anywhere in this source.
            basis="inferred:date-only",
            # The label is the round name. Four labels map to "submission", so
            # without this a venue with both a submission and an application
            # deadline collapses to one entry and loses a round.
            round_label=_label_prefix(item["head"]),
            source=self.name,
        )

        series_key = parent.series_key if parent else _series_key_for(stem)
        if parent is None and series_key:
            series_by_key.setdefault(
                series_key,
                ConferenceSeries(
                    series_key=series_key,
                    acronym=stem,
                    full_name=stripped,
                    contributing_sources=[self.name],
                    license=self.license,
                ),
            )

        return ConferenceInstance(
            source=self.name,
            source_record_id=item["href"],
            series_key=series_key,
            parent_instance_key=parent.instance_key if parent else None,
            record_kind="track",
            title=stripped,
            acronym=stem,
            year_label=_year_from(stem),
            url=item["href"],
            source_url=item["href"],
            deadlines=[deadline],
            # A stem match works on today's ten items; it is not a validated
            # heuristic (recon open question 4), so an unmatched deadline is
            # flagged for a human rather than silently attached to nothing.
            unresolved_parent=parent is None,
            contributing_sources=[self.name],
            license=self.license,
            raw={"label": item["head"], "date_text": item["date_text"]},
        )


# --- helpers -----------------------------------------------------------


def _parse_li_items(sidemenu_html: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for href, anchor_html in _LI_ANCHOR.findall(sidemenu_html):
        # Decode entities (some titles carry a mid-string "&#8211;" em dash)
        # before splitting, so the split never sees an un-decoded entity.
        label = html.unescape(anchor_html).strip()
        # Split on the LAST " - ": several titles contain their own em dash,
        # and the true date separator is always the final one in the string.
        head, sep, date_text = label.rpartition(" - ")
        if not sep:
            continue  # no date suffix at all -- not a shape we understand
        kind = _classify(head)
        items.append({"href": href, "head": head, "date_text": date_text.strip(), "kind": kind})
    return items


def _classify(head: str) -> str | None:
    for pattern, kind in _LABEL_RULES:
        if pattern.match(head):
            return kind
    return None


def _strip_label(head: str) -> str:
    for pattern, _kind in _LABEL_RULES:
        if pattern.match(head):
            return pattern.sub("", head, count=1).strip()
    return head


def _label_prefix(head: str) -> str:
    """The matched label, verbatim, as the round name.

    Four distinct labels map to ``submission`` ("Submission deadline",
    "Submission deadline extended", "Application deadline", "Applications
    due"). Without this, two deadline items for one venue produce the same
    ``(kind, round_label)`` identity, ``merge_deadlines`` treats the second as
    an extension of the first, and one of the two rounds silently disappears.
    """
    for pattern, _kind in _LABEL_RULES:
        match = pattern.match(head)
        if match:
            return match.group(0).rstrip(": ").strip()
    return ""


def _stem(text: str) -> str:
    """The acronym+year a deadline item and its event item have in common.

    Strip a trailing parenthetical qualifier ("(MICCAI-Endorsed Event)") and
    keep only the part before an em/en dash, which is where the short name
    lives on both the event entry and its paired deadline entry.
    """
    stripped = _TRAILING_PAREN.sub("", text).strip()
    return _EM_EN_DASH_SPLIT.split(stripped, maxsplit=1)[0].strip()


def _series_key_for(stem: str) -> str:
    return f"gen:miccai:{stem.lower().replace(' ', '-')}" if stem else ""


def _year_from(text: str) -> str:
    match = _YEAR_IN_TEXT.search(text or "")
    return match.group(0) if match else ""


def _parse_month_day_year(date_text: str) -> str | None:
    try:
        return datetime.strptime(date_text.strip(), "%B %d, %Y").date().isoformat()
    except ValueError:
        return None


def _deadline_instant(event_date: str | None) -> str | None:
    """Treat a bare deadline date as expiring at the end of that day, UTC.

    This is our assumption, not a claim the source makes -- which is exactly
    why the ``Deadline.basis`` on the caller's side reads ``inferred:...``
    rather than a real timezone name.
    """
    if not event_date:
        return None
    try:
        day = datetime.strptime(event_date, "%Y-%m-%d")
    except ValueError:
        return None
    return to_iso_instant(day.replace(hour=23, minute=59, second=59, tzinfo=UTC))
