"""ams_mathcal: the American Mathematical Society's public meetings calendar.

**Built for venue coverage, not CFPs.** MathCal is filtered by *event* date, so
by the time a meeting is "upcoming" any deadline it happens to mention has
already closed. Measured 2026-08-16: 88 upcoming events, of which exactly 2
mention a submission deadline anywhere (both in free prose, both already past).
This is the honest illustration of the whole society-calendar category's design
flaw -- a calendar keyed on event date structurally cannot surface an open
call -- and it is why this adapter never emits a deadline at all. It exists to
give the non-CS-and-engineering side of this system a venue and identity spine
(``dd.event_url`` is the conference's own site, the join key for dedupe against
WikiCFP/dblp) rather than to add actionable CFPs.

**Every instance is emitted with an empty deadline list.** ``event_dates_text``
carries the verbatim ``dt.event_dates`` string; ``event_start``/``event_end``
are deliberately left ``None`` rather than parsed out of it, the same call
``ccf_deadlines`` makes about its own free-text ``date`` field -- storing the
string honestly beats guessing at a split that could silently mis-attribute a
single-day event's one date to "start" or "end". Do not, ever, map an event
date onto a ``Deadline``: that is precisely the confusion this module's
existence is meant to prevent.

See ``docs/conferences/recon/society_calendars.md`` for the full recon.
"""

from __future__ import annotations

import base64
import binascii
import re

from tools.retrieval.collect.conferences.adapters.base import BaseConferenceAdapter
from tools.retrieval.collect.conferences.record import (
    ConferenceInstance,
    ConferenceSeries,
)
from tools.retrieval.collect.core.http import PoliteClient
from tools.retrieval.collect.core.rawstore import RawBundle, new_run_id, utc_now
from tools.retrieval.collect.core.text import clean_text

MATHCAL_URL = "https://www.ams.org/meetings/calendar/mathcal"

#: Measured 215,825 bytes for the real 88-event page. Anything dramatically
#: smaller is an error page or an empty result, not the calendar.
MIN_MATHCAL_BYTES = 20_000

LICENSE = "site content; Content-Signal use=reference"

_EVENT_BLOCK = re.compile(r'<dl class="event">(.*?)</dl>', re.DOTALL)
_ID_RE = re.compile(r"/mathcal/ics/(\d+)\.ics")
_DATES_RE = re.compile(r'<dt class="event_dates">\s*(.*?)\s*<a', re.DOTALL)
_TITLE_RE = re.compile(r'<dd class="event_title">\s*(.*?)\s*</dd>', re.DOTALL)
_LOCATION_RE = re.compile(r'<dd class="event_location">\s*(.*?)\s*</dd>', re.DOTALL)
_URL_RE = re.compile(r'<dd class="event_url">\s*<a href="([^"]+)"', re.DOTALL)
_INFO_RE = re.compile(r'<p class="event_info">(.*?)</p>', re.DOTALL)


class AMSMathCalAdapter(BaseConferenceAdapter):
    name = "ams_mathcal"
    venue_native = True
    phase = 4
    license = LICENSE

    def fetch(self, client: PoliteClient, *, limit: int | None = None) -> RawBundle:
        """One request. The raw bytes are base64'd so the JSON-serialised raw
        bundle survives untouched -- ``fetch`` never chooses an encoding.

        AMS serves this page as ISO-8859-1. Deciding *that* is an
        interpretation, and interpretation belongs in ``parse``: base64 makes
        no assumption about the byte content at all, so the actual
        ``.decode("latin-1")`` call happens only once, in ``parse``, and stays
        re-runnable offline over the exact bytes the server sent.
        """
        response = client.get(MATHCAL_URL, min_bytes=MIN_MATHCAL_BYTES)
        encoded = base64.b64encode(response.body).decode("ascii")
        return self.bundle(self.name, new_run_id(), utc_now(), [{"body_b64": encoded}], url=MATHCAL_URL)

    def parse(
        self, bundle: RawBundle
    ) -> tuple[list[ConferenceSeries], list[ConferenceInstance]]:
        if not bundle.records or not isinstance(bundle.records[0], dict):
            return [], []
        try:
            raw_bytes = base64.b64decode(bundle.records[0].get("body_b64", ""))
        except (ValueError, binascii.Error):
            return [], []

        # The one interpretive decision this whole adapter makes: latin-1,
        # because the Content-Type header says so. Decoding as UTF-8 here
        # would corrupt most of the location column ("Göttingen", "Málaga",
        # ...) -- verified against the live page.
        text = raw_bytes.decode("latin-1")

        instances: list[ConferenceInstance] = []
        for block in _EVENT_BLOCK.findall(text):
            instance = self._parse_block(block)
            if instance is not None:
                instances.append(instance)

        # No recurring-venue identity exists in this source at all -- titles
        # are one-off event names, not acronym+year pairs -- so there is
        # nothing honest to key a ConferenceSeries on. Leaving series_key
        # empty on every instance is deliberate, not an oversight.
        return [], instances

    # -- internals --------------------------------------------------------

    def _parse_block(self, block: str) -> ConferenceInstance | None:
        id_match = _ID_RE.search(block)
        if id_match is None:
            return None  # no stable identity -- nothing to upsert against
        record_id = id_match.group(1)

        dates_match = _DATES_RE.search(block)
        title_match = _TITLE_RE.search(block)
        location_match = _LOCATION_RE.search(block)
        url_match = _URL_RE.search(block)
        info_match = _INFO_RE.search(block)

        dates_text = clean_text(dates_match.group(1)) if dates_match else ""
        title = clean_text(title_match.group(1)) if title_match else ""
        location = clean_text(location_match.group(1)) if location_match else ""
        url = clean_text(url_match.group(1)) if url_match else ""
        info = clean_text(info_match.group(1)) if info_match else ""

        if not title:
            return None

        return ConferenceInstance(
            source=self.name,
            source_record_id=record_id,
            record_kind="conference",
            title=title,
            # Never parsed into event_start/event_end -- 88 distinct titles,
            # no acronym+year structure to split on reliably. The verbatim
            # string is the truth (ccf_deadlines makes the identical call
            # about its own free-text `date` field).
            event_dates_text=dates_text,
            place_text=location,
            city=_city_from(location),
            # ZERO deadlines, always. The calendar is event-date filtered, so
            # any deadline this record's prose happens to mention (~2.3% of
            # the corpus, both already past at recon time) is not a live
            # call -- and event dates are never a deadline substitute.
            deadlines=[],
            url=url,
            # The conference's own site, not AMS's -- the join key for dedupe
            # against WikiCFP/dblp downstream.
            source_url=url,
            cfp_text=info,
            contributing_sources=[self.name],
            license=self.license,
            raw={"dates_text": dates_text, "title": title, "location": location, "url": url},
        )


def _city_from(location: str) -> str:
    """First comma-separated component, a convenience, not a claim.

    Mirrors ``ccf_deadlines._city_from`` -- AMS's ``event_location`` has the
    identical "no structure, 88 distinct shapes" property.
    """
    if not location:
        return ""
    return location.split(",")[0].strip()
