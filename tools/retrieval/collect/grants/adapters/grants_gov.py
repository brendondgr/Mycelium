"""Grants.gov — the anchor source.

Probed against the live endpoints before this was written; the notes below record
what the probe found so nobody has to re-derive it:

* ``search2`` and ``fetchOpportunity`` are genuinely unauthenticated. Other
  endpoints on the same host want a key; we need none of them.
* An **empty keyword returns the full set**, not zero — 1,668 open+forecasted at
  time of probing. So we do not drive this with keyword queries at all.
* ``rows`` has **no observed cap**: ``rows=2000`` returned all 1,668 in one page.
  We still page, because the count grows and a single enormous request is rude.
* The status filter accepts exactly ``posted``, ``forecasted``, ``closed``,
  ``archived``. ``"open"`` is *not* a value — it silently returns 0 hits, which is
  the nastiest possible failure mode, so it is asserted against here.
* Detail records put their payload under ``synopsis`` for posted opportunities and
  under ``forecast`` for forecasted ones. Reading only one of them loses every
  forecast record's description.
"""

from __future__ import annotations

from typing import Any

from tools.retrieval.collect.core.http import FetchError, PoliteClient
from tools.retrieval.collect.core.rawstore import RawBundle, new_run_id, utc_now
from tools.retrieval.collect.grants.adapters.base import BaseAdapter
from tools.retrieval.collect.grants.normalize import (
    clean_text,
    dedupe_preserving_order,
    join_description,
    to_amount,
    to_int,
    to_iso_date,
)
from tools.retrieval.collect.grants.record import Opportunity

SEARCH_URL = "https://api.grants.gov/v1/api/search2"
DETAIL_URL = "https://api.grants.gov/v1/api/fetchOpportunity"
VIEW_URL = "https://www.grants.gov/search-results-detail/{id}"

#: Verified accepted values. "open" is not one of them.
OPEN_STATUSES = "forecasted|posted"
PAGE_SIZE = 500


class GrantsGovAdapter(BaseAdapter):
    name = "grants_gov"
    #: An aggregator: its structured dates and award figures are the most
    #: consistently typed of any source, but its descriptive text is whatever the
    #: agency pasted in. Merge policy uses both halves of that.
    funder_native = False
    phase = 0

    def __init__(self, *, fetch_details: bool = True) -> None:
        self.fetch_details = fetch_details

    # -- stage 1 ----------------------------------------------------------

    def fetch(self, client: PoliteClient, *, limit: int | None = None) -> RawBundle:
        run_id = new_run_id()
        summaries, hit_count = self._search_all(client, limit)

        details: dict[str, Any] = {}
        if self.fetch_details:
            for summary in summaries:
                opportunity_id = str(summary.get("id") or "")
                if not opportunity_id:
                    continue
                try:
                    response = client.post_json(DETAIL_URL, {"opportunityId": int(opportunity_id)})
                except (FetchError, ValueError):
                    # One bad detail must not sink a 1,600-record sweep; the
                    # summary alone still produces a usable record.
                    continue
                payload = response.json()
                if isinstance(payload, dict) and payload.get("errorcode") == 0:
                    details[opportunity_id] = payload.get("data") or {}

        return self.bundle(
            self.name,
            run_id,
            utc_now(),
            summaries,
            hit_count=hit_count,
            details=details,
            statuses=OPEN_STATUSES,
        )

    def _search_all(
        self, client: PoliteClient, limit: int | None
    ) -> tuple[list[dict[str, Any]], int]:
        collected: list[dict[str, Any]] = []
        hit_count = 0
        offset = 0

        while True:
            remaining = None if limit is None else limit - len(collected)
            if remaining is not None and remaining <= 0:
                break
            rows = PAGE_SIZE if remaining is None else min(PAGE_SIZE, remaining)

            response = client.post_json(
                SEARCH_URL,
                # No keyword at all: we want the whole open set, not the vendor's
                # relevance ranking over a guess at what we care about.
                {"rows": rows, "startRecordNum": offset, "oppStatuses": OPEN_STATUSES},
            )
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("errorcode") != 0:
                raise FetchError(SEARCH_URL, f"search2 returned {payload!r:.200}")

            data = payload.get("data") or {}
            hit_count = int(data.get("hitCount") or 0)
            page = [row for row in (data.get("oppHits") or []) if isinstance(row, dict)]
            collected.extend(page)

            if not page or len(collected) >= hit_count:
                break
            offset += len(page)

        return collected, hit_count

    # -- stage 2 ----------------------------------------------------------

    def parse(self, bundle: RawBundle) -> list[Opportunity]:
        details = bundle.meta.get("details") or {}
        return [
            self._parse_one(summary, details.get(str(summary.get("id") or "")) or {})
            for summary in bundle.records
            if isinstance(summary, dict) and summary.get("id")
        ]

    def _parse_one(self, summary: dict[str, Any], detail: dict[str, Any]) -> Opportunity:
        opportunity_id = str(summary["id"])
        # Forecast records carry their payload under "forecast", posted ones under
        # "synopsis". Take whichever is populated.
        body = detail.get("synopsis") or detail.get("forecast") or {}

        status = "forecasted" if summary.get("oppStatus") == "forecasted" else "open"

        close_raw = (
            body.get("responseDate")
            or body.get("estApplicationResponseDate")
            or summary.get("closeDate")
        )
        close_date = to_iso_date(body.get("responseDateStr")) or to_iso_date(close_raw)

        additional = dedupe_preserving_order(
            [
                value
                for value in (
                    to_iso_date(body.get("estApplicationResponseDate")),
                    to_iso_date(body.get("responseDate")),
                )
                if value and value != close_date
            ]
        )

        floor = to_amount(body.get("awardFloor") or body.get("estAwardFloor"))
        ceiling = to_amount(body.get("awardCeiling") or body.get("estAwardCeiling"))

        # The deadline before it moved, published on 63% of records. Without it a
        # first collection has no way to know an extension ever happened — the
        # history table can only see changes that occur after we start watching,
        # and this is the source telling us about one that already did.
        original_due = to_iso_date(detail.get("originalDueDate"))

        return Opportunity(
            source=self.name,
            source_record_id=opportunity_id,
            source_url=VIEW_URL.format(id=opportunity_id),
            opportunity_number=clean_text(summary.get("number") or detail.get("opportunityNumber")),
            record_kind="standalone",
            title=clean_text(summary.get("title") or detail.get("opportunityTitle")),
            funder=clean_text(summary.get("agency") or body.get("agencyName")),
            funder_subunit=clean_text(summary.get("agencyCode") or body.get("agencyCode")),
            description=join_description(
                body.get("synopsisDesc"),
                body.get("forecastDesc"),
                body.get("fundingDescLinkDesc"),
            ),
            categories=_categories(summary, body),
            status=status,
            posted_date=to_iso_date(body.get("postingDateStr")) or to_iso_date(body.get("postingDate")),
            open_date=to_iso_date(summary.get("openDate")),
            close_date=close_date,
            close_date_text=clean_text(close_raw) if close_raw else "",
            additional_due_dates=additional,
            original_close_date=original_due if original_due != close_date else None,
            expiration_date=to_iso_date(body.get("archiveDateStr"))
            or to_iso_date(body.get("archiveDate")),
            award_floor=floor,
            award_ceiling=ceiling,
            total_program_funding=to_amount(
                body.get("estimatedFunding") or body.get("estTotalProgramFunding")
            ),
            expected_awards=to_int(body.get("numberOfAwards") or body.get("estNumberOfAwards")),
            currency="USD",
            applicant_types=_labels(body.get("applicantTypes")),
            funding_instruments=_labels(body.get("fundingInstruments")),
            assistance_listings=_assistance_listings(summary, detail),
            # Tri-state on purpose. Grants.gov omits the field rather than saying
            # "no", and a missing cost-share requirement read as "not required" is
            # exactly the surprise that disqualifies an applicant late.
            cost_sharing=_tristate(body.get("costSharing")),
            agency_code=clean_text(
                (detail.get("topAgencyDetails") or {}).get("code")
                or summary.get("agencyCode")
                or ""
            ),
            opportunity_category=clean_text(
                (detail.get("opportunityCategory") or {}).get("description") or ""
            ),
            # Reissue and companion announcements, so a record links to the ones
            # that replaced or accompany it rather than sitting alone.
            related_numbers=dedupe_preserving_order(
                [
                    clean_text(entry.get("oppNumber") or entry.get("opportunityNumber"))
                    for entry in (detail.get("relatedOpps") or [])
                    if isinstance(entry, dict)
                ]
            ),
            eligibility=join_description(body.get("applicantEligibilityDesc")),
            raw={"summary": summary, "detail": detail},
        )


def _labels(entries: Any) -> list[str]:
    """Pull the human label out of Grants.gov's ``[{"description": ...}]`` lists."""
    out: list[str] = []
    for entry in entries or []:
        label = entry.get("description") if isinstance(entry, dict) else entry
        if label:
            out.append(clean_text(label))
    return dedupe_preserving_order(out)


def _assistance_listings(summary: dict[str, Any], detail: dict[str, Any]) -> list[str]:
    """CFDA / Assistance Listing numbers, from whichever half of the payload has them.

    Present on 99.9% of records and stable across years, which makes it the one
    identifier that reliably links this year's posting to last year's programme.
    """
    numbers = [clean_text(value) for value in (summary.get("cfdaList") or [])]
    for entry in detail.get("cfdas") or []:
        if isinstance(entry, dict) and entry.get("cfdaNumber"):
            numbers.append(clean_text(entry["cfdaNumber"]))
    return dedupe_preserving_order([n for n in numbers if n])


def _tristate(value: Any) -> bool | None:
    """True / False / unknown, keeping "the source did not say" distinct from "no"."""
    if isinstance(value, bool):
        return value
    text = clean_text(value).lower()
    if text in {"true", "yes", "y", "1"}:
        return True
    if text in {"false", "no", "n", "0"}:
        return False
    return None


def _categories(summary: dict[str, Any], body: dict[str, Any]) -> list[str]:
    """Subject areas only.

    This used to also carry CFDA numbers, funding instruments, applicant types and
    the document kind, which is why the field held 2,429 distinct values across
    four unrelated taxonomies and could not be used as a facet. Each of those now
    has a column of its own; what is left here is what the field is named after.

    It matters beyond filtering: this list is part of the embedded text, so a
    third of the corpus was carrying "Nonprofits having a 501(c)(3) status with
    the IRS…" in its vector — boilerplate with no discriminative power, diluting
    the subject matter the vector is supposed to represent.
    """
    values = _labels(body.get("fundingActivityCategories"))
    # "Other (see text field entitled ...)" is Grants.gov's placeholder for "the
    # agency did not pick a category". It is on 92 records and is not a subject.
    return dedupe_preserving_order([v for v in values if not v.lower().startswith("other (see")])
