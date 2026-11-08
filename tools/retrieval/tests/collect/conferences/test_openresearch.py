"""The openresearch adapter, and the guards its live data forced.

Every guard here traces to a numbered gotcha in
``docs/conferences/recon/scholarly_event_metadata.md``. The fixture is trimmed
from the real 342-record ``action=ask`` response and keeps one instance of
each trap that recon found.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from tools.retrieval.collect.conferences.adapters.openresearch import (
    OpenResearchAdapter,
    _ask_url,
    _unwrap,
)
from tools.retrieval.collect.core.http import Response
from tools.retrieval.collect.core.rawstore import RawBundle

FIXTURES = Path(__file__).parent / "fixtures"


def _load_records() -> list[dict]:
    payload = json.loads((FIXTURES / "openresearch_ask_sample.json").read_text(encoding="utf-8"))
    return _unwrap(payload["query"]["results"])


@pytest.fixture
def or_records() -> list[dict]:
    return _load_records()


@pytest.fixture
def or_bundle(or_records) -> RawBundle:
    return RawBundle(source="openresearch", run_id="20260816T000000Z", fetched_at="2026-08-16T00:00:00Z",
                      records=or_records, meta={})


@pytest.fixture
def parsed(or_bundle):
    series, instances = OpenResearchAdapter().parse(or_bundle)
    return series, {i.source_record_id: i for i in instances}


# --- adapter attributes ---------------------------------------------------


def test_adapter_declares_the_contract_attributes():
    adapter = OpenResearchAdapter()
    assert adapter.name == "openresearch"
    # A transcription of OpenReview/dblp per the wikitext's own "Sources"
    # section, not the organisers' words -- must lose on merge.
    assert adapter.venue_native is False
    assert adapter.phase == 3
    assert adapter.license == "CC-BY-SA-2.0-DE"
    assert adapter.available() == (True, "")


# --- gotcha 1: the "+" / urlencode trap -----------------------------------


def test_ask_url_percent_encodes_the_query_never_naive_concat():
    """A naive f-string URL would leave literal spaces and brackets in the
    query string. The server decodes an unescaped literal "+" as a space,
    turning "has any value" into "equals empty" and returning 0 results at
    HTTP 200 with no error -- verified live in recon. ``urlencode`` is the
    only thing standing between this adapter and that silent failure."""
    url = _ask_url("2026-08-16", 5000, offset=0)
    parsed_url = urlparse(url)
    assert parsed_url.path.endswith("/mediawiki/api.php")

    # A literal, un-encoded "[" or " " must never appear in the query string
    # component -- both would arrive at the server already mangled.
    assert "[" not in parsed_url.query
    assert " " not in parsed_url.query

    query = parse_qs(parsed_url.query)
    assert query["action"] == ["ask"]
    assert query["format"] == ["json"]
    # Round-tripping through parse_qs recovers the exact literal query text,
    # proving nothing was corrupted in transit -- brackets, colons, ">" and
    # the pipe-separated printout list all survive byte-for-byte.
    assert query["query"][0] == (
        "[[Submission deadline::>2026-08-16]]|?Title|?Acronym|?Start date|?End date"
        "|?Submission deadline|?Abstract deadline|?Notification|?Camera ready due"
        "|?Has location city|?Has location country|?Homepage|?Event type"
        "|?Event in series|?Modification date|limit=5000"
    )


def test_ask_url_omits_offset_when_zero_but_includes_it_otherwise():
    first_page = _ask_url("2026-08-16", 5000, offset=0)
    second_page = _ask_url("2026-08-16", 5000, offset=5000)
    assert "offset" not in parse_qs(urlparse(first_page).query)["query"][0]
    assert "offset=5000" in parse_qs(urlparse(second_page).query)["query"][0]


# --- gotcha 2: meta.count is not trustworthy; only a full page paginates --


class _FakeClient:
    """Stands in for PoliteClient in fetch() tests -- no network, no cache."""

    def __init__(self, pages: list[dict]) -> None:
        self._pages = pages
        self.urls: list[str] = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        payload = self._pages[len(self.urls) - 1]
        return Response(url=url, status=200, body=json.dumps(payload).encode("utf-8"))


def _page(results: dict, count: int, offset: int) -> dict:
    return {"query": {"results": results, "meta": {"count": count, "offset": offset}}}


def test_fetch_paginates_only_when_a_page_is_completely_full(monkeypatch):
    """meta.count is the number *returned*, never the number matched -- a
    500-row page against 9,775 real matches still reports meta.count: 500,
    indistinguishable from "there were exactly 500". The only safe signal is
    len(results) == limit."""
    import tools.retrieval.collect.conferences.adapters.openresearch as mod

    monkeypatch.setattr(mod, "PAGE_LIMIT", 2)
    full_page = {f"Event {i}": {"printouts": {}, "fullurl": ""} for i in range(2)}
    partial_page = {"Event 2": {"printouts": {}, "fullurl": ""}}
    # meta.count is deliberately wrong (says 999) to prove it is never read.
    client = _FakeClient([_page(full_page, 999, 0), _page(partial_page, 999, 2)])

    bundle = OpenResearchAdapter().fetch(client)

    assert len(client.urls) == 2, "a full first page must trigger a second request"
    second_query = parse_qs(urlparse(client.urls[1]).query)["query"][0]
    assert "offset=2" in second_query
    assert len(bundle.records) == 3


def test_fetch_stops_after_one_request_when_the_page_is_not_full(monkeypatch):
    import tools.retrieval.collect.conferences.adapters.openresearch as mod

    monkeypatch.setattr(mod, "PAGE_LIMIT", 5000)
    small_page = {"AAAECC 2027": {"printouts": {}, "fullurl": ""}}
    client = _FakeClient([_page(small_page, 342, 0)])

    bundle = OpenResearchAdapter().fetch(client)

    assert len(client.urls) == 1, "342 real records is nowhere near the 5000 page limit"
    assert len(bundle.records) == 1


# --- gotcha 4: timestamp, never the raw calendar-model string -------------


def test_the_verified_timestamp_decodes_to_exact_midnight_utc(parsed):
    """1788134400 -> 2026-08-31T00:00:00Z, verified live in recon. If this
    adapter ever split the `raw` field ("1/2027/2/15") on "/" and dropped the
    leading calendar-model digit instead, it would silently produce a
    plausible but wrong date."""
    _, instances = parsed
    record = instances["AAAECC 2027"]
    submission = next(d for d in record.deadlines if d.kind == "submission")
    assert submission.raw == "1/2027/2/15"
    assert submission.instant == "2027-02-15T00:00:00Z"


def test_a_corrupted_raw_field_does_not_affect_the_parsed_instant():
    """Even if `raw` is nonsense, the adapter must never touch it for dates --
    only `timestamp` feeds the instant."""
    from tools.retrieval.collect.conferences.adapters.openresearch import (
        _build_deadlines,
    )

    printouts = {
        "Submission deadline": [{"timestamp": "1788134400", "raw": "garbage/not/a/date"}],
    }
    deadlines, _ = _build_deadlines(printouts, None, "openresearch")
    assert deadlines[0].instant == "2026-08-31T00:00:00Z"
    assert deadlines[0].raw == "garbage/not/a/date"


# --- gotcha 5: no timezone anywhere -> always inferred --------------------


def test_every_deadline_carries_the_inferred_date_only_basis(parsed):
    """Briefing rule: never infer a basis silently. Every deadline in this
    source is a bare calendar date, so every one must say so."""
    _, instances = parsed
    for record in instances.values():
        for deadline in record.deadlines:
            assert deadline.basis == "inferred:date-only-utc"


# --- gotcha 6: deadline-after-start is flagged, never dropped -------------


def test_cardis_2026_deadline_after_start_is_flagged_not_dropped(parsed):
    """Verified live: CARDIS 2026 submission deadline 2026-12-12, event start
    2026-03-30 -- a real record, not a data error to paper over."""
    _, instances = parsed
    cardis = instances["CARDIS 2026"]
    assert any("falls after the event start date" in w for w in cardis.quality_warnings)
    submission = next(d for d in cardis.deadlines if d.kind == "submission")
    assert submission.instant is not None, "flagged, never dropped"


def test_a_record_with_no_start_date_skips_the_sanity_check_without_crashing(parsed):
    """ICSOFT 2027 has a submission deadline but no Start date at all -- the
    comparison must degrade to "nothing to check", not raise."""
    _, instances = parsed
    icsoft = instances["ICSOFT 2027"]
    assert icsoft.event_start is None
    assert not any("falls after" in w for w in icsoft.quality_warnings)
    assert any(d.kind == "submission" for d in icsoft.deadlines)


# --- gotcha 7: country is a category reference, not a code ----------------


def test_country_category_prefix_is_stripped_and_mapped_to_iso(parsed):
    _, instances = parsed
    aaip = instances["AAIP 2027"]
    assert aaip.city == "Shanghai"
    assert aaip.country_code == "CN"
    assert "Category:" not in aaip.place_text


def test_an_unmapped_country_name_is_left_blank_not_guessed():
    from tools.retrieval.collect.conferences.adapters.openresearch import (
        OpenResearchAdapter as A,
    )

    record = {
        "subject": "MADEUP 2099",
        "printouts": {
            "Title": ["Made Up Conference"],
            "Acronym": ["MADEUP 2099"],
            "Has location country": [{"fulltext": "Category:Atlantis"}],
        },
        "fullurl": "",
    }
    _, instance = A()._parse_record(record)
    assert instance.country_code == ""
    assert instance.place_text == "Atlantis"


# --- record shape -----------------------------------------------------


def test_workshop_event_type_maps_to_workshop_record_kind(parsed):
    _, instances = parsed
    itw = instances["ITW 2027"]
    assert itw.record_kind == "workshop"


def test_conference_is_the_default_record_kind(parsed):
    _, instances = parsed
    assert instances["AAAECC 2027"].record_kind == "conference"


def test_series_key_comes_from_event_in_series_not_the_yearly_acronym(parsed):
    """"Event in series" is the recurring venue ("AAAAECC"); the acronym
    ("AAAECC 2027") is one year's edition. Keying on the yearly acronym would
    make every edition its own unrelated series."""
    series, instances = parsed
    aaaecc = instances["AAAECC 2027"]
    assert aaaecc.series_key == "gen:openresearch:aaaaecc"
    assert any(s.series_key == "gen:openresearch:aaaaecc" for s in series)


def test_full_record_has_every_deadline_column_in_chronological_order(parsed):
    """ACC 2027 has all four deadline columns populated."""
    _, instances = parsed
    acc = instances["ACC 2027"]
    kinds = [d.kind for d in acc.deadlines]
    assert set(kinds) == {"abstract", "submission", "notification", "camera_ready"}
    instants = [d.instant for d in acc.deadlines]
    assert instants == sorted(instants)


def test_venue_native_is_false_because_the_wikitext_cites_other_sources():
    assert OpenResearchAdapter.venue_native is False


# --- the seam --------------------------------------------------------


def test_parse_touches_no_network_and_needs_only_the_stored_bundle(or_bundle):
    """The whole point of the fetch/parse split -- this must run standalone,
    no client, no PoliteClient import even reachable from here."""
    series, instances = OpenResearchAdapter().parse(or_bundle)
    assert len(instances) == 7
    assert len(series) == 7


def test_non_dict_records_in_the_bundle_are_skipped_defensively():
    bundle = RawBundle(source="openresearch", run_id="x", fetched_at="y", records=[None, "garbage", 42], meta={})
    series, instances = OpenResearchAdapter().parse(bundle)
    assert series == []
    assert instances == []
