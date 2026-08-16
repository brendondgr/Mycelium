"""The miccai adapter, and the guards its live feed forced.

Every guard traces to a numbered claim in
``docs/conferences/recon/society_calendars.md``. The fixture is trimmed from
the real 10-item RSS feed and keeps the full ten-item sidemenu widget intact,
because the traps live in how those ten items differ from each other.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.scraper.collect.conferences.adapters.miccai import MICCAIAdapter, _stem
from apps.scraper.collect.core.http import FetchError
from apps.scraper.collect.core.rawstore import RawBundle

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def feed_xml() -> str:
    return (FIXTURES / "miccai_keydates_feed_sample.xml").read_text(encoding="utf-8")


@pytest.fixture
def miccai_bundle(feed_xml) -> RawBundle:
    return RawBundle(source="miccai", run_id="20260816T000000Z", fetched_at="2026-08-16T00:00:00Z",
                      records=[{"feed_xml": feed_xml}], meta={})


@pytest.fixture
def parsed(miccai_bundle):
    series, instances = MICCAIAdapter().parse(miccai_bundle)
    return series, {i.source_record_id: i for i in instances}


# --- adapter attributes ----------------------------------------------------


def test_adapter_declares_the_contract_attributes():
    adapter = MICCAIAdapter()
    assert adapter.name == "miccai"
    assert adapter.venue_native is True  # the society's own site
    assert adapter.phase == 4
    assert adapter.license == "site content; Content-Signal use=reference"


# --- the count: exactly 3 of 10 are real deadlines --------------------


def test_exactly_ten_items_become_ten_instances(parsed):
    _, instances = parsed
    assert len(instances) == 10


def test_exactly_three_of_ten_are_real_deadlines(parsed):
    """Measured live: 3 of 10 widget items carry a recognised deadline
    label; the rest are bare event dates."""
    _, instances = parsed
    deadline_records = [i for i in instances.values() if i.deadlines]
    assert len(deadline_records) == 3
    assert {d.kind for r in deadline_records for d in r.deadlines} == {"submission"}


# --- the core design error, avoided: bare items are events, not deadlines -


def test_a_bare_item_with_no_prefix_gets_no_deadline(parsed):
    """"IPMI 2027 - International Conference on..." has no label prefix at
    all. Treating the whole widget list as deadlines -- the briefing's
    design error in miniature -- would wrongly gate this as a submission."""
    _, instances = parsed
    ipmi_event = next(
        i for i in instances.values() if i.title.startswith("IPMI 2027") and i.record_kind == "conference"
    )
    assert ipmi_event.deadlines == []
    assert ipmi_event.event_start == "2027-06-27"


def test_a_colon_in_the_title_does_not_get_mistaken_for_a_deadline_label(parsed):
    """"Path to Professorship: Insider Perspectives on Academic Careers" has
    a colon but matches none of the known deadline-label prefixes -- a naive
    "contains a colon" classifier would misfire on exactly this item."""
    _, instances = parsed
    professorship = next(i for i in instances.values() if "Path to Professorship" in i.title)
    assert professorship.deadlines == []
    assert professorship.record_kind == "conference"


# --- split on the LAST " - ", never the first ------------------------


@pytest.mark.parametrize(
    ("label", "expected_stem"),
    [
        ("IPMI 2027 – International Conference on Information Processing in Medical Imaging", "IPMI 2027"),
        ("Submission deadline: IPMI 2027 (MICCAI-Endorsed Event)", "Submission deadline: IPMI 2027"),
        ("Hamlyn Winter School on Surgical Imaging and Vision", "Hamlyn Winter School on Surgical Imaging and Vision"),
    ],
)
def test_stem_strips_trailing_parenthetical_and_keeps_text_before_the_dash(label, expected_stem):
    assert _stem(label) == expected_stem


def test_the_em_dash_entity_mid_title_does_not_confuse_the_date_split(parsed):
    """"IPMI 2027 &#8211; International Conference..." carries its own
    mid-string em dash (decoded from &#8211;). The date must come from the
    LAST " - ", not the first thing that looks like a separator."""
    _, instances = parsed
    ipmi_event = next(
        i for i in instances.values() if i.title.startswith("IPMI 2027") and i.record_kind == "conference"
    )
    assert ipmi_event.event_dates_text == "June 27, 2027"
    assert "International Conference" in ipmi_event.title


# --- parent join: stem match, and the flagged non-match ---------------


def test_ipmi_submission_deadline_resolves_to_its_parent_event(parsed):
    """"Submission deadline: IPMI 2027 (MICCAI-Endorsed Event)" and
    "IPMI 2027 - International Conference..." share the stem "IPMI 2027".
    ``title`` is stored with the label prefix stripped, so the original
    ``<li>`` text is matched via ``raw["label"]`` instead."""
    _, instances = parsed
    ipmi_event = next(
        i for i in instances.values() if i.title.startswith("IPMI 2027") and i.record_kind == "conference"
    )
    ipmi_deadline = next(
        i for i in instances.values() if i.raw["label"].startswith("Submission deadline")
    )
    assert ipmi_deadline.title == "IPMI 2027 (MICCAI-Endorsed Event)"
    assert ipmi_deadline.parent_instance_key == ipmi_event.instance_key
    assert ipmi_deadline.unresolved_parent is False
    assert ipmi_deadline.record_kind == "track"


def test_the_wim_award_deadline_has_no_matching_event_and_is_flagged(parsed):
    """"Applications due: WiM Oral Presentation Award 2026" has no paired
    bare-event "WiM Oral Presentation Award 2026" item in the ten-item
    widget -- a real non-match, not a hypothetical one. A stem match works
    on today's ten items; it is not a validated heuristic, so this must be
    surfaced for a human, never silently dropped or silently attached."""
    _, instances = parsed
    wim = next(i for i in instances.values() if "WiM Oral Presentation Award" in i.title)
    assert wim.unresolved_parent is True
    assert wim.parent_instance_key is None
    assert wim.deadlines[0].kind == "submission"


# --- dates: bare calendar dates, always basis "inferred:date-only" ----


def test_deadline_dates_carry_the_inferred_date_only_basis(parsed):
    _, instances = parsed
    for record in instances.values():
        for deadline in record.deadlines:
            assert deadline.basis == "inferred:date-only"


def test_a_deadline_instant_is_end_of_day_utc_on_its_calendar_date(parsed):
    _, instances = parsed
    ipmi_deadline = next(
        i for i in instances.values() if i.raw["label"].startswith("Submission deadline")
    )
    deadline = ipmi_deadline.deadlines[0]
    assert deadline.raw == "December 7, 2026"
    assert deadline.instant == "2026-12-07T23:59:59Z"


# --- the sidemenu content assertion -----------------------------------


def test_fetch_asserts_sidemenu_is_present_in_the_response():
    """If MICCAI reskins the page and the widget vanishes, this must raise
    rather than cache a 200 that reports a healthy fetch of nothing."""

    class _StubClient:
        def get(self, url, *, min_bytes=0, expect=None, **kwargs):
            body = b"<html>totally reskinned, no widget here</html>" * 200
            if expect is not None and not expect(body):
                raise FetchError(url, "response body failed the adapter's content check", 200)
            raise AssertionError("should have raised before reaching here")

    with pytest.raises(FetchError):
        MICCAIAdapter().fetch(_StubClient())


def test_parse_raises_loudly_if_a_stale_cached_payload_has_no_sidemenu():
    """Belt and braces: even a payload that slipped past the fetch-time
    assertion (an old cache entry, say) must fail parse loudly too."""
    bundle = RawBundle(source="miccai", run_id="x", fetched_at="y",
                        records=[{"feed_xml": "<rss><channel><item></item></channel></rss>"}], meta={})
    with pytest.raises(ValueError, match="sidemenu"):
        MICCAIAdapter().parse(bundle)


def test_parse_returns_nothing_for_an_empty_bundle():
    bundle = RawBundle(source="miccai", run_id="x", fetched_at="y", records=[], meta={})
    series, instances = MICCAIAdapter().parse(bundle)
    assert series == []
    assert instances == []


# --- the seam ------------------------------------------------------------


def test_parse_touches_no_network(miccai_bundle):
    series, instances = MICCAIAdapter().parse(miccai_bundle)
    assert len(instances) == 10
    assert len(series) > 0
