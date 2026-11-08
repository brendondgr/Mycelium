"""The society_pages adapter, and the guards its "Dates and Deadlines" pages
force -- traps that SfN's own live page contains for free.

The fixture is trimmed from the real 158,996-byte SfN page down to its two
richest tables (Abstracts and Sessions; Registration), keeping every trap
intact: a window-opening row phrased as "submission opens", a regular round
and a late-breaking round of the *same* deadline type, two non-specific dates
("Early August", "Late September") that must never become instants, and the
"November 14-18 | ... meeting dates" row that is the event, not a deadline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.retrieval.collect.conferences.adapters.society_pages import (
    BROWSER_EXTRA_HINT,
    REGISTRY_PATH,
    SocietyPagesAdapter,
    SocietyRegistryRow,
    _classify_kind,
    _is_window_opening,
    load_registry,
)
from tools.retrieval.collect.core.rawstore import RawBundle

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def page_html() -> str:
    return (FIXTURES / "sfn_dates_deadlines.html").read_text(encoding="utf-8")


@pytest.fixture
def sfn_row() -> SocietyRegistryRow:
    return SocietyRegistryRow(
        society="Society for Neuroscience",
        conference="Neuroscience 2026",
        acronym="Neuroscience",
        year=2026,
        url="https://www.sfn.org/meetings/neuroscience-2026/general-information/dates-and-deadlines",
        discipline="neuroscience",
        country="US",
        event_dates="November 14-18, 2026",
        notes="fixture row",
    )


@pytest.fixture
def sfn_bundle(sfn_row, page_html) -> RawBundle:
    record = {
        "society": sfn_row.society, "conference": sfn_row.conference,
        "acronym": sfn_row.acronym, "year": sfn_row.year, "url": sfn_row.url,
        "discipline": sfn_row.discipline, "country": sfn_row.country,
        "event_dates": sfn_row.event_dates, "notes": sfn_row.notes,
        "key": sfn_row.key, "html": page_html,
    }
    return RawBundle(
        source="society_pages", run_id="20260816T000000Z", fetched_at="2026-08-16T00:00:00Z",
        records=[record], meta={"mode": "captured"},
    )


@pytest.fixture
def parsed(sfn_bundle):
    series, instances = SocietyPagesAdapter().parse(sfn_bundle)
    assert len(instances) == 1
    return series, instances[0]


def deadlines_matching(instance, **kwargs):
    out = []
    for d in instance.deadlines:
        if all(getattr(d, k) == v for k, v in kwargs.items()):
            out.append(d)
    return out


# --- adapter contract ------------------------------------------------------


def test_adapter_declares_the_contract_attributes():
    adapter = SocietyPagesAdapter()
    assert adapter.name == "society_pages"
    assert adapter.venue_native is True
    assert adapter.phase == 4
    assert adapter.license == "site content; per-society terms"


def test_default_mode_is_http():
    assert SocietyPagesAdapter().mode == "http"


def test_an_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="unknown mode"):
        SocietyPagesAdapter(mode="telepathy")


# --- the registry ------------------------------------------------------


def test_the_checked_in_registry_seeds_the_three_verified_rows():
    rows = load_registry(REGISTRY_PATH)
    acronyms = {row.acronym for row in rows}
    assert {"Neuroscience", "ISMRM", "AVIATION"}.issubset(acronyms)
    assert len(rows) >= 3


def test_every_registry_row_records_when_it_was_verified():
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    for row in payload:
        assert row.get("notes"), f"{row.get('acronym')}: no verification note"
        assert "2026-08-16" in row["notes"] or row.get("verified_at") == "2026-08-16"


def test_the_gold_standard_row_names_sfn_as_the_gold_standard():
    rows = load_registry(REGISTRY_PATH)
    sfn = next(r for r in rows if r.acronym == "Neuroscience")
    assert "gold standard" in sfn.notes.lower()
    assert sfn.url == (
        "https://www.sfn.org/meetings/neuroscience-2026/general-information/dates-and-deadlines"
    )


def test_a_registry_row_has_a_stable_slug_key():
    row = SocietyRegistryRow(
        society="S", conference="C", acronym="Neuroscience", year=2026, url="https://x",
    )
    assert row.key == "neuroscience-2026"
    assert row.series_key == "gen:society:neuroscience"


# --- parse: instance shape ------------------------------------------------


def test_the_page_becomes_one_instance_with_registry_identity(parsed):
    _, instance = parsed
    assert instance.acronym == "Neuroscience"
    assert instance.year_label == "2026"
    assert instance.title == "Neuroscience 2026"
    assert instance.series_key == "gen:society:neuroscience"
    assert instance.record_kind == "conference"
    assert instance.country_code == "US"
    assert instance.license == "site content; per-society terms"


def test_a_series_is_emitted_alongside_the_instance(parsed):
    series, _ = parsed
    assert len(series) == 1
    assert series[0].series_key == "gen:society:neuroscience"
    assert series[0].acronym == "Neuroscience"


# --- the "submission opens" trap -------------------------------------------


def test_submission_opens_is_not_a_deadline(parsed):
    """"Online abstract submission opens" and "Late-breaking abstract
    submission opens" are window openings, never deadlines. Misreading them
    as ``kind="submission"`` is the exact design error the briefing warns
    about by name."""
    _, instance = parsed
    for d in instance.deadlines:
        assert "opens" not in d.raw.lower(), d.raw
    assert not any("opens" in w.lower() for w in instance.quality_warnings if "abstract" in w.lower())


def test_registration_opens_rows_are_also_skipped(parsed):
    """The same trap, same page, different table: "Advance member
    registration opens at noon EDT" must not become a registration deadline."""
    _, instance = parsed
    assert all("opens" not in d.raw.lower() for d in instance.deadlines)
    assert not any(
        "Bonus Day" in d.raw or "Advance member registration opens" in d.raw
        for d in instance.deadlines
    )


@pytest.mark.parametrize(
    "label",
    [
        "Online abstract submission opens",
        "Late-breaking abstract submission opens",
        "Advance member registration opens at noon EDT",
        "Regular registration opens at midnight EDT and continues through the annual meeting",
    ],
)
def test_is_window_opening_flags_every_opens_variant(label):
    assert _is_window_opening(label) is True


def test_a_rebuttal_opening_is_not_treated_as_the_opens_trap():
    """Unlike a submission window, a rebuttal/author-response period opening
    is itself a real, distinct ``Deadline`` kind (``rebuttal_open``)."""
    assert _is_window_opening("Author response period opens") is False
    assert _classify_kind("Author response period opens") == "rebuttal_open"
    assert _classify_kind("Rebuttal period closes") == "rebuttal_close"


# --- label -> kind classification ------------------------------------------


@pytest.mark.parametrize(
    ("label", "expected_kind"),
    [
        ("Extended deadline for abstract submission, 2 p.m. EDT", "abstract"),
        ("Late-breaking abstract submission closes", "abstract"),
        ("Extended deadline for submission of symposium, minisymposium, ... proposals", "submission"),
        ("Notifications of abstract acceptance status sent to presenting authors", "notification"),
        ("Deadline for online advance registration, 11:59 p.m. EDT", "registration"),
        ("Camera-ready deadline for accepted manuscripts", "camera_ready"),
        # Contains "abstract" and "deadline" but not as the contiguous phrase
        # the briefing names -- an administrative row, not an abstract
        # deadline. Real text from the SfN page.
        ("Deadline for abstract presenters to switch from virtual-only to in-person presentation", "unknown"),
        ("Edits to submitted abstracts must be entered by 2 p.m. EDT", "unknown"),
        ("Meeting mobile app available", "unknown"),
    ],
)
def test_classify_kind_matches_the_label_vocabulary(label, expected_kind):
    assert _classify_kind(label) == expected_kind


def test_the_edits_to_abstracts_row_is_unknown_not_abstract(parsed):
    """A real trap on SfN's own page: "Edits to submitted abstracts must be
    entered by 2 p.m. EDT" names abstracts but is not itself the abstract
    submission deadline."""
    _, instance = parsed
    edits = next(d for d in instance.deadlines if "Edits to submitted abstracts" in d.raw)
    assert edits.kind == "unknown"
    # It still carries a real, resolvable timestamp -- classification and
    # timezone resolution are independent concerns.
    assert edits.basis == "EDT"
    assert edits.instant == "2026-06-12T18:00:00Z"


# --- multi-round: regular vs late-breaking ----------------------------


def test_the_late_breaking_round_gets_a_distinct_round_label(parsed):
    _, instance = parsed
    regular = deadlines_matching(instance, kind="abstract", round_label="extended")
    late_breaking = deadlines_matching(instance, kind="abstract", round_label="late-breaking")
    assert len(regular) == 1
    assert len(late_breaking) == 1
    assert regular[0].raw != late_breaking[0].raw
    assert "June 11" in regular[0].raw
    assert "September 15" in late_breaking[0].raw
    # Same kind, different round -- exactly the shape record.py's docstring
    # says a single ``deadline`` column cannot express.
    assert regular[0].kind == late_breaking[0].kind == "abstract"


def test_late_breaking_also_labels_a_notification_row(parsed):
    """round_label is orthogonal to kind: the late-breaking *notification*
    on the page must carry the same distinguishing word."""
    _, instance = parsed
    notif = deadlines_matching(instance, kind="notification", round_label="late-breaking")
    assert len(notif) == 1
    assert "Notification of late-breaking abstract acceptance" in notif[0].raw


# --- "Early August" / "Late September": never an instant -------------


def test_a_vague_month_never_becomes_an_instant(parsed):
    _, instance = parsed
    early_august = next(d for d in instance.deadlines if d.raw.startswith("Early August"))
    assert early_august.instant is None
    assert early_august.kind == "notification"
    assert any("Early August" in w for w in instance.quality_warnings)


def test_late_september_also_never_becomes_an_instant(parsed):
    _, instance = parsed
    late_september_rows = [d for d in instance.deadlines if d.raw.startswith("Late September")]
    assert len(late_september_rows) == 2  # NMP available + late-breaking notification
    assert all(d.instant is None for d in late_september_rows)
    assert any("Late September" in w for w in instance.quality_warnings)


# --- timezone: EDT/EST reach the basis ---------------------------------


def test_est_basis_and_instant_for_the_january_deadline(parsed):
    _, instance = parsed
    jan = next(d for d in instance.deadlines if d.raw.startswith("January 26"))
    assert jan.basis == "EST"
    assert jan.kind == "submission"
    assert jan.round_label == "extended"
    # 5 p.m. EST (UTC-5, no daylight saving in January) = 22:00 UTC.
    assert jan.instant == "2026-01-26T22:00:00Z"


def test_edt_basis_and_instant_for_the_june_deadline(parsed):
    _, instance = parsed
    june = next(d for d in instance.deadlines if d.raw.startswith("June 11"))
    assert june.basis == "EDT"
    # 2 p.m. EDT (UTC-4, daylight saving active in June) = 18:00 UTC.
    assert june.instant == "2026-06-11T18:00:00Z"


def test_a_deadline_with_no_stated_zone_is_marked_inferred_date_only(parsed):
    _, instance = parsed
    sept15 = next(d for d in instance.deadlines if d.raw.startswith("September 15"))
    assert sept15.basis == "inferred:date-only"
    # Our own assumption (end of day UTC), not a claim the source makes.
    assert sept15.instant == "2026-09-15T23:59:59Z"


def test_the_registration_deadline_crosses_midnight_utc_correctly(parsed):
    """11:59 p.m. EDT on October 5 is 03:59 UTC on October 6 -- the exact
    day-shift bug this whole timezone module exists to prevent."""
    _, instance = parsed
    registration = next(
        d for d in instance.deadlines
        if d.kind == "registration" and "11:59" in d.raw
    )
    assert registration.basis == "EDT"
    assert registration.instant == "2026-10-06T03:59:00Z"


# --- event-date rows: never a deadline ---------------------------------


def test_the_meeting_dates_row_never_becomes_a_deadline(parsed):
    _, instance = parsed
    assert not any("meeting dates" in d.raw.lower() for d in instance.deadlines)
    assert not any("November 14-18" in d.raw for d in instance.deadlines)


def test_the_meeting_dates_row_populates_event_dates_text_instead(parsed):
    _, instance = parsed
    assert "November 14-18" in instance.event_dates_text
    assert "2026" in instance.event_dates_text


# --- registration table: multiple <li> under one shared date -----------


def test_three_li_items_under_one_date_cell_become_three_deadlines(parsed):
    """October 5 carries three <li> entries under one shared date cell in
    the source; each is a distinct candidate, not one merged row."""
    _, instance = parsed
    october_5 = [d for d in instance.deadlines if d.raw.startswith("October 5")]
    assert len(october_5) == 3
    assert {d.kind for d in october_5} == {"registration"}


# --- overall shape: the exact count, so a regression in either direction
# (over-matching noise, or silently dropping a row) is caught -------------


def test_the_full_deadline_count_matches_the_trimmed_fixture(parsed):
    """13 of 19 candidate rows across both tables are real deadlines: 6 are
    skipped as "opens" windows, and 1 is the meeting-dates event row."""
    _, instance = parsed
    assert len(instance.deadlines) == 13


def test_every_deadline_carries_a_non_empty_raw_and_basis(parsed):
    _, instance = parsed
    for d in instance.deadlines:
        assert d.raw
        assert d.basis
        assert d.source == "society_pages"


# --- fetch: three modes -----------------------------------------------


def test_available_reports_true_for_http_and_captured_always():
    assert SocietyPagesAdapter(mode="http").available() == (True, "")
    assert SocietyPagesAdapter(mode="captured").available() == (True, "")


def test_available_reports_false_for_browser_when_playwright_is_absent():
    """This environment has no playwright installed, so this is a real
    negative, not a mocked one."""
    ok, reason = SocietyPagesAdapter(mode="browser").available()
    assert ok is False
    assert "playwright" in reason.lower()
    assert BROWSER_EXTRA_HINT in reason


def test_captured_mode_touches_no_network(tmp_path, page_html, sfn_row):
    class _NetworkForbidden:
        def get(self, *args, **kwargs):
            raise AssertionError("captured mode must never call client.get")

    capture_dir = tmp_path / "captures"
    capture_dir.mkdir()
    (capture_dir / f"{sfn_row.key}.html").write_text(page_html, encoding="utf-8")

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps([{
        "society": sfn_row.society, "conference": sfn_row.conference,
        "acronym": sfn_row.acronym, "year": sfn_row.year, "url": sfn_row.url,
        "discipline": sfn_row.discipline, "country": sfn_row.country,
        "event_dates": sfn_row.event_dates, "notes": sfn_row.notes,
    }]), encoding="utf-8")

    adapter = SocietyPagesAdapter(mode="captured", capture_dir=capture_dir, registry_path=registry_path)
    bundle = adapter.fetch(_NetworkForbidden())

    assert len(bundle.records) == 1
    assert bundle.records[0]["key"] == "neuroscience-2026"
    assert bundle.records[0]["html"] == page_html

    series, instances = adapter.parse(bundle)
    assert len(instances) == 1
    assert len(instances[0].deadlines) == 13


def test_captured_mode_records_a_warning_when_the_file_is_missing(tmp_path, sfn_row):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps([{
        "society": sfn_row.society, "conference": sfn_row.conference,
        "acronym": sfn_row.acronym, "year": sfn_row.year, "url": sfn_row.url,
    }]), encoding="utf-8")

    adapter = SocietyPagesAdapter(
        mode="captured", capture_dir=tmp_path / "empty", registry_path=registry_path
    )
    bundle = adapter.fetch(None)  # no client needed in captured mode

    assert bundle.records == []
    assert len(bundle.meta["fetch_warnings"]) == 1
    assert "neuroscience-2026" in bundle.meta["fetch_warnings"][0]


def test_http_mode_sets_an_explicit_min_bytes(tmp_path, sfn_row, page_html):
    """A CDN interstitial or soft-404 must raise rather than be cached as a
    healthy fetch of nothing -- SPIE, ieee.org and sfn.org all fail exactly
    this way at HTTP 200 (see PoliteClient._validate)."""
    seen = {}

    class _RecordingClient:
        def get(self, url, *, min_bytes=0, **kwargs):
            seen["url"] = url
            seen["min_bytes"] = min_bytes

            class _Resp:
                def text(self_inner) -> str:
                    return page_html

            return _Resp()

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps([{
        "society": sfn_row.society, "conference": sfn_row.conference,
        "acronym": sfn_row.acronym, "year": sfn_row.year, "url": sfn_row.url,
    }]), encoding="utf-8")

    adapter = SocietyPagesAdapter(mode="http", registry_path=registry_path)
    bundle = adapter.fetch(_RecordingClient())

    assert seen["url"] == sfn_row.url
    assert seen["min_bytes"] > 0
    assert len(bundle.records) == 1


def test_http_mode_records_a_warning_and_continues_past_a_fetch_error(tmp_path, sfn_row):
    from tools.retrieval.collect.core.http import FetchError

    class _AlwaysFails:
        def get(self, url, *, min_bytes=0, **kwargs):
            raise FetchError(url, "HTTP 404", 404)

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps([{
        "society": sfn_row.society, "conference": sfn_row.conference,
        "acronym": sfn_row.acronym, "year": sfn_row.year, "url": sfn_row.url,
    }]), encoding="utf-8")

    adapter = SocietyPagesAdapter(mode="http", registry_path=registry_path)
    bundle = adapter.fetch(_AlwaysFails())

    assert bundle.records == []
    assert len(bundle.meta["fetch_warnings"]) == 1
    assert "404" in bundle.meta["fetch_warnings"][0]


def test_fetch_respects_the_limit_argument(tmp_path):
    calls = []

    class _CountingClient:
        def get(self, url, *, min_bytes=0, **kwargs):
            calls.append(url)

            class _Resp:
                def text(self_inner) -> str:
                    return "x" * (min_bytes + 1)

            return _Resp()

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps([
        {"society": "A", "conference": "A26", "acronym": "A", "year": 2026, "url": "https://a.example"},
        {"society": "B", "conference": "B26", "acronym": "B", "year": 2026, "url": "https://b.example"},
        {"society": "C", "conference": "C26", "acronym": "C", "year": 2026, "url": "https://c.example"},
    ]), encoding="utf-8")

    adapter = SocietyPagesAdapter(mode="http", registry_path=registry_path)
    adapter.fetch(_CountingClient(), limit=1)

    assert len(calls) == 1


def test_browser_mode_raises_a_clear_error_rather_than_importing_playwright(tmp_path, sfn_row):
    """No playwright in this environment; the failure must name the reason,
    not surface an ImportError from deep inside the adapter."""
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps([{
        "society": sfn_row.society, "conference": sfn_row.conference,
        "acronym": sfn_row.acronym, "year": sfn_row.year, "url": sfn_row.url,
    }]), encoding="utf-8")

    adapter = SocietyPagesAdapter(mode="browser", registry_path=registry_path)
    with pytest.raises(RuntimeError, match="playwright"):
        adapter.fetch(None)


def test_importing_the_module_never_requires_playwright():
    """Playwright must be an optional extra: importing this module (which
    every other test in this file already does) must not need it installed.
    This test simply documents that guarantee explicitly."""
    import sys

    assert "playwright" not in sys.modules


# --- the seam: parse touches no network ------------------------------


def test_parse_touches_no_network(sfn_bundle):
    series, instances = SocietyPagesAdapter().parse(sfn_bundle)
    assert len(instances) == 1
    assert len(series) == 1


def test_parse_returns_nothing_for_an_empty_bundle():
    bundle = RawBundle(source="society_pages", run_id="x", fetched_at="y", records=[], meta={})
    series, instances = SocietyPagesAdapter().parse(bundle)
    assert series == []
    assert instances == []


def test_parse_skips_a_record_with_no_html():
    bundle = RawBundle(
        source="society_pages", run_id="x", fetched_at="y",
        records=[{"acronym": "X", "year": 2026, "society": "S", "conference": "C", "url": "https://x"}],
        meta={},
    )
    series, instances = SocietyPagesAdapter().parse(bundle)
    assert instances == []
