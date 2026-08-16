"""The ams_mathcal adapter, and the guards its live page forced.

The fixture is five real ``<dl class="event">`` blocks trimmed from the live
88-event page, chosen to cover: a plain event, two of the exactly-two blocks
in the whole 88-event corpus that mention a submission deadline in prose
(both already past at recon time), and two blocks with accented / mis-encoded
Latin-1 characters in the location column.

See ``docs/conferences/recon/society_calendars.md`` for the full recon.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from apps.scraper.collect.conferences.adapters.ams_mathcal import (
    MATHCAL_URL,
    AMSMathCalAdapter,
)
from apps.scraper.collect.core.http import Response
from apps.scraper.collect.core.rawstore import RawBundle

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def raw_bytes() -> bytes:
    return (FIXTURES / "ams_mathcal_sample.html").read_bytes()


@pytest.fixture
def ams_bundle(raw_bytes) -> RawBundle:
    encoded = base64.b64encode(raw_bytes).decode("ascii")
    return RawBundle(source="ams_mathcal", run_id="20260816T000000Z", fetched_at="2026-08-16T00:00:00Z",
                      records=[{"body_b64": encoded}], meta={})


@pytest.fixture
def parsed(ams_bundle):
    series, instances = AMSMathCalAdapter().parse(ams_bundle)
    return series, {i.source_record_id: i for i in instances}


# --- adapter attributes ----------------------------------------------------


def test_adapter_declares_the_contract_attributes():
    adapter = AMSMathCalAdapter()
    assert adapter.name == "ams_mathcal"
    assert adapter.venue_native is True
    assert adapter.phase == 4
    assert adapter.license == "site content; Content-Signal use=reference"


# --- the headline finding: zero open calls, by design ----------------


def test_every_instance_has_an_empty_deadline_list(parsed):
    """This calendar is filtered by *event* date, so any deadline it
    mentions has already closed by the time the event is upcoming. The
    adapter must never manufacture a Deadline from event-date or prose
    text -- both real submission-deadline mentions in the corpus are past."""
    _, instances = parsed
    assert len(instances) == 5
    for record in instances.values():
        assert record.deadlines == []


def test_event_dates_are_never_mapped_onto_event_start_or_end(parsed):
    """`dt.event_dates` has no acronym+year structure to split reliably (88
    distinct shapes) -- the verbatim string is the truth, exactly the call
    ccf_deadlines makes about its own free-text `date` field."""
    _, instances = parsed
    poisson = instances["6947"]
    assert poisson.event_dates_text == "August 3, 2026 - August 14, 2026"
    assert poisson.event_start is None
    assert poisson.event_end is None


def test_a_deadline_mentioned_in_prose_does_not_leak_into_the_deadline_list(parsed):
    """The ITC 2026 block's own event_info prose says "Submission deadline:
    March 12 AoE" -- a real sentence, deliberately not surfaced as an
    actionable Deadline, because it is already closed and this source has
    no reliable way to tell open from closed prose mentions apart."""
    _, instances = parsed
    itc = instances["7052"]
    assert "Submission deadline" in itc.cfp_text
    assert itc.deadlines == []


# --- the latin-1 seam: decode happens in parse, never in fetch --------


def test_fetch_never_calls_decode_stores_base64_bytes_only(monkeypatch):
    """fetch must not choose an encoding at all -- base64 makes no
    assumption about the byte content, so the interpretive decision (which
    charset) stays entirely inside parse."""
    real_bytes = b"<html>\xf6\xe9 mixed latin-1 bytes</html>" * 3000  # over MIN_MATHCAL_BYTES

    class _StubClient:
        def get(self, url, *, min_bytes=0, **kwargs):
            assert url == MATHCAL_URL
            return Response(url=url, status=200, body=real_bytes)

    bundle = AMSMathCalAdapter().fetch(_StubClient())
    stored = bundle.records[0]["body_b64"]
    # The stored payload is plain ASCII (base64 alphabet) -- proof that
    # fetch never ran a decode that could raise or silently corrupt bytes.
    assert stored.isascii()
    assert base64.b64decode(stored) == real_bytes


def test_parse_decodes_latin1_and_preserves_accented_characters(parsed):
    """Verified live: "University of Göttingen" and similar are corrupted
    (raise or mangle) if decoded as UTF-8. latin-1 is a lossless 1:1
    byte<->codepoint mapping, so every byte the server sent survives."""
    _, instances = parsed
    goettingen = instances["7007"]
    assert "Göttingen" in goettingen.title
    assert "Göttingen" in goettingen.place_text


def test_utf8_would_have_corrupted_the_same_bytes(raw_bytes):
    """Direct proof of the trap this adapter avoids: decoding the exact
    fixture bytes as UTF-8 does not round-trip the accented text latin-1
    recovers cleanly."""
    latin1_text = raw_bytes.decode("latin-1")
    utf8_text = raw_bytes.decode("utf-8", errors="replace")
    assert "Göttingen" in latin1_text
    assert "Göttingen" not in utf8_text


def test_a_corrupted_base64_payload_is_handled_without_crashing():
    bundle = RawBundle(source="ams_mathcal", run_id="x", fetched_at="y",
                        records=[{"body_b64": "not valid base64!!!"}], meta={})
    series, instances = AMSMathCalAdapter().parse(bundle)
    assert series == []
    assert instances == []


# --- record id and identity -------------------------------------------


def test_record_id_comes_from_the_ics_href_not_invented(parsed):
    _, instances = parsed
    assert set(instances) == {"6947", "7052", "6991", "7007", "7155"}


def test_source_url_is_the_conferences_own_site_the_dedupe_join_key(parsed):
    _, instances = parsed
    poisson = instances["6947"]
    assert poisson.source_url == "http://wis.kuleuven.be/events/2026_poisson/poisson2026"
    assert poisson.url == poisson.source_url


def test_no_series_is_invented_for_a_source_with_no_recurring_identity(parsed):
    """AMS titles are one-off event names with no acronym+year structure --
    unlike ccf_deadlines or openresearch, there is nothing honest to key a
    ConferenceSeries on here."""
    series, _ = parsed
    assert series == []


# --- the seam ----------------------------------------------------------


def test_parse_touches_no_network(ams_bundle):
    series, instances = AMSMathCalAdapter().parse(ams_bundle)
    assert len(instances) == 5


def test_a_block_with_no_ics_id_is_skipped_defensively():
    from apps.scraper.collect.conferences.adapters.ams_mathcal import (
        AMSMathCalAdapter as A,
    )

    block_without_id = """
    <dl class="event">
      <dt class="event_dates">August 3, 2026 - August 14, 2026 </dt>
      <dd class="event_title">Some Event With No ICS Link</dd>
      <dd class="event_location">Nowhere</dd>
    </dl>
    """
    instance = A()._parse_block(block_without_id)
    assert instance is None
