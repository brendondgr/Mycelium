"""Tests for the ``collect_opportunities`` / ``refresh_dblp_registry`` commands.

Before this file existed, ``grep -rln "collect_opportunities\\|refresh_dblp_
registry"`` across every test tree returned nothing: ~395 lines running the
entire nightly grant/conference pipeline had no test at all.

**The defect this file exists to pin.** ``collect_opportunities.py`` joins
three independently-computed keys:

* ``tools.retrieval.collect.mapping.map_grant`` / ``map_conference`` write
  ``external_id`` from the collector's own upsert key (``Opportunity.
  stable_key`` / ``ConferenceInstance.instance_key``) when it ingests a
  record into ``ContentItem``.
* ``tools.retrieval.collect.extract.ExtractionInput.from_opportunity`` /
  ``from_conference`` build ``.key`` from the *same two* record attributes,
  independently, for the extraction stage.
* The command itself builds ``key_to_source = {item["external_id"]: item
  ["source"] for item in mapped}`` and looks up every extraction outcome by
  ``key_to_source.get(key)`` (module ``collect_opportunities.py``, ~lines
  368-369).

If any one of those three drifts from the other two, the lookup returns
``None`` and the command does ``if source is None: continue`` — silently
skipping the record. The run still reports ``extract: 0 record(s) settled.``
and **exits 0**. This is the same shape of bug that hid the fellowship
eligibility engine never running (``docs/plans/open-opportunity-collector.
md``, risk register): a queryset/lookup that is silently empty instead of
raising.

**Offline strategy.** ``collect_opportunities`` drives a lot of real
infrastructure — network fetch, three SQLite stores, a bounded LLM agent
loop, fastembed. None of that is what this file is testing (each has its own
suite: ``tools/retrieval/tests/collect/``, ``test_collect_mapping.py``,
``test_collect_ingest.py``, ``test_collect_extract.py``). So every test here
stubs exactly four seams on the command's own module object (never the
modules underneath — the point is to exercise the command's *real* wiring
between them):

* ``stage_extract`` — replaced with a fake that hands back caller-built
  ``DomainData`` (real ``Opportunity`` / ``ConferenceInstance`` dataclass
  literals, the ``test_collect_ingest.py`` fixture idiom), so no adapter ever
  makes an HTTP request.
* ``stage_deduplicate`` / ``stage_flag_new`` / ``stage_validate`` — no-ops;
  ``new_keys`` is set directly on the fixture's ``DomainData`` instead of
  being computed by a real (SQLite-backed) flagging pass.
* ``run_extraction`` — replaced with a fake that honours the real function's
  ``only_keys`` filtering contract and returns one ``ExtractionOutcome`` per
  selected record, so no LLM client is ever built and no model call is ever
  made.
* ``embed_pending`` — replaced with a no-op, so no fastembed model is ever
  loaded.

``map_grant``, ``map_conference``, ``ExtractionInput.from_opportunity``,
``ExtractionInput.from_conference``, ``ingest_collected``, and the command's
own ``key_to_source`` join are always the REAL functions — that seam is
exactly what this file exists to protect. Every test also passes
``--skip-fetch`` (so the raw-payload-pruning block, which touches a real
``pipeline.raw_store``, never runs) and ``--checkpoint ""`` (so nothing is
ever written under the repo-relative default checkpoint path).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from io import StringIO

import pytest
from django.core.management import call_command

from tools.retrieval.collect.conferences.record import ConferenceInstance, Deadline
from tools.retrieval.collect.extract import (
    DEFAULT_WORKERS,
    ExtractionInput,
    ExtractionOutcome,
)
from tools.retrieval.collect.grants.record import Opportunity
from tools.retrieval.collect.mapping import map_conference, map_grant
from tools.retrieval.collect.runner import CONFERENCES, GRANTS, DomainData
from tools.retrieval.management.commands import collect_opportunities as cmd
from tools.retrieval.management.commands import refresh_dblp_registry as dblp_cmd
from tools.retrieval.models import ContentItem

TODAY = date(2026, 8, 16)
NOW = datetime(2026, 8, 16, 12, 0, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# Fixture builders — real collector dataclasses, no network, no ORM
# --------------------------------------------------------------------------- #


def _opportunity(sid="g1", *, source="nsf", close_date="2026-11-12", **over):
    """Same idiom as ``test_collect_ingest.py``'s ``_grant_item``, one layer
    lower: this returns the raw ``Opportunity`` the command's fake
    ``stage_extract`` hands back, since the command itself is what calls
    ``map_grant`` / ``ExtractionInput.from_opportunity`` on it."""
    kwargs = dict(
        source=source,
        source_record_id=sid,
        title="Test Research Award",
        funder="Test Funder",
        description="A grant funding foundational research on distributed "
        "systems, intended to support early-career investigators.",
        close_date=close_date,
        currency="USD",
    )
    kwargs.update(over)
    return Opportunity(**kwargs)


def _conference_instance(
    sid="c1", *, source="ccf_deadlines", instant="2026-11-01T00:00:00Z", **over
):
    kwargs = dict(
        source=source,
        source_record_id=sid,
        series_key=f"conf/{sid}",
        title="Test Systems Conference",
        acronym="TSC",
        year_label="2026",
        deadlines=[
            Deadline(kind="submission", raw=instant, instant=instant, source=source),
        ],
    )
    kwargs.update(over)
    return ConferenceInstance(**kwargs)


def _fake_run_extraction(calls):
    """Stands in for ``tools.retrieval.collect.extract.run_extraction``.

    Honours the real function's ``only_keys`` filtering contract (plan §8,
    item 8 / the newness gate) and returns one verified ``ExtractionOutcome``
    per selected record, keyed by ``rec.key`` exactly as the real function's
    own ``dict(pairs)`` return does — that keying is the other half of the
    invariant this file pins, so the fake must not weaken it. Records every
    call's ``only_keys`` and ``max_workers`` in ``calls`` so a test can
    assert on how the command invoked it, not just on what came back.
    """

    def _run(records, *, max_workers=None, checkpoint=None, only_keys=None, **_kw):
        records = list(records)
        calls.append(
            {"records": records, "max_workers": max_workers, "only_keys": only_keys}
        )
        selected = [r for r in records if only_keys is None or r.key in only_keys]
        return {
            rec.key: ExtractionOutcome(
                key=rec.key,
                status="ok",
                attempts=1,
                ai_summary=f"Stub summary for {rec.key}.",
                ai_fields={"summary": "stub", "confidence": "high"},
                summary_source="extracted",
                search_text=f"stub search text {rec.key}",
                search_text_source="extracted",
            )
            for rec in selected
        }

    return _run


def _patch_stages(
    monkeypatch, data: dict[str, DomainData], *, captured: dict | None = None
):
    """Stub the four collector stages plus the report writer and the embed
    sweep, leaving every other name the command imports (``map_grant``,
    ``map_conference``, ``ExtractionInput``, ``ingest_collected``,
    ``apply_to_metadata``, ``prune_expired``) real. ``data`` is what the
    faked ``stage_extract`` hands back; ``captured["context"]``, when a dict
    is passed, records the ``RunContext`` the command actually built, so a
    test can assert on how ``--limit`` / ``--sources`` / ``--workers`` were
    wired through without needing the real (network-touching) stage to run.

    ``data`` must carry one entry per domain the command will actually walk
    (``context.domains``) — the real ``stage_extract`` always populates one
    ``DomainData`` per requested domain, so a caller exercising ``--new-only``
    under the default ``--domain all`` must either build both domains'
    fixtures or pass ``domain="grants"`` / ``"conferences"`` explicitly to
    match this fixture's scope; otherwise the command's own ``for domain in
    context.domains: ... data[domain] ...`` loop raises ``KeyError`` on the
    domain nobody built a fixture for.
    """

    def fake_stage_extract(context):
        if captured is not None:
            captured["context"] = context
        return data

    monkeypatch.setattr(cmd, "stage_extract", fake_stage_extract)
    monkeypatch.setattr(cmd, "stage_deduplicate", lambda context, data: None)
    monkeypatch.setattr(cmd, "stage_flag_new", lambda context, data: None)
    monkeypatch.setattr(cmd, "stage_validate", lambda context, data: 0)
    monkeypatch.setattr(cmd, "write_report", lambda context: None)
    # embed_pending's default embedder loads a real fastembed model; every
    # test here is about the collect -> map -> ingest -> extract seam, not
    # embedding, so it is stubbed out rather than fed a fake vector fn.
    monkeypatch.setattr(cmd, "embed_pending", lambda **kwargs: 0)


_COMMON_ARGS = dict(skip_fetch=True, checkpoint="", no_prune=True)


# --------------------------------------------------------------------------- #
# 1. The key-alignment invariant — identity, not a count (unit level)
# --------------------------------------------------------------------------- #
#
# These two tests need no command, no monkeypatching and no database: they
# pin the invariant at its source, directly on the two functions the plan
# names. A count-based assertion here ("N records extracted") would pass
# vacuously at N=0 if both functions silently agreed on reading nothing; only
# a value-identity assertion catches one function switching to a different
# source field.


def test_mapped_grant_external_id_matches_the_extraction_input_key():
    op = _opportunity("multi-round", close_date="2026-09-01")
    mapped = map_grant(op, today=TODAY)
    extraction_input = ExtractionInput.from_opportunity(op)

    assert mapped["external_id"] == op.stable_key
    assert extraction_input.key == op.stable_key
    assert extraction_input.key == mapped["external_id"]


def test_mapped_conference_external_id_matches_the_extraction_input_key():
    instance = _conference_instance("multi-round")
    mapped = map_conference(instance, series=None, now=NOW)
    extraction_input = ExtractionInput.from_conference(instance, series=None)

    assert mapped["external_id"] == instance.instance_key
    assert extraction_input.key == instance.instance_key
    assert extraction_input.key == mapped["external_id"]


# --------------------------------------------------------------------------- #
# 2. A non-empty extraction actually settles records — and a drift is caught
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_extraction_settles_grant_and_conference_records_with_a_nonzero_count(
    monkeypatch, tmp_path
):
    """The command-level half of the invariant: proves the command's own
    ``key_to_source`` dict (built from ``mapped``, keyed by ``external_id``)
    actually finds the ``ContentItem`` for every record the fake extraction
    settled, for both record kinds. If the command's join used the wrong
    field on either side, this would fail here — not with an exception, but
    with ``extraction_status`` silently absent from the metadata, exactly
    the failure mode this test is written to catch.
    """
    grant = _opportunity("g1")
    instance = _conference_instance("c1")
    data = {
        GRANTS: DomainData(domain=GRANTS, items=[grant]),
        CONFERENCES: DomainData(domain=CONFERENCES, items=[instance]),
    }
    _patch_stages(monkeypatch, data)
    calls: list[dict] = []
    monkeypatch.setattr(cmd, "run_extraction", _fake_run_extraction(calls))

    out = StringIO()
    call_command(
        "collect_opportunities", **_COMMON_ARGS, root=str(tmp_path), stdout=out
    )

    assert "extract: 2 record(s) settled." in out.getvalue()

    grant_item = ContentItem.objects.get(
        source="grants:nsf", external_id=grant.stable_key
    )
    assert grant_item.metadata["extraction_status"] == "ok"
    assert grant_item.metadata["ai_summary"] == f"Stub summary for {grant.stable_key}."

    conf_item = ContentItem.objects.get(
        source="conf:ccf_deadlines", external_id=instance.instance_key
    )
    assert conf_item.metadata["extraction_status"] == "ok"


@pytest.mark.django_db
def test_a_drifted_external_id_is_caught_not_silently_swallowed(monkeypatch, tmp_path):
    """Simulates exactly the drift the plan warns about (module docstring
    lines ~368-369, ``if source is None: continue``): a future ``map_grant``
    that stops writing ``external_id`` as ``record.stable_key``. This is the
    canary that proves this suite would actually fail, not just pass, on the
    regression it is written to guard against: ``extracted`` stays at 0 and
    the record's metadata is never touched, in a run that still exits 0 and
    still prints a SUCCESS line — the whole reason the plan calls this a
    silent failure rather than a crash.
    """
    op = _opportunity("drift")
    data = {GRANTS: DomainData(domain=GRANTS, items=[op])}
    _patch_stages(monkeypatch, data)
    monkeypatch.setattr(cmd, "run_extraction", _fake_run_extraction([]))

    real_map_grant = cmd.map_grant

    def drifted_map_grant(record, *, today):
        item = real_map_grant(record, today=today)
        if item is not None:
            # A stand-in for a future refactor that keys ContentItem on
            # something other than stable_key -- ExtractionInput.key (built
            # separately, below) never learns about this change.
            item["external_id"] = f"drifted:{item['external_id']}"
        return item

    monkeypatch.setattr(cmd, "map_grant", drifted_map_grant)

    out = StringIO()
    call_command(
        "collect_opportunities", **_COMMON_ARGS, root=str(tmp_path), stdout=out
    )

    assert "extract: 0 record(s) settled." in out.getvalue()
    # The record was still ingested -- under the drifted id -- but the
    # extraction verdict never reached it: the join missed silently instead
    # of raising, which is exactly the bug this test exists to make loud.
    drifted_item = ContentItem.objects.get(external_id=f"drifted:{op.stable_key}")
    assert "extraction_status" not in drifted_item.metadata


# --------------------------------------------------------------------------- #
# 3. --new-only: only flagged-new records extract; a quiet re-run says so
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_new_only_extracts_only_records_flagged_new(monkeypatch, tmp_path):
    new_op = _opportunity("new1")
    old_op = _opportunity("old1", source="sbir")
    data = {
        GRANTS: DomainData(
            domain=GRANTS, items=[new_op, old_op], new_keys=[new_op.stable_key]
        )
    }
    _patch_stages(monkeypatch, data)
    calls: list[dict] = []
    monkeypatch.setattr(cmd, "run_extraction", _fake_run_extraction(calls))

    out = StringIO()
    call_command(
        "collect_opportunities",
        **_COMMON_ARGS,
        root=str(tmp_path),
        domain="grants",
        new_only=True,
        stdout=out,
    )

    assert calls[0]["only_keys"] == {new_op.stable_key}
    assert (
        "extract: --new-only scoped to 1 of 2 collected record(s)." in out.getvalue()
    )
    assert "extract: 1 record(s) settled." in out.getvalue()

    new_item = ContentItem.objects.get(external_id=new_op.stable_key)
    assert new_item.metadata["extraction_status"] == "ok"
    old_item = ContentItem.objects.get(external_id=old_op.stable_key)
    assert "extraction_status" not in old_item.metadata


@pytest.mark.django_db
def test_new_only_rerun_with_nothing_new_extracts_zero_and_says_so_distinctly(
    monkeypatch, tmp_path
):
    """A re-run over a corpus the collector now reports nothing new in (the
    ordinary steady-state nightly, most nights) must extract zero records --
    and the transcript must say *why* it is zero via the ``--new-only
    scoped to 0 of N`` line, not merely stop at the same ``extract: 0``
    text a genuine failure could also produce. Distinguishing "nothing new"
    from "something broke" is the entire reason that line exists ahead of
    the settled count."""
    op = _opportunity("already-seen")
    data = {GRANTS: DomainData(domain=GRANTS, items=[op], new_keys=[])}
    _patch_stages(monkeypatch, data)
    calls: list[dict] = []
    monkeypatch.setattr(cmd, "run_extraction", _fake_run_extraction(calls))

    out = StringIO()
    call_command(
        "collect_opportunities",
        **_COMMON_ARGS,
        root=str(tmp_path),
        domain="grants",
        new_only=True,
        stdout=out,
    )

    assert calls[0]["only_keys"] == set()
    text = out.getvalue()
    assert "extract: --new-only scoped to 0 of 1 collected record(s)." in text
    assert "extract: 0 record(s) settled." in text
    # Still a clean, reported completion -- not a raised exception and not
    # silence: the SUCCESS line is the caller's evidence this was "nothing
    # new", not a crash that happened to produce no output.
    assert "collect_opportunities: 1 created" in text


# --------------------------------------------------------------------------- #
# 4. --no-extract skips the model entirely
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_no_extract_makes_zero_calls_to_the_model(monkeypatch, tmp_path):
    op = _opportunity("skip1")
    data = {GRANTS: DomainData(domain=GRANTS, items=[op])}
    _patch_stages(monkeypatch, data)
    calls: list[dict] = []
    monkeypatch.setattr(cmd, "run_extraction", _fake_run_extraction(calls))

    out = StringIO()
    call_command(
        "collect_opportunities",
        **_COMMON_ARGS,
        root=str(tmp_path),
        extract=False,
        stdout=out,
    )

    assert calls == []  # run_extraction was never invoked
    assert "extract:" not in out.getvalue()
    item = ContentItem.objects.get(external_id=op.stable_key)
    assert "extraction_status" not in item.metadata


# --------------------------------------------------------------------------- #
# 5. --workers defaults to 16 (EXP-2026-08-007)
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_workers_defaults_to_sixteen(monkeypatch, tmp_path):
    op = _opportunity("w1")
    data = {GRANTS: DomainData(domain=GRANTS, items=[op])}
    _patch_stages(monkeypatch, data)
    calls: list[dict] = []
    monkeypatch.setattr(cmd, "run_extraction", _fake_run_extraction(calls))

    call_command(
        "collect_opportunities", **_COMMON_ARGS, root=str(tmp_path), stdout=StringIO()
    )

    assert calls[0]["max_workers"] == 16
    assert calls[0]["max_workers"] == DEFAULT_WORKERS


@pytest.mark.django_db
def test_workers_flag_overrides_the_default(monkeypatch, tmp_path):
    op = _opportunity("w2")
    data = {GRANTS: DomainData(domain=GRANTS, items=[op])}
    _patch_stages(monkeypatch, data)
    calls: list[dict] = []
    monkeypatch.setattr(cmd, "run_extraction", _fake_run_extraction(calls))

    call_command(
        "collect_opportunities",
        **_COMMON_ARGS,
        root=str(tmp_path),
        workers=4,
        stdout=StringIO(),
    )

    assert calls[0]["max_workers"] == 4


# --------------------------------------------------------------------------- #
# 6. --limit and --sources narrow the run
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_limit_and_sources_narrow_the_run_context(monkeypatch, tmp_path):
    """``--limit`` and ``--sources`` are wired straight into the
    ``RunContext`` the real ``stage_extract`` reads (``context.limit``,
    ``context.sources``) -- that wiring is ``collect_opportunities``'s own
    responsibility. What an adapter *does* with a limit or a source filter
    is the collector's concern and has its own coverage
    (``tools/retrieval/tests/collect/test_runner.py::
    test_domain_and_source_filters_narrow_the_run``); this test does not
    re-derive that.

    The single item is load-bearing despite nothing asserting on it: a run
    that collects *nothing* is a failed run and raises (see
    ``test_collect_empty_run_guard.py``). Narrowing a run is not the same
    thing as emptying it, so the fixture has to look like a narrowed run
    that still found something.
    """
    captured: dict = {}
    data = {GRANTS: DomainData(domain=GRANTS, items=[_opportunity()])}
    _patch_stages(monkeypatch, data, captured=captured)
    monkeypatch.setattr(cmd, "run_extraction", _fake_run_extraction([]))

    call_command(
        "collect_opportunities",
        **_COMMON_ARGS,
        root=str(tmp_path),
        domain="grants",
        sources="nsf,sbir",
        limit=5,
        stdout=StringIO(),
    )

    context = captured["context"]
    assert context.limit == 5
    assert context.domains == [GRANTS]
    assert set(context.sources[GRANTS]) == {"nsf", "sbir"}


# --------------------------------------------------------------------------- #
# 7. A source that fails does not abort the run
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_failed_source_does_not_abort_the_run(monkeypatch, tmp_path):
    """Pins the command's half of the non-fatal contract ``manual_all.py``
    depends on (module docstring, stage 6: "prune"; ``manual_all.py``'s own
    stage-1 docstring: "a failed collector run warns ... and leaves the
    existing ... corpus in place"). The collector's own per-source isolation
    (``runner.py::_fetch_domain`` wraps every ``adapter.fetch()`` in its own
    ``try/except`` and records the failure into ``DomainData.errors`` rather
    than raising) means ``collect_opportunities.handle()`` sees a populated
    ``errors`` list on a perfectly ordinary run whenever one source is down.
    This test proves ``handle()`` does not treat that as fatal: the domain's
    other, successful record still gets mapped, ingested, and the command
    finishes with its usual SUCCESS line rather than raising or returning
    early.

    Scope note: this does not re-exercise ``_fetch_domain``'s own
    ``try/except`` -- that isolation is structural (every adapter call is
    individually wrapped) and lives in ``runner.py``, which this file does
    not touch. No test anywhere in the repo currently drives a real adapter
    failure through ``_fetch_domain`` end to end; that gap is being named
    here, not silently assumed away.
    """
    ok = _opportunity("ok1", source="nsf")
    data = {
        GRANTS: DomainData(
            domain=GRANTS,
            items=[ok],
            errors=[
                ("sbir", "fetch", "ConnectionError: could not reach sbir.gov mirror")
            ],
        )
    }
    _patch_stages(monkeypatch, data)
    monkeypatch.setattr(cmd, "run_extraction", _fake_run_extraction([]))

    out = StringIO()
    call_command(
        "collect_opportunities", **_COMMON_ARGS, root=str(tmp_path), stdout=out
    )

    assert ContentItem.objects.filter(
        source="grants:nsf", external_id=ok.stable_key
    ).exists()
    assert "collect_opportunities: 1 created" in out.getvalue()


# --------------------------------------------------------------------------- #
# 8. refresh_dblp_registry: runs, writes its cache, re-runs safely, no network
# --------------------------------------------------------------------------- #

_DBLP_SAMPLE_RESULTS = {
    "results": {
        "bindings": [
            {
                "stream": {"value": "https://dblp.org/streams/conf/nips"},
                "class": {"value": "https://dblp.org/rdf/schema#Conference"},
                "primary": {
                    "value": "Conference on Neural Information Processing Systems"
                },
                "title": {
                    "value": (
                        "Conference on Neural Information Processing Systems "
                        "(NeurIPS)"
                    )
                },
                "titleKind": {"value": "current"},
                "nYears": {"value": "35"},
                "firstYear": {"value": "1988"},
                "lastYear": {"value": "2025"},
            }
        ]
    }
}
_DBLP_EMPTY_RESULTS: dict = {"results": {"bindings": []}}


class _FakeSparqlResponse:
    """Stands in for ``tools.retrieval.collect.core.http.Response`` — the only
    thing ``fetch_registry`` reads off it is ``.json()``."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeDblpClient:
    """Stands in for ``PoliteClient``: never opens a socket.

    ``fetch_registry`` makes exactly two ``post_raw`` calls (the registry
    query, then the optional ``owl:differentFrom`` query) — distinguished
    here by body content, the same distinction the real SPARQL endpoint
    would draw by query text, so this fake exercises the real two-call
    shape rather than assuming it.
    """

    def __init__(self, *_args, **_kwargs) -> None:
        self.post_calls: list[str] = []

    def post_raw(self, url, body, *, headers=None, min_bytes=0):
        self.post_calls.append(url)
        text = body.decode("utf-8")
        payload = (
            _DBLP_EMPTY_RESULTS if "differentFrom" in text else _DBLP_SAMPLE_RESULTS
        )
        return _FakeSparqlResponse(payload)


def test_refresh_dblp_registry_writes_its_cache_offline(monkeypatch, tmp_path):
    fake_client = _FakeDblpClient()
    monkeypatch.setattr(dblp_cmd, "PoliteClient", lambda *a, **kw: fake_client)

    out = StringIO()
    call_command("refresh_dblp_registry", root=str(tmp_path), stdout=out)

    cache_path = tmp_path / "registry" / "dblp_venues.json"
    assert cache_path.exists()
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert payload["source"] == "dblp"
    assert payload["venues"][0]["key"] == "conf/nips"
    # Both calls went to the fake, never a real socket: the registry query
    # and the differentFrom query, and nothing else.
    assert fake_client.post_calls == [
        "https://sparql.dblp.org/sparql",
        "https://sparql.dblp.org/sparql",
    ]
    assert "dblp registry refreshed: 1 venue(s)" in out.getvalue()


def test_refresh_dblp_registry_rerun_is_no_op_safe(monkeypatch, tmp_path):
    """Running the refresh twice in a row -- exactly what a retried weekly
    cron does -- must not raise or corrupt the cache; the second run simply
    overwrites it with an equally valid payload, and still touches no real
    network either time."""
    fake_client = _FakeDblpClient()
    monkeypatch.setattr(dblp_cmd, "PoliteClient", lambda *a, **kw: fake_client)

    call_command("refresh_dblp_registry", root=str(tmp_path), stdout=StringIO())
    call_command("refresh_dblp_registry", root=str(tmp_path), stdout=StringIO())

    cache_path = tmp_path / "registry" / "dblp_venues.json"
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert payload["venues"][0]["key"] == "conf/nips"
    assert len(fake_client.post_calls) == 4  # two POSTs per run, both fake
