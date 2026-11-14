"""SBIR/STTR solicitations — the parent-plus-topic case.

This adapter is second in the build order on purpose. It is the one that forces
the object model from briefing section 1 to be real: a solicitation is an
administrative wrapper, and the technical topics nested inside it are where every
usable word of research description lives. Storing only the solicitation would
throw away nearly all the content — a single solicitation routinely carries dozens
of topics, each with a long, specific, technical description. Those are by a wide
margin the best descriptive text any source in this system produces.

So topics and subtopics are emitted as first-class records that point back at the
solicitation and inherit its dates, rather than being flattened into it.

**Operational note, probed:** ``api.www.sbir.gov`` answers ``403 Forbidden`` to
every request from some networks (including this development environment) —
every path, every user agent, with or without parameters. That is an edge/WAF
decision at their end, not a bug here. The adapter therefore treats a 403 as a
reportable source outage rather than a crash, and everything downstream of
``fetch`` is exercised from stored raw payloads so the flattening logic stays
testable regardless.

**Since 2026-11 the API answers 403 to everyone**: SBIR.gov's own API page says
its APIs are "currently undergoing maintenance". When the API refuses, the
adapter reads the public topic search instead (``www.sbir.gov/topics``, allowed
by robots.txt): the listing of open topics, fresh each run, and each topic's
own page for the full description, cached because a posted topic's text does
not change. Those are shaped like the API's rows, so ``parse`` is unchanged.
"""

from __future__ import annotations

import html
import re
from typing import Any

from tools.retrieval.collect.core.http import FetchError, PoliteClient
from tools.retrieval.collect.core.rawstore import RawBundle, new_run_id, utc_now
from tools.retrieval.collect.grants.adapters.base import BaseAdapter
from tools.retrieval.collect.grants.normalize import (
    clean_text,
    dedupe_preserving_order,
    join_description,
    to_iso_date,
)
from tools.retrieval.collect.grants.record import Opportunity

BASE_URL = "https://api.www.sbir.gov/public/api/solicitations"
#: Probed: this endpoint caps pages at roughly 50 rows and offers no configurable
#: sort (default is close date, descending). Plan for many small requests.
PAGE_SIZE = 50
MAX_PAGES = 200

#: Statuses that mean "accepting applications" or "about to". Compared casefolded
#: against ``current_status``.
OPEN_STATUSES = frozenset({"open", "future", "pre-release", "prerelease"})

SITE_ROOT = "https://www.sbir.gov"
#: The public topic search, open topics only (pre-release ones included).
SITE_LISTING = f"{SITE_ROOT}/topics?status=Open&page={{page}}"
#: The listing shows ten topics a page; this bounds a runaway pager.
SITE_MAX_PAGES = 80


class SBIRAdapter(BaseAdapter):
    name = "sbir"
    #: The agencies write these topic descriptions themselves — this is the
    #: funder's own prose, so it wins descriptive fields on merge.
    funder_native = True
    phase = 1

    # -- stage 1 ----------------------------------------------------------

    def fetch(self, client: PoliteClient, *, limit: int | None = None) -> RawBundle:
        try:
            return self._fetch_api(client, limit=limit)
        except FetchError as exc:
            if exc.status != 403:
                raise
        run_id = new_run_id()
        rows = fetch_site(client, limit=limit)
        return self.bundle(self.name, run_id, utc_now(), rows, via="site")

    def _fetch_api(self, client: PoliteClient, *, limit: int | None = None) -> RawBundle:
        run_id = new_run_id()
        collected: list[dict[str, Any]] = []
        start = 0

        for _ in range(MAX_PAGES):
            remaining = None if limit is None else limit - len(collected)
            if remaining is not None and remaining <= 0:
                break
            rows = PAGE_SIZE if remaining is None else min(PAGE_SIZE, remaining)
            url = f"{BASE_URL}?start={start}&rows={rows}"

            response = client.get(url)
            payload = response.json()
            page = payload if isinstance(payload, list) else (payload or {}).get("results") or []
            page = [row for row in page if isinstance(row, dict)]
            collected.extend(page)

            if len(page) < rows:
                break
            start += len(page)

        return self.bundle(self.name, run_id, utc_now(), collected, page_size=PAGE_SIZE)

    def available(self) -> tuple[bool, str]:
        return True, ""

    # -- stage 2 ----------------------------------------------------------

    def parse(self, bundle: RawBundle) -> list[Opportunity]:
        records: list[Opportunity] = []
        for solicitation in bundle.records:
            if not isinstance(solicitation, dict):
                continue
            if not _is_open(solicitation):
                # Probed question from the briefing: the endpoint exposes no
                # reliable server-side status filter, so we pull everything and
                # filter here. Cheap, since the dataset is small.
                continue
            parent = self._parse_solicitation(solicitation)
            records.append(parent)
            records.extend(self._parse_topics(solicitation, parent))
        return records

    def _parse_solicitation(self, row: dict[str, Any]) -> Opportunity:
        due_dates = _due_dates(row)
        close_date = to_iso_date(row.get("close_date")) or (due_dates[0] if due_dates else None)

        return Opportunity(
            source=self.name,
            source_record_id=str(
                row.get("solicitation_id") or row.get("solicitation_number") or row.get("solicitation_title")
            ),
            source_url=clean_text(row.get("solicitation_agency_url") or row.get("sbir_solicitation_link")),
            opportunity_number=clean_text(row.get("solicitation_number")),
            record_kind="standalone",
            title=clean_text(row.get("solicitation_title")),
            funder=clean_text(row.get("agency")),
            funder_subunit=clean_text(row.get("branch")),
            description=join_description(row.get("description"), row.get("solicitation_description")),
            # Programme, phase and year are identifiers, not subjects, and now
            # have columns. A solicitation's subject lives in its topics.
            categories=[],
            status="open" if _status_of(row) == "open" else "forecasted",
            posted_date=to_iso_date(row.get("release_date")),
            open_date=to_iso_date(row.get("open_date")),
            close_date=close_date,
            close_date_text=clean_text(row.get("close_date")),
            additional_due_dates=[d for d in due_dates if d != close_date],
            award_floor=None,
            award_ceiling=None,
            currency="USD",
            # SBIR and STTR are the programme; Phase I and Phase II are entirely
            # different amounts of money and maturity.
            opportunity_category=clean_text(row.get("program")),
            activity_codes=dedupe_preserving_order(
                [clean_text(p) for p in _as_list(row.get("phase")) if p]
            ),
            funding_instruments=["Procurement Contract"],
            applicant_types=["Small businesses"],
            raw=row,
        )

    def _parse_topics(self, row: dict[str, Any], parent: Opportunity) -> list[Opportunity]:
        """Flatten topics and their nested subtopics into individual records."""
        out: list[Opportunity] = []
        for topic in _as_list(row.get("solicitation_topics")):
            if not isinstance(topic, dict):
                continue
            out.append(self._topic_record(topic, row, parent))
            for subtopic in _as_list(topic.get("subtopics")):
                if isinstance(subtopic, dict):
                    out.append(self._topic_record(subtopic, row, parent, under=topic))
        return out

    def _topic_record(
        self,
        topic: dict[str, Any],
        row: dict[str, Any],
        parent: Opportunity,
        *,
        under: dict[str, Any] | None = None,
    ) -> Opportunity:
        number = clean_text(topic.get("topic_number") or topic.get("subtopic_number"))
        title = clean_text(topic.get("topic_title") or topic.get("subtopic_title"))

        return Opportunity(
            source=self.name,
            source_record_id=f"{parent.source_record_id}:{number or title}",
            source_url=clean_text(topic.get("sbir_topic_link") or topic.get("topic_link"))
            or parent.source_url,
            opportunity_number=number,
            # The pointer, not a merge. Dates and eligibility are inherited at
            # read time from this reference.
            parent_opportunity_number=parent.opportunity_number,
            record_kind="topic",
            title=title,
            funder=parent.funder,
            funder_subunit=clean_text(topic.get("branch")) or parent.funder_subunit,
            # The payload that matters: long, technical, subject-specific.
            description=join_description(
                topic.get("topic_description"),
                topic.get("subtopic_description"),
                topic.get("topic_open_date_desc"),
            ),
            categories=dedupe_preserving_order(
                [
                    *parent.categories,
                    clean_text(under.get("topic_number")) if under else "",
                ]
            ),
            # Dates carried through from the solicitation, as the topics have none.
            status=parent.status,
            posted_date=parent.posted_date,
            open_date=parent.open_date,
            close_date=parent.close_date,
            close_date_text=parent.close_date_text,
            additional_due_dates=list(parent.additional_due_dates),
            eligibility=parent.eligibility,
            currency="USD",
            # Inherited from the solicitation, like the dates: a topic has no
            # programme or eligibility of its own.
            opportunity_category=parent.opportunity_category,
            activity_codes=list(parent.activity_codes),
            funding_instruments=list(parent.funding_instruments),
            applicant_types=list(parent.applicant_types),
            agency_code=parent.agency_code,
            raw={"topic": topic, "solicitation_number": row.get("solicitation_number")},
        )


# --- helpers -------------------------------------------------------------


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _status_of(row: dict[str, Any]) -> str:
    return clean_text(row.get("current_status") or row.get("status")).lower()


def _is_open(row: dict[str, Any]) -> bool:
    status = _status_of(row)
    if status:
        return status in OPEN_STATUSES
    # No status field at all: fall back to dates rather than dropping the record.
    return bool(to_iso_date(row.get("close_date")) or to_iso_date(row.get("open_date")))


def _due_dates(row: dict[str, Any]) -> list[str]:
    raw = row.get("application_due_date") or row.get("application_due_dates")
    values = [to_iso_date(entry) for entry in _as_list(raw)]
    return dedupe_preserving_order([value for value in values if value])


# --- the public site, while the API is down ---------------------------------

_HIT = re.compile(r'<h3[^>]*>\s*<a href="/topics/(\d+)">(.*?)</a>\s*</h3>(.*?)(?=<h3|</ul>\s*</nav>|$)', re.S)
_DATE = re.compile(r"<b>(Release Date|Open Date|Close Date):</b>\s*([^<&]+)")
_STATUS = re.compile(r'<span class="[^"]*radius-sm[^"]*">\s*([^<]+?)\s*</span>')


def _text_lines(page: str) -> list[str]:
    page = re.sub(r"<(script|style)\b.*?</\1>", "", page, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", "\n", page))
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_listing(page: str) -> list[dict[str, str]]:
    """The topic hits on one listing page: id, title, status and dates."""
    hits = []
    for topic_id, title, rest in _HIT.findall(page):
        dates = {label: value.strip() for label, value in _DATE.findall(rest)}
        status = _STATUS.search(rest)
        hits.append(
            {
                "id": topic_id,
                "title": clean_text(html.unescape(re.sub(r"<[^>]+>", "", title))),
                "status": status.group(1) if status else "",
                "release_date": dates.get("Release Date", ""),
                "open_date": dates.get("Open Date", ""),
                "close_date": dates.get("Close Date", ""),
            }
        )
    return hits


def _after(lines: list[str], label: str, stop: tuple[str, ...]) -> list[str]:
    """The lines after ``label`` up to the next of ``stop``."""
    try:
        start = lines.index(label) + 1
    except ValueError:
        return []
    out = []
    for line in lines[start:]:
        if line in stop:
            break
        out.append(line)
    return out


_LABELS = (
    "Funding Agency", "Year:", "Topic Number:", "Solicitation Number:",
    "Tagged as:", "Solicitation Status:", "NOTE:", "View Official Solicitation",
    "Release Schedule", "Release Date", "Open Date", "Due Date(s)", "Close Date",
    "Description",
)
_PAGE_END = ("Site Map", "Privacy Policy")


def parse_topic(page: str) -> dict[str, Any]:
    """One topic's own page: agency, numbers, programme, due dates, description."""
    lines = _text_lines(page)
    agency = _after(lines, "Funding Agency", _LABELS)
    tags = [t.upper() for t in _after(lines, "Tagged as:", _LABELS)]
    official = re.search(r'href="([^"]+)"[^>]*>\s*View Official Solicitation', page)
    return {
        "agency": agency[0] if agency else "",
        "branch": agency[1] if len(agency) > 1 else "",
        "topic_number": next(iter(_after(lines, "Topic Number:", _LABELS)), ""),
        "solicitation_number": next(iter(_after(lines, "Solicitation Number:", _LABELS)), ""),
        "program": "STTR" if "STTR" in tags else "SBIR",
        "phase": _phases(tags),
        "due_dates": _after(lines, "Due Date(s)", _LABELS),
        "agency_url": html.unescape(official.group(1)) if official else "",
        "description": "\n\n".join(_after(lines, "Description", _PAGE_END)),
    }


def _phases(tags: list[str]) -> list[str]:
    if "BOTH" in tags:
        return ["Phase I", "Phase II"]
    return [p for p, tag in (("Phase I", "PHASE I"), ("Phase II", "PHASE II")) if tag in tags]


def fetch_site(client: PoliteClient, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Open topics from the public site, grouped into API-shaped solicitations."""
    hits: list[dict[str, str]] = []
    for page in range(SITE_MAX_PAGES):
        found = parse_listing(client.get(SITE_LISTING.format(page=page), cache=False).text())
        hits.extend(found)
        if not found or (limit is not None and len(hits) >= limit):
            break
    if limit is not None:
        hits = hits[:limit]
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for hit in hits:
        url = f"{SITE_ROOT}/topics/{hit['id']}"
        topic = parse_topic(client.get(url, min_bytes=1000).text())
        number = topic["solicitation_number"] or f"topic-{hit['id']}"
        key = (number, hit["open_date"], hit["close_date"])
        row = groups.get(key)
        if row is None:
            row = groups[key] = {
                "solicitation_id": number,
                "solicitation_number": number,
                "solicitation_title": f"{topic['agency']} {topic['program']} solicitation {number}".strip(),
                "program": topic["program"],
                "phase": topic["phase"],
                "agency": topic["agency"],
                "branch": topic["branch"],
                "release_date": hit["release_date"],
                "open_date": hit["open_date"],
                "close_date": hit["close_date"],
                "application_due_date": topic["due_dates"],
                "solicitation_agency_url": topic["agency_url"],
                "current_status": hit["status"] or "Open",
                "solicitation_topics": [],
            }
        row["solicitation_topics"].append(
            {
                "topic_title": hit["title"],
                "topic_number": topic["topic_number"],
                "branch": topic["branch"],
                "topic_description": topic["description"],
                "sbir_topic_link": url,
            }
        )
    # A solicitation whose topics carry different dates becomes one row per
    # date pair; each needs its own id.
    numbers = [k[0] for k in groups]
    for (number, opened, closed), row in groups.items():
        if numbers.count(number) > 1:
            row["solicitation_id"] = f"{number}@{opened}/{closed}"
        # The branch belongs to the solicitation only when every topic shares it.
        if len({t["branch"] for t in row["solicitation_topics"]}) > 1:
            row["branch"] = ""
    return list(groups.values())

