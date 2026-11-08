"""The website enrichment layer, offline.

Nothing here touches the network or the model server. The properties that matter
are the ones that keep a language model's output from becoming an unverified
fact in the store, so most of these tests feed ``verify`` a deliberately
fabricated response and require it to be refused.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from tools.retrieval.collect.conferences import enrich
from tools.retrieval.collect.conferences.record import (
    ConferenceInstance,
    ConferenceSeries,
    Deadline,
)
from tools.retrieval.collect.conferences.store import ConferenceStore
from tools.retrieval.collect.core.http import FetchError, RobotsGate

NOW = datetime(2026, 8, 16, 12, 0, 0, tzinfo=UTC)

PAGE = """
<html>
<head><title>3DV 2027</title></head>
<nav><ul><li><a href="/dates">Important Dates</a></li><li><a href="/cfp">Call for Papers</a></li></ul></nav>
<!-- a comment that must not survive -->
<body>
<p>The 14th International Conference on 3D Vision will be held in Thessaloniki, Greece.</p>
<p>Since 2013, 3DV has been a platform for research covering 3D computer vision and
graphics, from novel optical sensors and signal processing to geometric modeling and
rendering.</p>
<h2>Important Dates</h2>
<p>All deadlines are 11:00 am Pacific Time (PDT).</p>
<ul><li>Paper Submission Aug 28, 2026</li><li>Final Notification Dec 02, 2026</li></ul>
</body>
<footer>Sponsored by everyone. Copyright 2027.</footer>
</html>
"""


def task(**overrides) -> enrich.EnrichmentTask:
    base = {
        "instance_key": "conf/3dv|2027|conference",
        "url": "https://3dvconf.github.io/2027/",
        "acronym": "3DV",
        "title": "Fourteenth International Conference on 3D Vision",
        "year_label": "2027",
        "gaps": ("description", "deadlines", "topics"),
    }
    return enrich.EnrichmentTask(**{**base, **overrides})


def instance(**overrides) -> ConferenceInstance:
    deadlines = overrides.pop("deadlines", [])
    base = {
        "source": "openreview",
        "source_record_id": "3dv27",
        "series_key": "conf/3dv",
        "title": "Fourteenth International Conference on 3D Vision",
        "acronym": "3DV",
        "year_label": "2027",
        "url": "https://3dvconf.github.io/2027/",
    }
    return ConferenceInstance(**{**base, **overrides}, deadlines=deadlines)


class StubClient:
    """Answers a fixed map of URLs. Anything else raises, as a dead host would."""

    def __init__(self, pages: dict[str, str], status: dict[str, int] | None = None) -> None:
        self.pages = pages
        self.status = status or {}
        self.host_intervals: dict[str, float] = {}
        self.requested: list[str] = []

    def get(self, url: str, **_kwargs):
        from tools.retrieval.collect.core.http import Response

        self.requested.append(url)
        if url in self.pages:
            return Response(url=url, status=200, body=self.pages[url].encode())
        raise FetchError(url, "not found", self.status.get(url, 404))


# --- gap detection -------------------------------------------------------


def test_a_complete_record_is_left_alone():
    series = {"conf/3dv": ConferenceSeries(
        series_key="conf/3dv", full_name="International Conference on 3D Vision"
    )}
    record = instance(
        topics=["3d vision"],
        deadlines=[Deadline(kind="submission", instant="2026-08-28T18:00:00Z", basis="PDT")],
    )
    assert enrich.gaps_for(record, series) == ()


def test_each_missing_field_is_named():
    record = instance()
    assert enrich.gaps_for(record, {}) == ("description", "deadlines", "topics")


def test_a_generated_summary_closes_the_description_gap():
    record = instance(generated_summary="x" * 200, topics=["3d vision"])
    assert "description" not in enrich.gaps_for(record, {})


def test_a_deadline_without_a_basis_still_counts_as_missing():
    record = instance(
        deadlines=[Deadline(kind="submission", instant="2026-08-28T18:00:00Z", basis="")]
    )
    assert "deadlines" in enrich.gaps_for(record, {})


def test_a_non_url_is_never_fetched():
    """OpenReview publishes whatever the organizers typed into a text box."""
    assert task(url="TBD").is_fetchable is False
    assert task(url="").is_fetchable is False
    # Two URLs in one field. urllib raises InvalidURL on the space, from inside
    # a worker, which is a crash to catch rather than a record to skip.
    assert task(url="https://glee-competition.com; https://other.org").is_fetchable is False
    assert task(url="https://x.org/a\npath").is_fetchable is False
    assert task().is_fetchable is True


def test_a_cached_verdict_is_not_re_asked():
    record = instance()
    cache = {record.instance_key: enrich.EnrichmentRecord(
        instance_key=record.instance_key, status="robots_denied"
    )}
    tasks, census = enrich.plan_enrichment([record], [], cache=cache)
    assert tasks == []
    assert census["cached"] == 1


def test_a_closed_edition_is_skipped_unless_asked_for():
    """Past deadlines mean closed. The ``active`` flag is not consulted.

    That flag is set at persist time, so a freshly parsed record always carries
    the dataclass default of True — filtering on it queued 1,037 records while
    reporting "0 inactive (skipped)", three quarters of them past editions.
    """
    closed = instance(deadlines=[
        Deadline(kind="submission", instant="2020-01-01T00:00:00Z", basis="AoE")
    ], active=True)  # the flag says active; the dates say otherwise

    tasks, census = enrich.plan_enrichment([closed], [], active_only=True, now=NOW)
    assert tasks == [] and census["closed"] == 1

    tasks, _ = enrich.plan_enrichment([closed], [], active_only=False, now=NOW)
    assert len(tasks) == 1


def test_a_record_with_no_deadline_at_all_is_still_worth_reading():
    """Not knowing when the call closes is the reason to go and look."""
    unknown = instance(active=False)  # flag says inactive, but nothing is dated
    tasks, _ = enrich.plan_enrichment([unknown], [], active_only=True, now=NOW)
    assert len(tasks) == 1


# --- robots ---------------------------------------------------------------


def test_robots_disallow_is_honoured():
    client = StubClient({"https://x.org/robots.txt": "User-agent: *\nDisallow: /private\n"})
    gate = RobotsGate(client, user_agent="mycelium-collector/0.1")
    assert gate.allowed("https://x.org/public")[0] is True
    allowed, why = gate.allowed("https://x.org/private/page")
    assert allowed is False
    assert "disallows" in why


def test_a_missing_robots_file_means_everything_is_allowed():
    """404 is the common case on conference sites and grants full access."""
    gate = RobotsGate(StubClient({}), user_agent="ua")
    assert gate.allowed("https://x.org/anything")[0] is True


def test_an_unreachable_robots_file_means_disallow():
    """RFC 9309: a server that cannot state its rules has not granted permission."""
    client = StubClient({}, status={"https://x.org/robots.txt": 503})
    gate = RobotsGate(client, user_agent="ua")
    allowed, why = gate.allowed("https://x.org/anything")
    assert allowed is False
    assert "treating as disallow" in why


def test_robots_is_fetched_once_per_host():
    client = StubClient({"https://x.org/robots.txt": "User-agent: *\nAllow: /\n"})
    gate = RobotsGate(client, user_agent="ua")
    for path in ("a", "b", "c"):
        gate.allowed(f"https://x.org/{path}")
    assert client.requested.count("https://x.org/robots.txt") == 1


def test_a_published_crawl_delay_widens_our_interval():
    client = StubClient({"https://x.org/robots.txt": "User-agent: *\nCrawl-delay: 7\n"})
    gate = RobotsGate(client, user_agent="ua")
    gate.allowed("https://x.org/page")
    assert client.host_intervals["x.org"] == 7.0


# --- page reduction ------------------------------------------------------


def test_chrome_and_comments_do_not_reach_the_model():
    text = enrich.page_text(PAGE)
    assert "must not survive" not in text
    assert "Sponsored by everyone" not in text
    assert "3D computer vision" in text


def test_a_nav_item_named_important_dates_is_not_a_dates_section():
    """The bug this check exists for: the word without a date matched everything."""
    nav_only = "<nav><a href='/d'>Important Dates</a></nav><body><p>Welcome.</p></body>"
    assert enrich.states_dates(enrich.page_text(nav_only)) is False
    assert enrich.states_dates(enrich.page_text(PAGE)) is True


def test_only_same_site_cfp_links_are_followed():
    body = """
    <a href="/important-dates">Important Dates</a>
    <a href="https://elsewhere.org/cfp">Call for Papers</a>
    <a href="/sponsors">Sponsors</a>
    """
    links = enrich.cfp_links(body, "https://x.org/2027/")
    assert links == ["https://x.org/important-dates"]


def test_a_long_page_is_centred_on_its_dates_not_truncated_from_the_top():
    padding = "Sponsor blurb. " * 900
    body = f"<body><p>{padding}</p><h2>Important Dates</h2><p>Paper Submission Aug 28, 2026</p></body>"
    text = enrich.page_text(body, max_chars=2000)
    assert "Aug 28, 2026" in text, "a head-slice would drop every date on the page"


# --- the model's reply ---------------------------------------------------


def test_a_fenced_reply_still_parses():
    assert enrich.extract_json('```json\n{"a": 1}\n```')["a"] == 1
    assert enrich.extract_json('Sure! Here you go:\n{"a": 2}')["a"] == 2
    with pytest.raises(ValueError, match="no JSON object"):
        enrich.extract_json("I could not find anything.")


def test_only_the_missing_fields_are_asked_for():
    prompt = enrich.build_prompt(task(gaps=("deadlines",)), "page")
    assert "every dated submission milestone" in prompt
    assert "the subject topics" not in prompt


# --- verification --------------------------------------------------------


def payload(**overrides) -> dict:
    base = {
        "is_this_venue": True,
        "summary": "3DV is a conference on 3D computer vision and graphics, covering "
                   "optical sensors, geometric modeling and rendering.",
        "purpose": "To advance research in 3D computer vision.",
        "audience": "Researchers in 3D vision and graphics.",
        "topics": ["3d computer vision", "geometric modeling"],
        "submission_types": ["paper"],
        "deadlines": [
            {"kind": "submission", "round_label": "", "date_text": "Aug 28, 2026",
             "timezone_text": "11:00 am Pacific Time (PDT)"}
        ],
        "_raw": "{}",
        "_model": "stub",
    }
    return {**base, **overrides}


def verified(**overrides) -> enrich.EnrichmentRecord:
    text = enrich.page_text(PAGE)
    return enrich.verify(
        task(), payload(**overrides), text,
        enrich.EnrichmentRecord(instance_key="k", url="https://x.org/"),
    )


def test_a_grounded_response_is_accepted():
    record = verified()
    assert record.status == "ok"
    assert record.topics == ["3d computer vision", "geometric modeling"]
    assert len(record.deadlines) == 1


def test_a_date_that_is_not_on_the_page_is_refused():
    """The check the whole design rests on."""
    record = verified(deadlines=[
        {"kind": "submission", "date_text": "December 31, 2026", "timezone_text": "AoE",
         "round_label": ""}
    ])
    assert record.deadlines == []
    assert any("not on the page" in r["why"] for r in record.rejected)


def test_an_unknown_deadline_kind_is_refused():
    record = verified(deadlines=[
        {"kind": "vibes", "date_text": "Aug 28, 2026", "timezone_text": "", "round_label": ""}
    ])
    assert record.deadlines == []
    assert any("unknown deadline kind" in r["why"] for r in record.rejected)


def test_prose_written_from_priors_is_refused_whole():
    """Summary, purpose and audience are one generation and fall together.

    Checking only the summary let ACL 2027's purpose and audience — written from
    the same priors in the same breath, about a placeholder page — through.
    """
    record = verified(
        summary="A premier gathering for maritime archaeology in Antarctica.",
        purpose="To advance underwater basket weaving scholarship.",
        audience="Marine archaeologists and polar historians.",
    )
    assert record.summary == ""
    assert record.purpose == ""
    assert record.audience == ""
    assert any(r["field"] == "prose" for r in record.rejected)


def test_a_topic_sharing_no_word_with_the_page_is_refused():
    record = verified(topics=["3d computer vision", "maritime archaeology"])
    assert record.topics == ["3d computer vision"]
    assert any("no word of it appears" in r["why"] for r in record.rejected)


def test_a_page_about_a_different_venue_is_refused_outright():
    other = "<body><p>Welcome to the International Congress of Beekeeping, held annually "
    other += "in Ljubljana since 1873. Honey production and hive management.</p></body>"
    record = enrich.verify(
        task(), payload(), enrich.page_text(other),
        enrich.EnrichmentRecord(instance_key="k"),
    )
    assert record.status == "not_the_venue"
    assert record.deadlines == [] and record.summary == ""


def test_the_models_own_denial_is_believed():
    record = verified(is_this_venue=False)
    assert record.status == "not_the_venue"


def test_we_parse_the_date_ourselves_rather_than_trusting_the_model():
    """The model wrote "PDT" for a December date; December is PST.

    The model only ever locates the string. ``resolve_instant`` does the
    arithmetic, through zoneinfo, for the actual date in question — so the hour
    is right even when the label the page used is not.
    """
    record = verified(deadlines=[
        {"kind": "notification", "round_label": "final", "date_text": "Dec 02, 2026",
         "timezone_text": "11:00 am Pacific Time (PDT)"}
    ])
    assert record.deadlines[0]["instant"] == "2026-12-02T19:00:00Z"  # 11:00 PST, not PDT


def test_an_unstated_timezone_is_marked_inferred_not_assumed_silently():
    record = verified(deadlines=[
        {"kind": "submission", "round_label": "", "date_text": "Aug 28, 2026",
         "timezone_text": ""}
    ])
    assert record.deadlines[0]["basis"].startswith("inferred:")


@pytest.mark.parametrize(
    ("text", "basis"),
    [
        ("AoE", "AoE"),
        ("23:59 UTC", "UTC+0"),
        ("11:00 am Pacific Time (PDT)", "PDT"),
        ("UTC-8", "UTC-8"),
        ("", "inferred:unstated"),
    ],
)
def test_the_timezone_basis_is_read_from_the_pages_own_wording(text, basis):
    assert enrich.basis_from(text)[0] == basis


def test_every_generated_deadline_is_flagged_estimated():
    record = verified()
    assert all(d["is_estimated"] for d in record.deadlines)
    assert all(d["source"].startswith("enrichment:") for d in record.deadlines)


# --- application ---------------------------------------------------------


def test_a_published_deadline_beats_a_generated_one():
    record = instance(deadlines=[
        Deadline(kind="submission", round_label="", instant="2026-08-01T00:00:00Z",
                 basis="AoE", source="openreview")
    ])
    result = enrich.EnrichmentRecord(instance_key=record.instance_key, status="ok")
    result.deadlines = [{
        "kind": "submission", "round_label": "", "instant": "2026-08-28T18:00:00Z",
        "basis": "PDT", "raw": "Aug 28, 2026", "source": "enrichment:x", "is_estimated": True,
    }]
    enrich.apply_enrichment([record], {record.instance_key: result})

    assert len(record.deadlines) == 1
    assert record.deadlines[0].source == "openreview", "the source's own date must win"


def test_a_new_round_from_the_website_is_added():
    record = instance(deadlines=[
        Deadline(kind="submission", instant="2026-08-01T00:00:00Z", basis="AoE")
    ])
    result = enrich.EnrichmentRecord(instance_key=record.instance_key, status="ok")
    result.deadlines = [{
        "kind": "abstract", "round_label": "", "instant": "2026-07-25T18:00:00Z",
        "basis": "PDT", "raw": "Jul 25, 2026", "source": "enrichment:x", "is_estimated": True,
    }]
    applied = enrich.apply_enrichment([record], {record.instance_key: result})

    assert applied["deadlines"] == 1
    assert {d.kind for d in record.deadlines} == {"submission", "abstract"}


def test_an_unusable_result_still_records_its_status():
    record = instance()
    result = enrich.EnrichmentRecord(instance_key=record.instance_key, status="robots_denied")
    enrich.apply_enrichment([record], {record.instance_key: result})
    assert record.enrichment_status == "robots_denied"
    assert record.generated_summary == ""


def test_the_composed_summary_reads_in_the_order_a_reader_needs():
    result = enrich.EnrichmentRecord(
        instance_key="k", summary="What it is.", purpose="Why it exists.",
        audience="Who submits.",
    )
    assert enrich.compose_summary(result) == "What it is.\n\nWhy it exists.\n\nWho submits."


# --- persistence ---------------------------------------------------------


def test_an_ordinary_collection_run_cannot_wipe_an_enrichment(tmp_path):
    """The adapter re-emits every record with the generated fields empty.

    Without the carry-forward the enrichment would survive exactly until the next
    fetch, which is the kind of bug that looks like the model got worse.
    """
    with ConferenceStore(tmp_path / "conferences.db") as store:
        enriched = instance(
            generated_summary="A summary recovered from the venue's website.",
            generated_topics=["3d vision"],
            enrichment_status="ok",
        )
        store.upsert_instances([enriched])

        # The next ordinary run: same record, straight from the adapter.
        store.upsert_instances([instance()])
        stored = store.all_instances()[0]

    assert stored.generated_summary == "A summary recovered from the venue's website."
    assert stored.generated_topics == ["3d vision"]
    assert stored.enrichment_status == "ok"


def test_enrichment_rows_round_trip(tmp_path):
    with ConferenceStore(tmp_path / "conferences.db") as store:
        record = enrich.EnrichmentRecord(
            instance_key="k", url="https://x.org/", status="ok", summary="s",
            topics=["a", "b"], deadlines=[{"kind": "submission"}],
            rejected=[{"field": "topic", "value": "x", "why": "y"}],
        )
        store.write_enrichment([record])
        back = store.read_enrichment()

    assert back["k"].summary == "s"
    assert back["k"].topics == ["a", "b"]
    assert back["k"].rejected[0]["why"] == "y"
    assert store.count_by_enrichment_status if True else None


def test_the_enrichment_columns_are_added_to_an_existing_database(tmp_path):
    """A store created before this feature must migrate, not raise."""
    import sqlite3

    path = tmp_path / "conferences.db"
    with ConferenceStore(path) as store:
        store.upsert_instances([instance()])
    conn = sqlite3.connect(path)
    conn.execute("ALTER TABLE instances DROP COLUMN generated_summary")
    conn.commit()
    conn.close()

    with ConferenceStore(path) as store:
        columns = {r[1] for r in store.conn.execute("PRAGMA table_info(instances)")}
    assert "generated_summary" in columns


def test_json_shapes_survive_the_round_trip():
    record = enrich.EnrichmentRecord(instance_key="k", topics=["a"], deadlines=[{"kind": "x"}])
    row = record.to_row()
    assert json.loads(row["topics"]) == ["a"]
    assert enrich.EnrichmentRecord.from_row(row).deadlines == [{"kind": "x"}]


def test_a_summary_only_enrichment_actually_reaches_the_store(tmp_path):
    """The change detector must see an edit that touches only generated columns.

    Listing them as bookkeeping neutralised the adapter re-emit and also made a
    genuine enrichment write invisible: the row compared equal to its stored
    self, the store reported 'unchanged', and nothing was written. Five of nine
    generated summaries vanished that way — the four that survived were exactly
    the ones that also gained a deadline.
    """
    with ConferenceStore(tmp_path / "conferences.db") as store:
        store.upsert_instances([instance()])

        enriched = instance(
            generated_summary="Recovered from the venue's website.",
            generated_topics=["3d vision"],
            enrichment_status="ok",
        )
        stats = store.upsert_instances([enriched])
        assert stats.updated == 1, "a summary-only change is still a change"

        stored = store.all_instances()[0]

    assert stored.generated_summary == "Recovered from the venue's website."
    assert stored.generated_topics == ["3d vision"]


def test_re_applying_a_cached_result_is_idempotent():
    """Apply runs from the cache too, so a result that failed to land can heal."""
    record = instance()
    result = enrich.EnrichmentRecord(
        instance_key=record.instance_key, status="ok", summary="What it is.",
        topics=["3d vision"],
    )
    first = enrich.apply_enrichment([record], {record.instance_key: result})
    second = enrich.apply_enrichment([record], {record.instance_key: result})

    assert first["summaries"] == 1
    assert second["summaries"] == 0, "a second apply must not overwrite or double-count"
    assert record.generated_summary == "What it is."


def test_two_urls_on_one_host_share_a_lock_but_different_hosts_do_not():
    """Sixteen workers must not become sixteen simultaneous hits on one site."""
    import tools.retrieval.collect.runner as pl

    locks = pl._HostLocks()
    assert locks.for_url("https://x.org/a") is locks.for_url("https://x.org/b")
    assert locks.for_url("https://x.org/a") is not locks.for_url("https://y.org/a")


def test_the_host_lock_actually_serializes_same_host_work():
    import threading

    import tools.retrieval.collect.runner as pl

    locks = pl._HostLocks()
    overlapping = []
    inside = []

    def worker(url):
        with locks.for_url(url):
            inside.append(url)
            overlapping.append(len(inside))
            inside.pop()

    threads = [threading.Thread(target=worker, args=("https://same.org/p",)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert max(overlapping) == 1, "two workers were inside one host's lock at once"


def test_a_transient_failure_is_retried_but_a_settled_verdict_is_not():
    """321 model_failed rows must not become 321 permanent data gaps.

    One over-concurrent run wrote that many in a sitting. Treating them as
    answers would have excluded every one of those records from enrichment
    forever — a momentary server overload turning into a permanent hole.
    """
    record = instance()

    for transient in ("model_failed", "fetch_failed", "thin_page"):
        cache = {record.instance_key: enrich.EnrichmentRecord(
            instance_key=record.instance_key, status=transient
        )}
        tasks, _ = enrich.plan_enrichment([record], [], cache=cache, now=NOW)
        assert len(tasks) == 1, f"{transient} is about the moment, not the page"

    for settled in ("ok", "robots_denied", "not_the_venue"):
        cache = {record.instance_key: enrich.EnrichmentRecord(
            instance_key=record.instance_key, status=settled
        )}
        tasks, census = enrich.plan_enrichment([record], [], cache=cache, now=NOW)
        assert tasks == [], f"{settled} is an answer; asking again is rude"
        assert census["cached"] == 1


@pytest.mark.parametrize(
    ("written", "iso"),
    [
        ("May 25th, 2026", "2026-05-25"),
        ("August 31st, 2026", "2026-08-31"),
        ("July 22nd, 2026", "2026-07-22"),
        ("September 3rd, 2026", "2026-09-03"),
        ("May 23, 2026 23:59 PT", "2026-05-23"),
    ],
)
def test_dates_written_the_way_people_write_them_are_parsed(written, iso):
    from tools.retrieval.collect.core.text import to_iso_date

    assert to_iso_date(written) is None, "the shared parser has never needed these"
    assert to_iso_date(enrich.normalize_date_text(written)) == iso


@pytest.mark.parametrize(
    "ambiguous",
    [
        "August 2026",                       # a month, not a day
        "the week of March 25th",            # not a date at all
        "12 June 2026 3 July 2026",          # original and extension in one field
        "April 25, 2024 ➡ May 2nd 2024",     # ditto, with an arrow
    ],
)
def test_genuinely_ambiguous_dates_stay_refused(ambiguous):
    """Normalization must not become guessing. A wrong deadline is worse than none."""
    from tools.retrieval.collect.core.text import to_iso_date

    assert to_iso_date(enrich.normalize_date_text(ambiguous)) is None
