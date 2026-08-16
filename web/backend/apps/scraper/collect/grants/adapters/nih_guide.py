"""NIH Guide — announcements from structured XML, overlays from the notice feed.

The briefing told us to check whether NIH exposes anything more structured than
RSS before committing to RSS parsing. It does, and it changes the design:

``https://grants.nih.gov/web_services/XML/NIH_All_Active_FOAs.xml`` is a single
XML document listing **every currently active** NIH announcement — 651 at time of
probing — with typed fields: ``DocType``, ``DocNum``, ``Title``, ``Purpose``,
``OpenDate``, ``ExpirationDate``, ``LARD`` (last application receipt date),
``ActivityCodes``, and repeated ``RelatedNotices`` elements. That is strictly
better than scraping RSS item pages, and it is a complete active set rather than
a one-week rolling window.

What that feed does *not* contain is ``NOT-`` records: zero of the 651. Notices —
and therefore the **topic overlays** described in briefing section 1 — only appear
in the RSS feed. So this adapter reads both:

* the XML feed for standalone announcements (PA / PAR / PAS / RFA), and
* the RSS feed for notices, following each notice link to extract its
  ``Related Announcements`` parent references and its expiration date.

Overlays deliberately omit deadline, budget, project period, and eligibility
because all of that lives on the parent. We store the pointer and the subject
text, and let read time do the inheriting.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any

from apps.scraper.collect.core.http import FetchError, PoliteClient
from apps.scraper.collect.core.rawstore import RawBundle, new_run_id, utc_now
from apps.scraper.collect.grants.adapters.base import BaseAdapter
from apps.scraper.collect.grants.normalize import (
    clean_text,
    dedupe_preserving_order,
    html_to_text,
    join_description,
    to_iso_date,
)
from apps.scraper.collect.grants.record import Opportunity

ACTIVE_FOA_XML = "https://grants.nih.gov/web_services/XML/NIH_All_Active_FOAs.xml"
NEWSFEED_RSS = "https://grants.nih.gov/grants/guide/newsfeed/fundingopps.xml"

#: Canonical agency code, matching what Grants.gov reports for NIH records so the
#: two sources land in the same facet bucket after a merge.
AGENCY_CODE = "HHS"

#: Prefixes that denote an actual funding announcement with deadlines.
ANNOUNCEMENT_TYPES = frozenset({"PA", "PAR", "PAS", "RFA", "NOFO"})
#: The notice prefix. This category contains the topic overlays.
NOTICE_TYPE = "NOT"

#: Any NIH document number, used to pull parent references out of notice prose.
#: Two shapes coexist and both appear as parent references: with an institute
#: segment ("NOT-CA-26-011", "RFA-CA-25-001") and without ("PA-25-172",
#: "PAR-24-122"). The institute segment is therefore optional, not assumed.
NIH_NUMBER = re.compile(r"\b(PAR?S?|RFA|NOT|NOFO)-(?:([A-Z]{2})-)?(\d{2})-(\d{3,4})\b")
#: The "Related Announcements" block on a notice page, up to the next heading.
RELATED_BLOCK = re.compile(
    r"Related\s+Announcements(.*?)(?:Issued\s+by|Purpose\b|Key\s+Dates)", re.IGNORECASE | re.DOTALL
)
_LABELLED_DATE = "{label}\\s*:?\\s*([A-Z][a-z]+ \\d{{1,2}},\\s*\\d{{4}}|\\d{{4}}-\\d{{2}}-\\d{{2}})"

#: NIH's published standard due dates for new applications, keyed by activity
#: code, as (month, day). Announcements that run on the standard cycle say so in
#: prose — "Multiple dates, see announcement." — and give only the *last* receipt
#: date as a field, so without this table a call with a round due in six weeks is
#: stored as due in seventeen months.
#:
#: Encoded rather than fetched because it changes rarely and a per-record page
#: fetch costs hundreds of requests. Anything derived from it is marked
#: ``dates_inferred``, and step 8's page fetch overwrites it wherever the real
#: dates can be read directly. Longest match wins, so "R01" beats the "R" family
#: fallback.
NIH_STANDARD_DATES: dict[str, tuple[tuple[int, int], ...]] = {
    # Research grants
    "R01": ((2, 5), (6, 5), (10, 5)),
    "U01": ((2, 5), (6, 5), (10, 5)),
    "R03": ((2, 16), (6, 16), (10, 16)),
    "R21": ((2, 16), (6, 16), (10, 16)),
    "R33": ((2, 16), (6, 16), (10, 16)),
    "R34": ((2, 16), (6, 16), (10, 16)),
    "R36": ((2, 16), (6, 16), (10, 16)),
    "R15": ((2, 25), (6, 25), (10, 25)),
    # Conference grants
    "R13": ((4, 12), (8, 12), (12, 12)),
    "U13": ((4, 12), (8, 12), (12, 12)),
    # SBIR / STTR
    "R41": ((1, 5), (4, 5), (9, 5)),
    "R42": ((1, 5), (4, 5), (9, 5)),
    "R43": ((1, 5), (4, 5), (9, 5)),
    "R44": ((1, 5), (4, 5), (9, 5)),
    "U43": ((1, 5), (4, 5), (9, 5)),
    "U44": ((1, 5), (4, 5), (9, 5)),
    # Career development, fellowships, training, centres — by family
    "K": ((2, 12), (6, 12), (10, 12)),
    "F": ((4, 8), (8, 8), (12, 8)),
    "T": ((5, 25), (9, 25), (1, 25)),
    "D": ((5, 25), (9, 25), (1, 25)),
    "P": ((1, 25), (5, 25), (9, 25)),
}

#: NIH's AIDS and AIDS-related standard due dates. Announcements that accept both
#: kinds of application run to this cycle last, which is why so many LARD values
#: land on it rather than on the mechanism's own dates.
AIDS_STANDARD_DATES: tuple[tuple[int, int], ...] = ((1, 7), (5, 7), (9, 7))

#: How many rounds to derive. Enough to cover a three-year announcement running
#: three cycles a year without inventing a decade of dates nobody will act on.
MAX_DERIVED_ROUNDS = 9

#: The prose NIH uses when an announcement runs on the standard cycle rather than
#: having one deadline of its own.
STANDARD_CYCLE_TEXT = re.compile(r"multiple dates|standard dates|see announcement", re.IGNORECASE)


class NIHGuideAdapter(BaseAdapter):
    name = "nih_guide"
    #: The funder itself. Its ``Purpose`` prose beats whatever the agency pasted
    #: into the aggregator, so it wins descriptive fields on merge.
    funder_native = True
    phase = 3

    def __init__(self, *, follow_notices: bool = True, max_notices: int = 60) -> None:
        self.follow_notices = follow_notices
        #: The RSS window is small, but a re-issued week can spike. Bound it so a
        #: bad day costs NIH tens of requests, not thousands.
        self.max_notices = max_notices

    # -- stage 1 ----------------------------------------------------------

    def fetch(self, client: PoliteClient, *, limit: int | None = None) -> RawBundle:
        run_id = new_run_id()

        announcements = self._fetch_announcements(client, limit)
        notices = self._fetch_notices(client) if self.follow_notices else []

        return self.bundle(
            self.name,
            run_id,
            utc_now(),
            announcements,
            notices=notices,
            announcement_feed=ACTIVE_FOA_XML,
            notice_feed=NEWSFEED_RSS,
        )

    def _fetch_announcements(self, client: PoliteClient, limit: int | None) -> list[dict[str, Any]]:
        response = client.get(ACTIVE_FOA_XML)
        root = ET.fromstring(response.body)
        rows = [_element_to_dict(node) for node in root]
        return rows[:limit] if limit else rows

    def _fetch_notices(self, client: PoliteClient) -> list[dict[str, Any]]:
        try:
            response = client.get(NEWSFEED_RSS)
        except FetchError:
            return []
        root = ET.fromstring(response.body)

        notices: list[dict[str, Any]] = []
        for item in root.findall(".//item")[: self.max_notices]:
            link = (item.findtext("link") or "").strip()
            entry: dict[str, Any] = {
                "title": (item.findtext("title") or "").strip(),
                "link": link,
                "description": (item.findtext("description") or "").strip(),
                "pubDate": (item.findtext("pubDate") or "").strip(),
            }
            if link:
                try:
                    # The RSS body is one sentence of boilerplate; the real text
                    # and the parent references are only on the notice page.
                    entry["body_html"] = client.get(link).text()
                except FetchError as exc:
                    entry["fetch_error"] = str(exc)
            notices.append(entry)
        return notices

    # -- stage 2 ----------------------------------------------------------

    def parse(self, bundle: RawBundle) -> list[Opportunity]:
        records = [
            record
            for row in bundle.records
            if isinstance(row, dict)
            and (record := self._parse_announcement(row)) is not None
        ]
        for notice in bundle.meta.get("notices") or []:
            if isinstance(notice, dict):
                parsed = self._parse_notice(notice)
                if parsed is not None:
                    records.append(parsed)
        return records

    def _parse_announcement(self, row: dict[str, Any]) -> Opportunity | None:
        doc_type = clean_text(row.get("DocType")).upper()
        number = clean_text(row.get("DocNum"))
        if not number or doc_type not in ANNOUNCEMENT_TYPES:
            return None

        # LARD is the last date applications are accepted; AppReceiptDate is
        # frequently the string "Multiple dates, see announcement." — prose, not a
        # date, so it goes in the verbatim field and never into close_date.
        receipt_text = clean_text(row.get("AppReceiptDate"))
        close_date = to_iso_date(row.get("LARD")) or to_iso_date(receipt_text)

        # "Multiple dates" means the announcement runs on NIH's standard cycle and
        # LARD is the *end* of it, not the next round. Derive the intervening
        # rounds so the record can be sorted and counted down against honestly.
        activity_codes = _activity_codes(row.get("ActivityCodes"))
        rounds: list[str] = []
        if close_date and STANDARD_CYCLE_TEXT.search(receipt_text):
            rounds = standard_cycle_dates(
                activity_codes,
                open_date=to_iso_date(row.get("OpenDate")),
                last_date=close_date,
            )

        intent_text = clean_text(row.get("IntentDate"))

        return Opportunity(
            source=self.name,
            source_record_id=clean_text(row.get("rowid")) or number,
            source_url=clean_text(row.get("GuideLink")),
            opportunity_number=number,
            record_kind="standalone",
            title=clean_text(row.get("Title")),
            funder="National Institutes of Health",
            funder_subunit=clean_text(row.get("PrimaryIC")),
            description=join_description(row.get("Purpose"), row.get("RelNote")),
            # DocType and activity codes are their own columns now. NIH's feed
            # publishes no subject taxonomy, so this is honestly empty rather than
            # filled with identifiers dressed up as subjects.
            categories=[],
            status="open",
            posted_date=to_iso_date(row.get("RelDate")),
            open_date=to_iso_date(row.get("OpenDate")),
            close_date=close_date,
            close_date_text=receipt_text,
            additional_due_dates=rounds,
            expiration_date=to_iso_date(row.get("ExpirationDate")),
            # A letter of intent is due before the application and missing it
            # disqualifies you, so it is carried whether or not it parses as a
            # date — "30 days prior to the application due date" is still the
            # thing an applicant has to act on.
            intent_date=to_iso_date(intent_text),
            intent_date_text="" if intent_text.lower().startswith("not applicable") else intent_text,
            dates_inferred=bool(rounds),
            currency="USD",
            # An R01 and an R21 are different propositions — different size,
            # duration, and review. Nothing could tell them apart before this.
            activity_codes=activity_codes,
            opportunity_category=doc_type,
            agency_code=AGENCY_CODE,
            # Leading institute is funder_subunit; these are the ones that
            # participate. "Anything NCI is involved in" needs both.
            participating_units=_string_list(row.get("PartIC")),
            raw=row,
        )

    def _parse_notice(self, notice: dict[str, Any]) -> Opportunity | None:
        body_text = html_to_text(notice.get("body_html") or notice.get("description") or "")
        number = _first_number(notice.get("title"), notice.get("description"), notice.get("link"))
        if not number or not number.upper().startswith(NOTICE_TYPE):
            return None

        parents = _related_announcements(notice.get("body_html") or "", exclude=number)
        expiration = _labelled_date(body_text, "Expiration Date") or _labelled_date(
            body_text, "Response Date"
        )

        return Opportunity(
            source=self.name,
            source_record_id=number,
            source_url=clean_text(notice.get("link")),
            opportunity_number=number,
            # First parent wins as the pointer; the rest stay in categories so no
            # reference is silently dropped.
            parent_opportunity_number=parents[0] if parents else None,
            record_kind="overlay",
            title=clean_text(notice.get("title")),
            funder="National Institutes of Health",
            funder_subunit=_issuing_ic(body_text),
            description=body_text,
            # A notice publishes no subject taxonomy. Its extra parent references
            # used to be stashed here as "parent:PAR-24-122" pseudo-categories,
            # which is how a subject field ends up holding identifiers.
            categories=[],
            opportunity_category=NOTICE_TYPE,
            related_numbers=parents[1:],
            status="open",
            posted_date=to_iso_date(notice.get("pubDate")),
            # No close date by design: an overlay carries no deadline of its own,
            # and inventing one from the parent here would make prune lie.
            close_date=None,
            close_date_text="",
            # An overlay expires on its own schedule, independent of any parent.
            expiration_date=expiration,
            currency="USD",
            unresolved_parent=not parents,
            raw=notice,
        )


# --- helpers -------------------------------------------------------------


def _activity_codes(value: object) -> list[str]:
    """Split the ActivityCodes field into individual codes (R01, R21, K99...)."""
    return dedupe_preserving_order(
        [clean_text(code).upper() for code in re.split(r"[,/;\s]+", clean_text(value)) if code]
    )


def _string_list(value: object) -> list[str]:
    """A repeated XML element, which arrives as a str or a list depending on count."""
    values = value if isinstance(value, list) else [value]
    return dedupe_preserving_order([clean_text(item).upper() for item in values if item])


def _cycle_for(activity_codes: list[str]) -> tuple[tuple[int, int], ...]:
    """The standard cycle for the first activity code we recognize.

    Longest key first so a specific code wins over its family: R01 has its own
    dates and must not fall through to a generic "R" rule that does not exist.
    """
    for code in activity_codes:
        for key in sorted(NIH_STANDARD_DATES, key=len, reverse=True):
            if code.startswith(key):
                return NIH_STANDARD_DATES[key]
    return ()


def _runs_on_standard_dates(last_date: date, cycle: tuple[tuple[int, int], ...]) -> bool:
    """Does this announcement's own last receipt date corroborate the cycle?

    The whole derivation rests on "multiple dates, see announcement" meaning the
    published standard dates. That is usually true and occasionally not, and a
    wrongly invented deadline is the most damaging thing this system can produce
    — worse than the terse single date it replaces, because it looks specific.

    So the inference is required to agree with a signal already in the record.
    An announcement running on standard dates ends on one of three published
    families: the mechanism's own new-application dates, its renewal dates one
    month later, or the AIDS dates it also accepts. Measured over the live
    corpus, 85% of "multiple dates" announcements with a known mechanism land on
    one of the three. The remainder set their own schedule, and for those a
    single honest date beats three confident wrong ones.
    """
    stamp = (last_date.month, last_date.day)
    renewal = {((month % 12) + 1, day) for month, day in cycle}
    return stamp in set(cycle) or stamp in renewal or stamp in set(AIDS_STANDARD_DATES)


def standard_cycle_dates(
    activity_codes: list[str],
    *,
    open_date: str | None,
    last_date: str,
    limit: int = MAX_DERIVED_ROUNDS,
) -> list[str]:
    """Derive the standard-cycle rounds an announcement runs on.

    Bounded by the announcement's own window: nothing before it opens, nothing at
    or after the last receipt date, which is already stored as ``close_date``.
    Deliberately *not* bounded by today — the adapter records what the source
    says, and which round is next is a read-time question already answered by
    ``Opportunity.due_on``. Keeping the clock out of parsing is also what makes
    this reproducible from a stored payload months later.

    An unrecognized activity code yields nothing rather than a guessed cycle, and
    so does an announcement that does not corroborate the cycle — see
    :func:`_runs_on_standard_dates`.
    """
    cycle = _cycle_for(activity_codes)
    if not cycle:
        return []

    try:
        end = date.fromisoformat(last_date)
    except (TypeError, ValueError):
        return []

    if not _runs_on_standard_dates(end, cycle):
        return []

    start = date(end.year - 3, 1, 1)
    if open_date:
        try:
            start = max(start, date.fromisoformat(open_date))
        except ValueError:
            pass

    found: list[str] = []
    for year in range(start.year, end.year + 1):
        for month, day in cycle:
            try:
                candidate = date(year, month, day)
            except ValueError:  # e.g. a 29 Feb rule in a non-leap year
                continue
            if start <= candidate < end:
                found.append(candidate.isoformat())
    # Keep the rounds nearest the end: an announcement's remaining cycles matter
    # more than the ones it ran through years ago.
    return sorted(set(found))[-limit:]


def _element_to_dict(node: ET.Element) -> dict[str, Any]:
    """Flatten one <GuideDocs> element, collecting repeated tags into lists."""
    out: dict[str, Any] = {}
    for child in node:
        text = (child.text or "").strip()
        if child.tag in out:
            existing = out[child.tag]
            out[child.tag] = [*existing, text] if isinstance(existing, list) else [existing, text]
        else:
            out[child.tag] = text
    return out


def _format_number(match: re.Match[str]) -> str:
    parts = [match.group(1), match.group(2), match.group(3), match.group(4)]
    return "-".join(part for part in parts if part)


def _first_number(*values: object) -> str | None:
    for value in values:
        if not value:
            continue
        match = NIH_NUMBER.search(str(value).upper())
        if match:
            return _format_number(match)
    return None


def _related_announcements(body_html: str, *, exclude: str) -> list[str]:
    """Extract the parent announcement number(s) a notice points applicants to.

    Prefer the explicit ``Related Announcements`` block; fall back to scanning the
    whole body, because some notices name the parent only in prose.
    """
    text = html_to_text(body_html)
    block = RELATED_BLOCK.search(text)
    scopes = [block.group(1)] if block else []
    scopes.append(text)

    for scope in scopes:
        found = dedupe_preserving_order(
            [
                _format_number(match)
                for match in NIH_NUMBER.finditer(scope.upper())
                if _format_number(match) != exclude
            ]
        )
        # An overlay points at funding announcements, not at other notices.
        announcements = [n for n in found if n.split("-")[0] in ANNOUNCEMENT_TYPES]
        if announcements:
            return announcements
    return []


def _labelled_date(text: str, label: str) -> str | None:
    match = re.search(_LABELLED_DATE.format(label=re.escape(label)), text, re.IGNORECASE)
    return to_iso_date(match.group(1)) if match else None


def _issuing_ic(text: str) -> str:
    match = re.search(r"Issued by\s+(.{3,120}?)(?:\s{2,}|\n|Purpose\b)", text, re.IGNORECASE)
    return clean_text(match.group(1)) if match else ""
