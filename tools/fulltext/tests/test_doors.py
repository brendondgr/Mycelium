"""The read and write doors, and the fulltext_get command."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings

from tools.fulltext import jobs, read, service, tasks
from tools.fulltext.engine.pipeline import Engine
from tools.fulltext.models import FulltextRequest
from tools.fulltext.tests.engine.conftest import FULL_ENV, FakeResolver, fake_fetch
from tools.retrieval.read import ContentItem

pytestmark = pytest.mark.django_db
Status = FulltextRequest.Status


@pytest.fixture(autouse=True)
def data_dir(tmp_path):
    with override_settings(FULLTEXT_DATA_DIR=str(tmp_path / "store")):
        yield


def make_engine(tmp_path, env=FULL_ENV, unpaywall=None):
    e = Engine(env, tmp_path / "cache")
    e.resolver = FakeResolver(e.fetcher)
    e.calls = []
    pdf = tmp_path / "cache" / "downloads" / "abc123.bin"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.4 fake")
    e.fetcher.fetch = fake_fetch(e.calls, pdf)
    e.fetcher.unpaywall_record = lambda doi: (unpaywall or {}).get(
        doi, {"is_oa": False, "oa_status": "closed"}
    )
    return e


@pytest.fixture
def engine(tmp_path, monkeypatch):
    e = make_engine(
        tmp_path,
        unpaywall={
            "10.1021/acs.est.444": {
                "is_oa": True,
                "best_oa_location": {"host_type": "repository"},
            }
        },
    )
    monkeypatch.setattr(jobs, "engine", lambda: e)
    return e


def test_check_says_what_is_within_reach_without_fetching(engine):
    out = service.check(["PMC333", "hep-th/9901001", "444", "222", "111", "999"])
    verdicts = [o["availability"] for o in out]
    assert verdicts == [
        "open",
        "open",
        "open",
        "subscription",
        "subscription",
        "not_found",
    ]
    assert "Unpaywall" in out[2]["explanation"]
    assert out[3]["will_try"] and "wiley" in out[3]["will_try"]
    assert engine.calls == []  # nothing fetched


def test_check_without_publisher_keys_says_unavailable(tmp_path, monkeypatch):
    e = make_engine(tmp_path, env={"CONTACT_EMAIL": "lab@fsu.edu"})
    monkeypatch.setattr(jobs, "engine", lambda: e)
    [els] = service.check(["111"])
    assert els["availability"] == "unavailable"
    assert "cannot be asked on this instance" in els["explanation"]


def test_request_then_read_through_the_doors(engine):
    item = ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source="openalex",
        external_id="W2",
        metadata={"doi": "10.1002/tox.222"},
    )
    assert read.document(item) is None and not read.has_full_text(item)
    [req] = service.request(["222"])
    assert req.status == Status.FULL_TEXT
    doc = read.document(item)
    assert (
        doc.source == "wiley" and doc.licensed and doc.content_item_id == str(item.pk)
    )
    assert doc.original_path.read_bytes().startswith(b"%PDF")
    assert "## Full text" in read.full_text(item)
    assert read.full_text({"doi": "10.1002/tox.222"}) == read.full_text(item)
    assert read.availability(item)["availability"] == "stored"
    assert service.check(["10.1002/tox.222"])[0]["availability"] == "stored"
    state = read.request_state(req.pk)
    assert state.finished and state.document_id == doc.id


def test_availability_of_an_item_without_identifiers(engine):
    item = ContentItem.objects.create(
        type=ContentItem.Type.PAPER, source="x", external_id="1", metadata={}
    )
    assert read.availability(item)["availability"] == "invalid_identifier"


def test_background_requests_go_to_a_worker(engine, monkeypatch):
    sent = []
    monkeypatch.setattr(tasks.run_requests, "delay", lambda ids: sent.append(ids))
    reqs = service.request(["222", "444"], background=True)
    assert {r.status for r in reqs} == {Status.QUEUED}
    assert sent == [[str(r.pk) for r in reqs]]


def test_retry_in_the_background_requeues_only_transient_failures(engine, monkeypatch):
    sent = []
    monkeypatch.setattr(tasks.run_requests, "delay", lambda ids: sent.append(ids))
    [els] = service.request(["111"])
    FulltextRequest.objects.filter(pk=els.pk).update(retryable=True)
    els.refresh_from_db()
    assert service.retry([els], background=True) == [els]
    els.refresh_from_db()
    assert els.status == Status.QUEUED and sent == [[str(els.pk)]]


def test_sources_door_lists_every_source(engine):
    assert {s["source"] for s in service.sources()} >= {"pmc", "arxiv", "wiley"}


def test_fulltext_get_command(engine):
    out = StringIO()
    call_command("fulltext_get", "222", "999", stdout=out)
    text = out.getvalue()
    assert "222: full_text" in text and "markdown:" in text and "original:" in text
    assert "999: not_found" in text
    out = StringIO()
    call_command("fulltext_get", "--check-only", "111", stdout=out)
    assert "111: subscription" in out.getvalue() and "would try" in out.getvalue()
