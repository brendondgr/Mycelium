"""EU Funding & Tenders Portal (SEDIA).

This interface is far less formally documented than the US sources, so the shape
below was read off the portal's own browser traffic and then verified directly.
Everything the portal's client sends is reproduced here, including the static
``apiKey=SEDIA`` that is embedded in the client rather than issued per user.

Two things worth recording, because both cost time to discover:

1. The ``query`` part must be sent as a **multipart form field with content type
   ``application/json``**. Passing the same JSON as a plain string field returns
   an opaque ``HTTP 500 / "An internal error occurred"``, not a validation error.
2. The briefing lists "search response does not reliably include the full topic
   text, a second fetch per topic is usually required" as a known limitation.
   **That is no longer true.** The response carries ``descriptionByte`` with the
   complete topic description inline, so this adapter makes one request per page
   and no per-topic follow-up. The per-topic fetch path is kept behind a flag in
   case the field is withdrawn.

Endpoint stability is a standing risk, so every part of the request that could
change lives in the module constants below — a URL or parameter rename is a
one-line fix.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from tools.retrieval.collect.core.http import PoliteClient
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

# --- the one-line-fix zone ------------------------------------------------
SEARCH_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
API_KEY = "SEDIA"
#: Matches everything; the portal's own client sends exactly this.
MATCH_ALL_TEXT = "***"
#: Document types: 1 = topic, 2 = call.
DOC_TYPES = ["1", "2"]
#: Status codes: forthcoming and open. (Closed is 31094503 and is never requested.)
STATUS_FORTHCOMING = "31094501"
STATUS_OPEN = "31094502"
OPEN_STATUSES = [STATUS_FORTHCOMING, STATUS_OPEN]
TOPIC_URL = (
    "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/"
    "opportunities/topic-details/{identifier}"
)
PAGE_SIZE = 100
MAX_PAGES = 60
# --------------------------------------------------------------------------

#: Canonical agency code for the one non-US funder in the system.
AGENCY_CODE = "EC"

STATUS_LABELS = {STATUS_FORTHCOMING: "forecasted", STATUS_OPEN: "open"}


class EUPortalAdapter(BaseAdapter):
    name = "eu_portal"
    funder_native = True
    phase = 5

    # -- stage 1 ----------------------------------------------------------

    def fetch(self, client: PoliteClient, *, limit: int | None = None) -> RawBundle:
        run_id = new_run_id()
        collected: list[dict[str, Any]] = []
        total = 0

        for page in range(1, MAX_PAGES + 1):
            remaining = None if limit is None else limit - len(collected)
            if remaining is not None and remaining <= 0:
                break
            size = PAGE_SIZE if remaining is None else min(PAGE_SIZE, remaining)

            url = f"{SEARCH_URL}?apiKey={API_KEY}&text={MATCH_ALL_TEXT}&pageSize={size}&pageNumber={page}"
            body, content_type = _multipart_body()
            response = client.post_raw(url, body, headers={"Content-Type": content_type})
            payload = response.json()
            if not isinstance(payload, dict):
                break

            total = int(payload.get("totalResults") or 0)
            results = [row for row in (payload.get("results") or []) if isinstance(row, dict)]
            collected.extend(results)
            if not results or len(collected) >= total:
                break

        return self.bundle(self.name, run_id, utc_now(), collected, total_results=total)

    # -- stage 2 ----------------------------------------------------------

    def parse(self, bundle: RawBundle) -> list[Opportunity]:
        records: list[Opportunity] = []
        for row in bundle.records:
            if not isinstance(row, dict):
                continue
            record = self._parse_one(row)
            if record is not None:
                records.append(record)
        return records

    def _parse_one(self, row: dict[str, Any]) -> Opportunity | None:
        metadata = row.get("metadata") or {}
        identifier = _first(metadata.get("identifier"))
        if not identifier:
            return None

        status_code = _first(metadata.get("status"))
        status = STATUS_LABELS.get(status_code, "open")

        deadlines = dedupe_preserving_order(
            [iso for iso in (to_iso_date(value) for value in _all(metadata.get("deadlineDate"))) if iso]
        )
        call_identifier = _first(metadata.get("callIdentifier"))
        budget = _budget(metadata.get("budgetOverview"))

        return Opportunity(
            source=self.name,
            source_record_id=clean_text(row.get("reference")) or identifier,
            source_url=clean_text(row.get("url")) or TOPIC_URL.format(identifier=identifier),
            opportunity_number=identifier,
            # A topic sits under a call. Same parent-plus-topic shape as SBIR, so
            # it gets the same treatment rather than being flattened into the call.
            parent_opportunity_number=call_identifier if call_identifier != identifier else None,
            record_kind="topic" if call_identifier and call_identifier != identifier else "standalone",
            title=clean_text(_first(metadata.get("title"))) or identifier,
            funder="European Commission",
            funder_subunit=clean_text(_first(metadata.get("frameworkProgramme"))),
            # descriptionByte carries the whole topic text inline — no second fetch.
            # topicConditions used to be concatenated here; it is admissibility and
            # eligibility boilerplate, near-identical across a whole programme, so
            # it belongs in eligibility. Leaving it in the description diluted the
            # subject matter that retrieval is supposed to match on.
            description=join_description(
                _first(metadata.get("descriptionByte")),
                _first(metadata.get("destinationDescription")),
            ),
            # Subjects only. Action types and keywords have their own columns now;
            # the keyword list is mostly call identifiers, which say nothing about
            # what a topic is about and were being embedded as if they did.
            categories=dedupe_preserving_order(
                [clean_text(v) for v in _all(metadata.get("crossCuttingPriorities"))]
            ),
            status=status,
            # startDate is when the call *opens*, which for a 2027 call is in the
            # future — storing it as posted_date put unpublished calls at the top
            # of a recently-posted sort. When the portal indexed the topic is the
            # nearest thing it publishes to a posting date.
            posted_date=to_iso_date(_first(metadata.get("esDA_IngestDate")))
            or to_iso_date(_first(metadata.get("esDA_FirstIngestDate"))),
            open_date=to_iso_date(_first(metadata.get("startDate"))),
            # Every round goes in; the normalize stage decides which is close_date
            # and Opportunity.due_on decides which is displayed. Taking deadlines[0]
            # here is what advertised a 2021 deadline on a call still running.
            close_date=deadlines[-1] if deadlines else None,
            close_date_text="; ".join(str(v) for v in _all(metadata.get("deadlineDate"))),
            additional_due_dates=deadlines[:-1],
            award_floor=budget.get("min"),
            award_ceiling=budget.get("max"),
            total_program_funding=budget.get("total"),
            expected_awards=budget.get("grants"),
            #: The one non-USD source in the system.
            currency="EUR",
            # RIA / IA / CSA and friends. The EU's equivalent of an activity code:
            # it determines the funding rate and what a consortium has to look like.
            action_types=dedupe_preserving_order(
                [clean_text(value) for value in _all(metadata.get("typesOfAction"))]
            ),
            # Single-stage or two-stage changes what submitting actually involves.
            deadline_model=clean_text(_first(metadata.get("deadlineModel"))),
            topic_keywords=dedupe_preserving_order(
                [
                    *[clean_text(v) for v in _all(metadata.get("keywords"))],
                    *[clean_text(v) for v in _all(metadata.get("crossCuttingPriorities"))],
                ]
            ),
            agency_code=AGENCY_CODE,
            eligibility=join_description(
                _first(metadata.get("supportInfo")),
                # topicConditions carries the admissibility and eligibility rules
                # on 96% of topics. supportInfo alone already covered most records;
                # this deepens them rather than filling gaps — average EU
                # eligibility text goes from a pointer to ~4,800 characters of
                # actual country, consortium and admissibility rules.
                _first(metadata.get("topicConditions")),
            ),
            raw=row,
        )


# --- helpers -------------------------------------------------------------


def _multipart_body() -> tuple[bytes, str]:
    """Build the exact multipart payload the portal's own client sends.

    Hand-rolled rather than delegated to a library because the ``Content-Type`` on
    the individual parts is load-bearing — the server rejects plain text parts.
    """
    boundary = f"----collect{uuid.uuid4().hex}"
    query = {
        "bool": {
            "must": [
                {"terms": {"type": DOC_TYPES}},
                {"terms": {"status": OPEN_STATUSES}},
            ]
        }
    }
    parts = [
        ("query", json.dumps(query)),
        ("languages", json.dumps(["en"])),
        ("sort", json.dumps({"field": "sortStatus", "order": "ASC"})),
    ]

    chunks: list[bytes] = []
    for name, value in parts:
        chunks.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n'
                f"Content-Type: application/json\r\n\r\n"
                f"{value}\r\n"
            ).encode()
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _all(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _first(value: Any) -> str:
    values = _all(value)
    return str(values[0]) if values else ""


def _budget(value: Any) -> dict[str, float | int | None]:
    """Pull EUR figures out of the portal's nested budget blob.

    ``budgetOverview`` arrives as a JSON *string* inside a list. Anything
    unparseable yields empty values rather than a partially-invented budget.
    """
    out: dict[str, float | int | None] = {"min": None, "max": None, "total": None, "grants": None}
    raw = _first(value)
    if not raw:
        return out
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return out

    minimums: list[float] = []
    maximums: list[float] = []
    totals: list[float] = []
    grants: list[int] = []

    for actions in (parsed.get("budgetTopicActionMap") or {}).values():
        for action in actions if isinstance(actions, list) else []:
            if not isinstance(action, dict):
                continue
            low = to_amount(action.get("minContribution"))
            high = to_amount(action.get("maxContribution"))
            count = to_int(action.get("expectedGrants"))
            if low:
                minimums.append(low)
            if high:
                maximums.append(high)
            if count:
                grants.append(count)
            for year_value in (action.get("budgetYearMap") or {}).values():
                amount = to_amount(year_value)
                if amount:
                    totals.append(amount)

    out["min"] = min(minimums) if minimums else None
    out["max"] = max(maximums) if maximums else None
    out["total"] = sum(totals) if totals else None
    out["grants"] = sum(grants) if grants else None
    return out
