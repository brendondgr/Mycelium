"""The OpenReview adapter, and the traps its live probing found.

Every guard here maps to a numbered gotcha in ``docs/conferences/recon/openreview.md``.
The fixture is trimmed from real live payloads (``AAAI.org/2027/Conference`` is the
report's own canonical multi-round example) plus a handful of venues with one field
surgically removed to represent documented-but-unsampled traps -- an unreadable
invitation (46/1073 active venues), a cdate-only round (21/1006), and a missing
``submission_id`` (2/1075). Each of those is called out at the point it is built.
"""

from __future__ import annotations

import json

import pytest

from tools.retrieval.collect.conferences.adapters.openreview import (
    OpenReviewAdapter,
    _chunk_ids,
    _fallback_submission_deadline,
    _record_kind,
    _series_key,
    _year_from_id,
)
from tools.retrieval.tests.collect.conferences.conftest import FIXTURES, TODAY, bundle


def _load_records() -> list[dict]:
    return json.loads((FIXTURES / "openreview_active_sample.json").read_text(encoding="utf-8"))


@pytest.fixture
def openreview_records() -> list[dict]:
    return _load_records()


@pytest.fixture
def openreview_bundle(openreview_records) -> RawBundle:  # noqa: F821 - typing only
    return bundle("openreview", openreview_records)


@pytest.fixture
def parsed(openreview_bundle):
    series, instances = OpenReviewAdapter().parse(openreview_bundle)
    return series, {i.source_record_id: i for i in instances}


# --- identity --------------------------------------------------------------


def test_series_key_strips_only_the_year_segment(parsed):
    """`AAAI.org/2027/Conference` must not carry `2027` into the series key,
    or next year's edition would never join this year's."""
    _, instances = parsed
    aaai = instances["AAAI.org/2027/Conference"]
    assert aaai.series_key == "gen:openreview:AAAI.org/Conference"


def test_series_key_does_not_collapse_distinct_venues_sharing_a_host(parsed):
    """The recon report's own suggestion -- key on `host` alone -- would merge
    every ACM-hosted venue into one series. This fixture alone has ACM.org
    hosting both CHASE and the ICMR workshop; they must stay separate."""
    _, instances = parsed
    chase = instances["ACM.org/CHASE/2026/Workshop/ARMH"]
    icmr = instances["ACM.org/ICMR/2026/Workshop/LSC"]
    assert chase.series_key != icmr.series_key
    assert chase.series_key.startswith("gen:openreview:ACM.org/")
    assert icmr.series_key.startswith("gen:openreview:ACM.org/")


@pytest.mark.parametrize(
    ("group_id", "expected"),
    [
        ("AAAI.org/2027/Conference", "conference"),
        ("ACM.org/CHASE/2026/Workshop/ARMH", "workshop"),
        ("ICML.cc/2026/Position_Paper_Track", "track"),
        ("GSCL.org/KONVENS/2026/Workshop/Eval4SD", "workshop"),
    ],
)
def test_record_kind_is_read_from_the_id_path_convention(group_id, expected):
    """No typed field distinguishes these anywhere in the API (recon open
    question #3) -- this is deliberately a path-segment convention."""
    assert _record_kind(group_id) == expected


def test_year_label_is_the_first_year_shaped_path_segment():
    assert _year_from_id("AAAI.org/2027/Conference") == "2027"
    assert _year_from_id("ACM.org/BCB/2026/Conference") == "2026"
    assert _year_from_id("no/year/here") == ""


def test_series_key_falls_back_to_host_when_every_segment_is_a_year():
    assert _series_key("2026", "example.org") == "gen:openreview:example.org"


# --- epoch-millisecond deadlines --------------------------------------------


def test_duedate_is_epoch_milliseconds_utc_cross_checked_against_venue_prose(parsed):
    """The report's own live cross-check: AAAI 2027's `duedate` decodes to
    exactly the instant its `content.date` prose independently claims for
    'Abstract Registration'. No basis inference anywhere in this path."""
    _, instances = parsed
    aaai = instances["AAAI.org/2027/Conference"]
    abstract = next(d for d in aaai.deadlines if d.kind == "abstract")
    assert abstract.raw == "1784721540000"
    assert abstract.instant == "2026-07-22T11:59:00Z"
    assert abstract.basis == "UTC"


def test_expdate_and_audit_timestamps_are_never_read_as_a_deadline():
    """`expdate` (a +30 minute grace period on 1002/1006 invitations) and
    `tcdate`/`tmdate`/`mdate` sit right next to `duedate` in the payload and
    are easy to grab by mistake. None of the four may leak into the deadline
    list or its instant."""
    from tools.retrieval.collect.conferences.adapters.openreview import _deadlines_for

    content = {"submission_id": {"value": "X/-/Submission"}}
    invitation = {
        "id": "X/-/Submission",
        "cdate": 1700000000000,
        "duedate": 1784721540000,
        "expdate": 1784723340000,  # 30 minutes later
        "tcdate": 1600000000000,
        "tmdate": 1900000000000,
        "mdate": 1900000000000,
    }
    deadlines, warnings = _deadlines_for(content, invitation, "openreview")
    assert len(deadlines) == 1
    assert deadlines[0].instant == "2026-07-22T11:59:00Z"
    assert warnings == []


# --- the multi-round trap ----------------------------------------------------


def test_multiround_duedate_is_relabelled_abstract_not_submission(parsed):
    """gotcha #3: a naive Submission-invitation-duedate mapping reports this
    as the paper deadline. It is the abstract deadline."""
    _, instances = parsed
    aaai = instances["AAAI.org/2027/Conference"]
    kinds = [d.kind for d in aaai.deadlines]
    assert "abstract" in kinds
    assert kinds.count("submission") <= 1  # the fallback text, never the raw duedate


def test_multiround_venue_is_flagged_so_a_human_knows_the_deadline_is_uncertain(parsed):
    _, instances = parsed
    aaai = instances["AAAI.org/2027/Conference"]
    assert any("abstract-registration deadline" in w for w in aaai.quality_warnings)


def test_multiround_paper_deadline_is_recovered_from_the_content_date_fallback(parsed):
    """Only 73/198 multi-round venues have this fallback at all; AAAI 2027 is
    the report's own worked example, and this is the exact number it claims:
    2026-07-29, not the 2026-07-22 abstract date."""
    _, instances = parsed
    aaai = instances["AAAI.org/2027/Conference"]
    paper = next(d for d in aaai.deadlines if d.kind == "submission")
    assert paper.instant == "2026-07-29T11:59:00Z"
    assert paper.raw == "Jul 29 2026 11:59AM UTC-0"
    assert paper.basis == "UTC-0"


def test_a_second_real_multiround_venue_confirms_the_pattern(parsed):
    """ICML 2026, independent of the AAAI example, with different numbers."""
    _, instances = parsed
    icml = instances["ICML.cc/2026/Conference"]
    abstract = next(d for d in icml.deadlines if d.kind == "abstract")
    paper = next(d for d in icml.deadlines if d.kind == "submission")
    assert abstract.instant == "2026-01-24T11:59:00Z"
    assert paper.instant == "2026-01-29T11:59:00Z"


def test_a_track_sharing_the_multiround_venues_pattern_still_parses(parsed):
    """ICML's Position Paper Track is its own group with its own invitation,
    not a shadow of the main conference -- it must get the same treatment."""
    _, instances = parsed
    track = instances["ICML.cc/2026/Position_Paper_Track"]
    assert track.record_kind == "track"
    assert any(d.kind == "abstract" for d in track.deadlines)
    assert any(d.kind == "submission" for d in track.deadlines)


def test_multiround_without_a_usable_fallback_yields_only_the_abstract(parsed):
    """125/198 multi-round venues have no content.date fallback at all --
    GSCL/KONVENS Eval4SD in this fixture is one (`content.date` is empty).
    The real paper deadline is genuinely not obtainable anonymously, and that
    must show up as a warning, not as a guessed date."""
    _, instances = parsed
    eval4sd = instances["GSCL.org/KONVENS/2026/Workshop/Eval4SD"]
    assert len(eval4sd.deadlines) == 1
    assert eval4sd.deadlines[0].kind == "abstract"
    assert any("no usable content.date fallback" in w for w in eval4sd.quality_warnings)


def test_non_multiround_venue_is_not_double_counted_even_with_full_date_text(parsed):
    """ACM ICMR's LSC workshop is NOT multi-round (no
    full_submission_invitation_id) but its content.date happens to carry a
    complete 'Submission Deadline: ...' segment anyway. The fallback path
    must never fire here -- one deadline, taken directly from duedate."""
    _, instances = parsed
    lsc = instances["ACM.org/ICMR/2026/Workshop/LSC"]
    assert len(lsc.deadlines) == 1
    assert lsc.deadlines[0].kind == "submission"
    assert lsc.deadlines[0].instant == "2026-05-06T12:00:00Z"


# --- the empty-list trap (gotcha #2) ----------------------------------------


def test_missing_invitation_yields_no_deadline_but_is_flagged_not_silent(parsed):
    """gotcha #2: an unreadable id returns HTTP 200 with an empty list, not a
    403 -- 46/1073 active venues silently yield no deadline this way. A
    healthy-looking empty result must still be visible on the record."""
    _, instances = parsed
    brigap = instances["BriGap/2026/Workshop"]
    assert brigap.deadlines == []
    assert any("returned no result" in w for w in brigap.quality_warnings)
    assert brigap.is_relevant(TODAY) is False  # no deadlines -> never relevant


def test_cdate_only_invitation_yields_no_deadline_but_is_flagged(parsed):
    """21/1006 readable invitations carry `cdate` (submissions open) with no
    `duedate` at all yet -- a round that has not been dated, not a miss."""
    _, instances = parsed
    detec = instances["DETEC/2026/Conference"]
    assert detec.deadlines == []
    assert any("cdate but no duedate" in w for w in detec.quality_warnings)


def test_missing_submission_id_is_flagged_and_never_crashes(parsed):
    """2/1075 active venues have no content.submission_id at all -- fetch()
    never had an id to look up for these, so parse() must not assume one."""
    _, instances = parsed
    gils = instances["GILS/2026/Conference"]
    assert gils.deadlines == []
    assert any("no content.submission_id" in w for w in gils.quality_warnings)


def test_legacy_shaped_group_is_skipped_not_crashed(openreview_bundle):
    """0/1075 *active* venues are legacy (verified live), but a legacy-shaped
    group -- no `domain`, no `content` key at all -- must not crash parse()
    if the API ever hands one back."""
    series, instances = OpenReviewAdapter().parse(openreview_bundle)
    ids = {i.source_record_id for i in instances}
    assert "legacy.example/2019/Conference" not in ids
    assert len(series) == len(instances)  # one series per surviving instance


# --- fields that must stay empty or verbatim --------------------------------


def test_cfp_text_is_always_empty_even_when_description_is_populated(openreview_records):
    """gotcha #5: group.description is the identical OpenReview boilerplate
    on 601/1075 active venues, and invitation `instructions` has only 2
    distinct values across 549. Populating cfp_text from either would poison
    dedupe's descriptive-field merge with hundreds of identical strings."""
    boilerplate = "Set up and customize the peer review process for your venue."
    poisoned = json.loads(json.dumps(openreview_records[0]))  # deep copy
    poisoned["group"]["description"] = boilerplate

    _, instances = OpenReviewAdapter().parse(bundle("openreview", [poisoned]))
    assert instances[0].cfp_text == ""


def test_every_content_value_is_unwrapped_from_its_value_envelope(parsed):
    """gotcha #7: `group.content.title` is `{"value": "..."}`, not a string.
    A parser that forgets to unwrap would store the dict's repr as the title."""
    _, instances = parsed
    aaai = instances["AAAI.org/2027/Conference"]
    assert aaai.title == "The Forty-First AAAI Conference on Artificial Intelligence"
    assert isinstance(aaai.title, str)


def test_start_date_free_text_is_kept_verbatim_never_parsed(parsed):
    _, instances = parsed
    aaai = instances["AAAI.org/2027/Conference"]
    assert aaai.event_dates_text == "Feb 16 2027"
    assert aaai.event_start is None


def test_location_online_is_detected_as_virtual(parsed):
    _, instances = parsed
    caisc = instances["CAISc/2026/Conference"]
    assert caisc.is_virtual is True
    assert caisc.is_hybrid is False


# --- the free-text fallback parser, in isolation ----------------------------


@pytest.mark.parametrize(
    ("text", "expected_value", "expected_basis"),
    [
        (
            "Submission Start: Jun 30 2026 11:59AM UTC-0, Abstract Registration: "
            "Jul 22 2026 11:59AM UTC-0, Submission Deadline: Jul 29 2026 11:59AM UTC-0",
            "2026-07-29 11:59:00",
            "UTC-0",
        ),
        ("Submission Deadline: Aug 05 2026 11:59AM UTC-0", "2026-08-05 11:59:00", "UTC-0"),
    ],
)
def test_fallback_extracts_the_submission_deadline_segment(text, expected_value, expected_basis):
    result = _fallback_submission_deadline(text)
    assert result is not None
    _, value, basis = result
    assert value == expected_value
    assert basis == expected_basis


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Submission Deadline: TBD",
        "Submission Start: Jun 30 2026 11:59AM UTC-0",  # no deadline segment at all
        "Conference: March 9-12, 2027",  # the one real weird value found live
    ],
)
def test_fallback_returns_none_rather_than_guess_at_an_unrecognised_shape(text):
    assert _fallback_submission_deadline(text) is None


# --- chunking (pure, no network) --------------------------------------------


def test_chunk_ids_respects_the_character_budget_not_a_fixed_count():
    """500 ids in one request returned HTTP 414 live; chunking must be driven
    by encoded URL length, not a hardcoded batch size."""
    ids = [f"Venue.org/{i}/2026/Conference" for i in range(500)]
    chunks = _chunk_ids(ids, budget=1000)
    assert len(chunks) > 1
    assert sum(len(c) for c in chunks) == 500
    # every id must land in exactly one chunk
    assert sorted(x for c in chunks for x in c) == sorted(ids)


def test_chunk_ids_keeps_a_short_roster_in_one_request():
    ids = ["TMLR", "DMLR", "Computo"]
    chunks = _chunk_ids(ids, budget=6000)
    assert chunks == [ids]


def test_chunk_ids_of_an_empty_roster_is_empty():
    assert _chunk_ids([]) == []


# --- fetch(), against a fake offline client ---------------------------------


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Stands in for PoliteClient: records every URL requested and answers
    from a canned map, so fetch()'s request-shaping logic is testable with no
    network and no real PoliteClient machinery involved."""

    def __init__(self, answers: dict[str, dict]) -> None:
        self.answers = answers
        self.urls: list[str] = []

    def get(self, url: str, **kwargs) -> _FakeResponse:
        self.urls.append(url)
        for prefix, payload in self.answers.items():
            if url.startswith(prefix):
                return _FakeResponse(payload)
        raise AssertionError(f"unexpected URL in fetch(): {url}")


def _fake_client_for(venue_ids: list[str], groups: list[dict], invitations: list[dict]) -> _FakeClient:
    from tools.retrieval.collect.conferences.adapters.openreview import (
        GROUPS_URL,
        INVITATIONS_URL,
    )

    return _FakeClient(
        {
            f"{GROUPS_URL}?id=active_venues": {"groups": [{"id": "active_venues", "members": venue_ids}]},
            f"{GROUPS_URL}?ids=": {"groups": groups},
            f"{INVITATIONS_URL}?ids=": {"invitations": invitations},
        }
    )


def _venue(vid: str, submission_id: str) -> dict:
    return {"id": vid, "domain": vid, "host": vid.split("/")[0],
            "content": {"submission_id": {"value": submission_id}}}


def test_fetch_always_sends_expired_true_on_the_invitations_request():
    """gotcha #1: without `expired=true`, an already-expired invitation 400s
    and PoliteClient never retries a 400 -- it would kill the whole fetch on
    the first venue whose deadline had already passed."""
    venues = ["A/2026/Conference"]
    groups = [_venue("A/2026/Conference", "A/2026/Conference/-/Submission")]
    invitations = [{"id": "A/2026/Conference/-/Submission", "duedate": 1784721540000}]
    client = _fake_client_for(venues, groups, invitations)

    OpenReviewAdapter().fetch(client)

    invitation_calls = [u for u in client.urls if "/invitations?" in u]
    assert invitation_calls, "fetch() must call /invitations at all"
    assert all("expired=true" in u for u in invitation_calls)


def test_fetch_pairs_a_missing_invitation_as_none_not_a_dropped_venue():
    """The empty-list trap, reproduced end to end: the invitations endpoint
    simply omits an id it will not show us. fetch() must still emit a record
    for that venue, paired with invitation=None, so parse() can see the gap."""
    venues = ["A/2026/Conference", "B/2026/Conference"]
    groups = [
        _venue("A/2026/Conference", "A/2026/Conference/-/Submission"),
        _venue("B/2026/Conference", "B/2026/Conference/-/Submission"),
    ]
    # Only A's invitation comes back -- B's id was asked for and silently omitted.
    invitations = [{"id": "A/2026/Conference/-/Submission", "duedate": 1784721540000}]
    client = _fake_client_for(venues, groups, invitations)

    result = OpenReviewAdapter().fetch(client)

    by_id = {r["group"]["id"]: r["invitation"] for r in result.records}
    assert by_id["A/2026/Conference"] is not None
    assert by_id["B/2026/Conference"] is None


def test_fetch_records_asked_vs_returned_counts_in_meta():
    """gotcha #2's aggregate half: the gap must be visible offline, in
    bundle.meta, without needing to re-fetch to notice 46/1073 went missing."""
    venues = ["A/2026/Conference", "B/2026/Conference"]
    groups = [_venue("A/2026/Conference", "A/2026/Conference/-/Submission")]  # B silently missing
    invitations: list[dict] = []
    client = _fake_client_for(venues, groups, invitations)

    result = OpenReviewAdapter().fetch(client)

    assert result.meta["venues_requested"] == 2
    assert result.meta["groups_returned"] == 1
    assert result.meta["submissions_requested"] == 1
    assert result.meta["invitations_returned"] == 0


def test_fetch_strips_the_webfield_js_blob():
    """`group.web` is a multi-KB JS blob parse() never reads (took a full
    dump from 10.8 MB to 8.6 MB in recon). It must not survive into storage."""
    venues = ["A/2026/Conference"]
    groups = [_venue("A/2026/Conference", "A/2026/Conference/-/Submission")]
    groups[0]["web"] = "// webfield_template\n" + ("x" * 2000)
    invitations = [{"id": "A/2026/Conference/-/Submission", "duedate": 1784721540000}]
    client = _fake_client_for(venues, groups, invitations)

    result = OpenReviewAdapter().fetch(client)

    assert "web" not in result.records[0]["group"]


def test_fetch_respects_limit():
    venues = [f"V{i}/2026/Conference" for i in range(5)]
    groups = [_venue(v, f"{v}/-/Submission") for v in venues]
    invitations = [{"id": f"{v}/-/Submission", "duedate": 1784721540000} for v in venues]
    client = _fake_client_for(venues, groups, invitations)

    result = OpenReviewAdapter().fetch(client, limit=2)

    assert result.meta["venues_requested"] == 2
