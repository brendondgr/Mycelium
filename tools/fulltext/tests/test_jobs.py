"""Requests run through the engine, stored, recorded, audited."""

from pathlib import Path

import pytest
from apps.accounts.models import AuditEvent
from django.contrib.auth import get_user_model
from django.test import override_settings

from tools._framework import events
from tools.fulltext import jobs, store, tasks
from tools.fulltext.engine.pipeline import Engine
from tools.fulltext.models import FulltextDocument, FulltextRequest
from tools.fulltext.tests.engine.conftest import FULL_ENV, FakeResolver, fake_fetch
from tools.retrieval.read import ContentItem

pytestmark = pytest.mark.django_db
Status = FulltextRequest.Status


@pytest.fixture(autouse=True)
def data_dir(tmp_path):
    with override_settings(FULLTEXT_DATA_DIR=str(tmp_path / "store")):
        yield tmp_path / "store"


@pytest.fixture
def engine(tmp_path, monkeypatch):
    e = Engine(FULL_ENV, tmp_path / "cache")
    e.resolver = FakeResolver(e.fetcher)
    e.calls = []
    pdf = tmp_path / "cache" / "downloads" / "abc123.bin"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.4 fake wiley pdf")
    e.fetcher.fetch = fake_fetch(e.calls, pdf)
    monkeypatch.setattr(jobs, "engine", lambda: e)
    return e


@pytest.fixture
def user():
    return get_user_model().objects.create_user(
        username="reader", email="reader@fsu.edu", password="x"
    )


def test_a_retrieved_paper_is_stored_and_linked_to_the_corpus(engine, user, data_dir):
    item = ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source="openalex",
        external_id="W1",
        metadata={"doi": "10.1002/tox.222", "title": "Nanoplastics and the heart"},
    )
    seen = []

    def handler(**kw):
        seen.append(kw)

    events.subscribe("fulltext.retrieved", handler)
    try:
        [req] = jobs.run(jobs.create(["222"], requester=user))
    finally:
        events.unsubscribe("fulltext.retrieved", handler)
    assert req.status == Status.FULL_TEXT and req.finished_at is not None
    doc = req.document
    assert doc.source == "wiley" and doc.licensed and doc.doi == "10.1002/tox.222"
    assert doc.content_item == item and req.content_item == item
    assert store.original_file(doc).read_bytes().startswith(b"%PDF")
    assert store.original_file(doc).suffix == ".pdf"
    assert "## Full text" in store.read_markdown(doc)
    assert str(store.absolute(doc.markdown_path)).startswith(str(data_dir))
    # Licensed content is audited; the event names the document and the item.
    audit = AuditEvent.objects.get(action="fulltext.licensed_fetch")
    assert audit.actor == user and audit.target_id == str(doc.pk)
    assert seen == [{"document": doc, "content_item": item}]


def test_a_stored_paper_is_served_without_asking_any_provider(engine):
    jobs.run(jobs.create(["222"]))
    engine.calls.clear()
    [again] = jobs.run(jobs.create(["10.1002/tox.222"]))
    assert again.status == Status.FULL_TEXT and "from the store" in again.explanation
    assert engine.calls == []
    assert FulltextDocument.objects.count() == 1


def test_open_copies_are_not_audited_and_pmc_originals_are_xml(engine):
    [req] = jobs.run(jobs.create(["PMC333"]))
    assert req.status == Status.FULL_TEXT and req.document.source == "pmc"
    assert not req.document.licensed and req.document.original_kind == "xml"
    assert not AuditEvent.objects.filter(action="fulltext.licensed_fetch").exists()


def test_every_outcome_is_recorded_with_its_reason(engine):
    reqs = jobs.run(
        jobs.create(
            ["111", "999", "plastic", {"pmid": "111", "doi": "10.1002/tox.222"}]
        )
    )
    by = {str(r.identifier): r for r in reqs}
    els = by["111"]
    assert els.status == Status.ABSTRACT_ONLY and "Elsevier" in els.explanation
    assert (
        els.next_steps and els.route and els.attempts["elsevier"].startswith("http 403")
    )
    assert els.ids["doi"] == "10.1016/j.envpol.2020.111" and els.document is None
    assert by["999"].status == Status.NOT_FOUND
    assert by["plastic"].status == Status.INVALID
    assert (
        next(r for r in reqs if isinstance(r.identifier, dict)).status
        == Status.MISMATCH
    )
    assert all(r.finished for r in reqs)


def test_a_resolution_failure_leaves_retryable_errors(engine, monkeypatch):
    def boom(items):
        raise RuntimeError("NCBI down")

    monkeypatch.setattr(engine, "resolve", boom)
    [req] = jobs.run(jobs.create(["222"]))
    assert (
        req.status == Status.ERROR and req.retryable and "NCBI down" in req.explanation
    )
    monkeypatch.undo()
    monkeypatch.setattr(jobs, "engine", lambda: engine)
    [again] = jobs.retry([req])
    assert again.status == Status.FULL_TEXT


def test_retry_skips_what_cannot_change_unless_asked(engine):
    [els] = jobs.run(jobs.create(["111"]))
    assert jobs.retry([els]) == []  # not retryable
    assert [r.status for r in jobs.retry([els], only_retryable=False)] == [
        Status.ABSTRACT_ONLY
    ]


def test_the_celery_task_runs_unfinished_requests(engine):
    reqs = jobs.create(["222", "444"])
    assert tasks.run_requests([str(r.pk) for r in reqs]) == 2
    assert tasks.run_requests([str(r.pk) for r in reqs]) == 0  # already finished
    assert {r.status for r in FulltextRequest.objects.all()} == {
        Status.FULL_TEXT,
        Status.ABSTRACT_ONLY,
    }


def test_stored_paths_cannot_escape_the_store(data_dir):
    with pytest.raises(ValueError):
        store.absolute("../../etc/passwd")
    assert (
        store.absolute("files/ab/x.md") == (Path(data_dir) / "files/ab/x.md").resolve()
    )
