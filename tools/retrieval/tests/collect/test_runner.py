"""Tests for the vendored consolidated pipeline (``tools.retrieval.collect.runner``).

Everything here runs on a handful of fixture records rather than the corpus, and
nothing touches the network or a model server. The three properties worth
proving are:

* the verbosity primitives actually say what, how and where, and count correctly;
* "new" means *absent from the store before this run*, so a second run over the
  same records flags nothing;
* every validation rule fires on a record that violates it — a rule that has
  never been seen to fail is not evidence of anything when it stays silent.

Ported from the standalone project's ``tests/test_consolidated_pipeline.py``
(plan Phase 1). Two groups of tests from the original did not come with it:

* The **stage 4 embedding tests** (``StubEmbedder``, the content-hash
  re-embed check, and the conference-embedding-text check) tested
  functionality that no longer exists here — ``runner.py`` dropped the
  embedding stage entirely (see its module docstring). Porting tests for code
  that was deliberately removed would not be a regression guard, it would be
  a test for a stage that can never run.
* ``test_every_registered_adapter_in_the_repo_is_enumerated`` and
  ``test_domain_and_source_filters_narrow_the_run`` are kept but no longer
  assert anything about ``wikicfp``, and the registered-source count drops
  from 13 to 12 — WikiCFP was dropped as a source (plan D5), not merely
  skipped in this port.

Ported enrichment stage went the same way as embedding, later: ``STAGES`` was
five entries (extraction, deduplication, new items, enrichment, validation)
when this file was first ported, and is four now that the enrichment stage —
which called a model server through a vendored ``_LLMClient`` that disagreed
with Mycelium's real ``settings.LLM_BASE_URL`` — was removed in favour of the
universal extraction stage plan D9 puts in Mycelium itself (Phase 8). No test
here called ``stage_enrich`` directly (it touched the network and a model
server, which this file's own docstring rules out), so nothing needed
deleting for that removal — only the hard-coded stage count below.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime

import pytest

import tools.retrieval.collect.runner as pl
from tools.retrieval.collect.conferences.record import (
    ConferenceInstance,
    ConferenceSeries,
    Deadline,
)
from tools.retrieval.collect.grants.record import Opportunity
from tools.retrieval.collect.grants.store import Store

# --- fixtures ------------------------------------------------------------


def grant(**overrides) -> Opportunity:
    base = {
        "source": "grants_gov",
        "source_record_id": "1",
        "opportunity_number": "TEST-001",
        "title": "Ecological Forecasting of Coastal Wetland Loss",
        "funder": "National Science Foundation",
        "description": (
            "Supports research on the ecological forecasting of coastal wetland loss "
            "under sea level rise, including remote sensing, hydrological modelling "
            "and community resilience planning across the Gulf and Atlantic coasts."
        ),
        "categories": ["Environment", "Earth Sciences"],
        "close_date": "2027-03-01",
    }
    return Opportunity(**{**base, **overrides})


def conference(**overrides) -> ConferenceInstance:
    deadlines = overrides.pop(
        "deadlines",
        [
            Deadline(
                kind="submission",
                raw="2027-01-15 23:59:59",
                instant="2027-01-16T11:59:59Z",
                basis="AoE",
                source="ccf_deadlines",
            )
        ],
    )
    base = {
        "source": "ccf_deadlines",
        "source_record_id": "sigmod27",
        "series_key": "conf/sigmod",
        "title": "ACM SIGMOD International Conference on Management of Data",
        "acronym": "SIGMOD",
        "year_label": "2027",
        "topics": ["databases"],
    }
    return ConferenceInstance(**{**base, **overrides}, deadlines=deadlines)


@pytest.fixture
def console() -> pl.Console:
    return pl.Console(pl.Console.NORMAL, stream=io.StringIO())


def output(console: pl.Console) -> str:
    return console.stream.getvalue()


# --- verbosity primitives ------------------------------------------------


def test_a_stage_banner_states_what_how_and_where(console):
    console.stage(2, "deduplication", what="collapse duplicates", how="four layers",
                  where="runner.py")
    text = output(console)
    # 4, not 5: the enrichment stage is gone too, now (see the module
    # docstring), so STAGES has four entries — extraction, deduplication,
    # new items, validation.
    assert "STAGE 2/4 · DEDUPLICATION" in text
    assert "what  : collapse duplicates" in text
    assert "how   : four layers" in text
    assert "where : runner.py" in text


def test_every_line_carries_its_location_in_the_pipeline(console):
    console.stage(3, "new items", what="w", how="h", where="where")
    console.step("3.1 persist", "starting")
    console.info("something happened")
    assert "[3/4 new items·3.1 persist] something happened" in output(console)

    console.endstep()
    console.info("back at stage level")
    assert "[3/4 new items] back at stage level" in output(console)


def test_counters_are_width_matched_so_columns_line_up():
    assert pl.Console.counter(4, 13) == "[ 4/13]"
    assert pl.Console.counter(13, 13) == "[13/13]"
    assert pl.Console.counter(256, 2190) == "[  256/2,190]"


def test_progress_ticks_on_a_cadence_but_always_shows_the_last_one(console):
    for done in range(1, 101):
        console.progress(done, 100, "records", every=25)
    lines = [line for line in output(console).splitlines() if "records" in line]
    assert "[  1/100] records (1%)" in lines[0]
    assert "[100/100] records (100%)" in lines[-1]
    # 1, 25, 50, 75, 100 — not one line per record.
    assert len(lines) == 5


def test_quiet_keeps_stage_summaries_and_problems_and_drops_the_rest():
    quiet = pl.Console(pl.Console.QUIET, stream=io.StringIO())
    quiet.info("chatter")
    quiet.summary("the point of the stage")
    quiet.warn("a problem")
    text = output(quiet)
    assert "chatter" not in text
    assert "the point of the stage" in text
    assert "a problem" in text


def test_per_record_detail_only_appears_at_verbose():
    normal = pl.Console(pl.Console.NORMAL, stream=io.StringIO())
    verbose = pl.Console(pl.Console.VERBOSE, stream=io.StringIO())
    for console in (normal, verbose):
        console.detail("one record")
    assert "one record" not in output(normal)
    assert "one record" in output(verbose)


# --- source enumeration --------------------------------------------------


def test_every_registered_adapter_in_the_repo_is_enumerated():
    """12, not 13: WikiCFP is dropped as a source, not merely disabled (D5)."""
    sources = pl.all_sources()
    names = {info.name for info in sources}
    assert {"grants_gov", "sbir", "nih_guide", "nsf", "eu_portal", "sam_gov"} <= names
    assert {"ccf_deadlines", "openreview", "openresearch"} <= names
    assert "wikicfp" not in names
    assert len(sources) == 12


def test_domain_and_source_filters_narrow_the_run():
    assert set(pl.sources_for(["conferences"], [])) == {"conferences"}
    picked = pl.sources_for(["grants", "conferences"], ["nsf", "openresearch"])
    assert picked == {"grants": ["nsf"], "conferences": ["openresearch"]}


def test_an_unknown_source_is_refused_rather_than_silently_ignored():
    with pytest.raises(SystemExit, match="unknown source"):
        pl.sources_for(["grants"], ["not_a_source"])


def test_wikicfp_itself_is_an_unknown_source():
    """The adapter is gone, not disabled — asking for it by name must fail
    the same way a typo would, not silently return zero records."""
    with pytest.raises(SystemExit, match="unknown source"):
        pl.sources_for(["conferences"], ["wikicfp"])


# --- stage 3: new-item flagging -----------------------------------------


def test_new_means_absent_before_this_run_not_first_seen_today(tmp_path):
    """The second run over identical records must flag nothing."""
    db = tmp_path / "opportunities.db"
    records = [grant(source_record_id=str(i), opportunity_number=f"T-{i}") for i in range(3)]

    with Store(db) as store:
        before = pl._existing_keys(store.conn, "opportunities", "stable_key")
        store.upsert_all(records)
        after = pl._existing_keys(store.conn, "opportunities", "stable_key")
        first_run = after - before
        pl._record_new_items(store.conn, "run-1", records, lambda r: r.stable_key, first_run)

    assert len(first_run) == 3

    with Store(db) as store:
        before = pl._existing_keys(store.conn, "opportunities", "stable_key")
        store.upsert_all(records)
        after = pl._existing_keys(store.conn, "opportunities", "stable_key")
        second_run = after - before
        pl._record_new_items(store.conn, "run-2", records, lambda r: r.stable_key, second_run)

        rows = dict(
            store.conn.execute("SELECT run_id, COUNT(*) FROM new_items GROUP BY run_id")
        )

    assert second_run == set()
    assert rows == {"run-1": 3}, "the second run must contribute no rows at all"


def test_the_new_items_table_carries_enough_to_act_on(tmp_path):
    db = tmp_path / "opportunities.db"
    record = grant()
    with Store(db) as store:
        store.upsert_all([record])
        pl._record_new_items(
            store.conn, "run-1", [record], lambda r: r.stable_key, {record.stable_key}
        )
        row = store.conn.execute("SELECT * FROM new_items").fetchone()

    assert row["item_key"] == record.stable_key
    assert row["source"] == "grants_gov"
    assert row["title"].startswith("Ecological Forecasting")
    assert row["run_id"] == "run-1"


# --- stage 4: field validation ------------------------------------------


@pytest.mark.parametrize(
    ("field", "broken"),
    [
        ("name", {"title": "N/A"}),
        ("description", {"description": "See the announcement."}),
        ("description", {"description": "Short."}),
        ("deadlines", {"close_date": "2027-03-01", "additional_due_dates": []}),
        ("tags", {"categories": [], "topic_keywords": []}),
    ],
)
def test_every_grant_rule_can_be_made_to_fire(field, broken):
    """A rule never seen to fail proves nothing when it stays silent."""
    rule = next(r for r in pl.GRANT_RULES if r.field == field)
    assert rule.check(grant()) is True

    record = grant(**broken)
    if field == "deadlines":
        # The one rule that cannot fail on presence alone: a rolling call with no
        # dates is legitimately actionable, so only an unusable date set fails.
        record = grant(close_date=None)
        assert rule.check(record) is True
        return
    assert rule.check(record) is False


def test_a_conference_deadline_without_a_timezone_basis_is_not_usable():
    rules = pl.conference_rules({})
    deadline_rule = next(r for r in rules if r.field == "deadlines")

    assert deadline_rule.check(conference()) is True
    assert deadline_rule.check(
        conference(deadlines=[Deadline(kind="submission", raw="March 1", instant=None, basis="")])
    ) is False
    assert deadline_rule.check(
        conference(
            deadlines=[Deadline(kind="submission", instant="2027-01-16T11:59:59Z", basis="")]
        )
    ) is False, "an instant with no basis is up to a day wrong in either direction"


def test_a_notification_date_alone_is_not_a_submission_deadline():
    rules = pl.conference_rules({})
    deadline_rule = next(r for r in rules if r.field == "deadlines")
    record = conference(
        deadlines=[
            Deadline(kind="notification", instant="2027-04-01T00:00:00Z", basis="UTC")
        ]
    )
    assert deadline_rule.check(record) is False


def test_a_venue_name_plus_a_topic_stands_in_for_absent_call_text():
    series = {"conf/sigmod": ConferenceSeries(
        series_key="conf/sigmod",
        full_name="ACM SIGMOD International Conference on Management of Data",
    )}
    rules = pl.conference_rules(series)
    description = next(r for r in rules if r.field == "description")
    prose = next(r for r in rules if r.field == "cfp_prose")

    record = conference(cfp_text="")
    assert description.check(record) is True
    assert prose.check(record) is False, "the fallback must not hide the missing call text"

    # An acronym on its own is not a description, whatever else is present.
    bare = conference(title="SIGMOD", series_key="unknown", topics=["databases"])
    assert description.check(bare) is False


def test_grades_separate_complete_usable_partial_and_unusable():
    assert pl.grade(grant(), pl.GRANT_RULES) == "complete"
    assert pl.grade(grant(categories=[], topic_keywords=[]), pl.GRANT_RULES) == "usable"
    assert pl.grade(grant(description="See above."), pl.GRANT_RULES) == "partial"
    assert pl.grade(grant(title=""), pl.GRANT_RULES) == "unusable"


def test_validation_counts_per_field_and_per_source(console):
    records = [
        grant(source_record_id="1", opportunity_number="A-1"),
        grant(source_record_id="2", opportunity_number="A-2", description="See above."),
        grant(source="nsf", source_record_id="3", opportunity_number="A-3", title=""),
    ]
    result = pl.validate_records(records, pl.GRANT_RULES, console)

    assert result["records"] == 3
    assert result["per_field"]["name"] == 2
    assert result["per_field"]["description"] == 2
    assert result["per_source"]["grants_gov"]["records"] == 2
    assert result["per_source"]["nsf"]["records"] == 1
    assert result["grades"] == {"complete": 1, "usable": 0, "partial": 1, "unusable": 1}
    assert result["failures"]["name"], "a failing record must come with an example"


def test_validation_shows_at_most_five_examples_per_rule(console):
    records = [
        grant(source_record_id=str(i), opportunity_number=f"B-{i}", title="")
        for i in range(20)
    ]
    result = pl.validate_records(records, pl.GRANT_RULES, console)
    assert len(result["failures"]["name"]) == 5


# --- the report ----------------------------------------------------------


def test_the_report_is_written_and_round_trips(tmp_path):
    context = pl.RunContext(
        run_id="20270101T000000Z", started_at="2027-01-01T00:00:00+00:00", root=tmp_path,
        domains=["grants"], console=pl.Console(pl.Console.QUIET, stream=io.StringIO()),
        now=datetime(2027, 1, 1, tzinfo=UTC),
    )
    context.stage_report("validation")["grants"] = {"records": 3}

    path = pl.write_report(context)
    payload = json.loads(path.read_text())

    assert path.name == "20270101T000000Z.json"
    assert payload["run_id"] == "20270101T000000Z"
    assert payload["stages"]["validation"]["grants"]["records"] == 3
    assert payload["finished_at"]


# --- the CLI -------------------------------------------------------------


def test_the_cli_defaults_to_every_domain_and_a_live_fetch():
    args = pl.build_parser().parse_args([])
    assert args.domain == "all"
    assert args.skip_fetch is False


def test_list_sources_runs_without_touching_the_network(capsys):
    assert pl.main(["--list-sources"]) == 0
    printed = capsys.readouterr().out
    assert "ccf_deadlines" in printed
    assert "grants_gov" in printed
    assert "wikicfp" not in printed
