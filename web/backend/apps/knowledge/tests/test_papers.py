"""The demonstrated pipeline end to end, with a scripted model.

An import is read the day it lands; the nightly pass reads what is still
unread within its cap and re-records only the people whose papers changed; a
model outage leaves works unread and costs nothing but a night.
"""

import json

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from apps.accounts.author_works import store_author_works
from apps.accounts.intake.drafts import AuthorProfileDraft
from apps.accounts.models import AuthorWork
from apps.knowledge import papers, tasks
from apps.knowledge.models import Edge, Tier, WorkFacets

from .test_works import ABSTRACT, GOOD


def _model(calls):
    def complete(system, user):
        calls.append(user)
        return json.dumps(GOOD)

    return complete


def _down(system, user):
    raise ConnectionError("model down")


@pytest.fixture
def ada(db):
    return User.objects.create_user("ada", "ada@example.org", "pw")


def _works(user, n, *, start=0):
    return [
        AuthorWork.objects.create(
            user=user,
            source="openalex",
            source_id=f"W{start + i}",
            title=f"Mapping coral bleaching from drones, part {start + i}",
            abstract=ABSTRACT,
            year=2020 + i,
            openalex_field_id="23",
            field_checked_at="2026-01-01T00:00:00Z",
        )
        for i in range(n)
    ]


def test_a_person_is_read_and_linked_in_one_pass(ada, embedder):
    _works(ada, 2)
    calls = []
    result = papers.refresh_person(ada, complete=_model(calls))
    assert (result.read, result.unavailable, result.people) == (2, 0, 1)
    assert len(calls) == 2
    assert Edge.objects.filter(user=ada, tier=Tier.DEMONSTRATED).count() == 5
    rolled = Edge.objects.get(user=ada, surface="Kalman filter")
    assert rolled.weight == 2.0

    again = papers.refresh_person(ada, complete=_model(calls))
    assert again.read == 0 and len(calls) == 2
    assert again.edges_created == again.edges_deleted == 0


def test_a_model_outage_leaves_works_unread_for_tomorrow(ada, embedder):
    _works(ada, 2)
    result = papers.refresh_person(ada, complete=_down)
    assert (result.read, result.unavailable) == (0, 2)
    assert not WorkFacets.objects.exists()
    assert not Edge.objects.exists()
    calls = []
    assert papers.refresh_pending(complete=_model(calls)).read == 2


def test_the_nightly_pass_respects_its_cap(ada, embedder, settings):
    settings.KNOWLEDGE_WORK_FACETS_NIGHTLY_CAP = 3
    _works(ada, 5)
    calls = []
    assert papers.refresh_pending(complete=_model(calls), lookups=0).read == 3
    assert papers.refresh_pending(complete=_model(calls), lookups=0).read == 2
    assert papers.refresh_pending(complete=_model(calls), lookups=0).read == 0
    assert len(calls) == 5


def test_the_nightly_pass_rebuilds_only_people_whose_papers_changed(
    ada, embedder, monkeypatch
):
    bo = User.objects.create_user("bo", "bo@example.org", "pw")
    _works(ada, 1)
    papers.refresh_person(ada, complete=_model([]))
    _works(bo, 1, start=10)
    recorded = []
    real = papers.demonstrated.record_person
    monkeypatch.setattr(
        papers.demonstrated,
        "record_person",
        lambda user: recorded.append(user.username) or real(user),
    )
    papers.refresh_pending(complete=_model([]), lookups=0)
    assert recorded == ["bo"]


def test_the_nightly_pass_looks_up_fields_it_does_not_have(ada, embedder):
    work = AuthorWork.objects.create(
        user=ada,
        source="scholar",
        source_id="S1",
        title="Mapping coral bleaching from drones",
        abstract=ABSTRACT,
        doi="10.1/reef",
    )

    def fetch(url):
        return {"primary_topic": {"field": {"id": "https://openalex.org/fields/23"}}}

    result = papers.refresh_pending(complete=_model([]), fetch=fetch)
    assert result.looked_up == 1
    work.refresh_from_db()
    assert work.openalex_field_id == "23"
    assert WorkFacets.objects.get(author_work=work).openalex_field_id == "23"


def test_one_person_failing_does_not_stop_the_rest(ada, embedder, monkeypatch):
    bo = User.objects.create_user("bo", "bo@example.org", "pw")
    _works(ada, 1)
    _works(bo, 1, start=10)
    real = papers.demonstrated.record_person

    def flaky(user):
        if user.username == "ada":
            raise RuntimeError("boom")
        return real(user)

    monkeypatch.setattr(papers.demonstrated, "record_person", flaky)
    result = papers.refresh_pending(complete=_model([]), lookups=0)
    assert result.failures == [f"user:{ada.pk}"]
    assert Edge.objects.filter(user=bo).exists()


def test_an_import_queues_its_reading(
    ada, settings, monkeypatch, django_capture_on_commit_callbacks
):
    settings.KNOWLEDGE_FACET_ON_IMPORT = True
    queued = []
    monkeypatch.setattr(tasks.facet_user_works, "delay", queued.append)
    draft = AuthorProfileDraft(
        display_name="Ada",
        evidence=[{"title": "A paper", "source_id": "W1", "abstract": ABSTRACT}],
    )
    with django_capture_on_commit_callbacks(execute=True):
        store_author_works(ada, draft, source="openalex")
    assert queued == [str(ada.pk)]


def test_the_import_hook_is_silent_when_switched_off(
    ada, monkeypatch, django_capture_on_commit_callbacks
):
    monkeypatch.setattr(
        tasks.facet_user_works, "delay", lambda *a: pytest.fail("queued while off")
    )
    draft = AuthorProfileDraft(
        display_name="Ada", evidence=[{"title": "A paper", "source_id": "W1"}]
    )
    with django_capture_on_commit_callbacks(execute=True):
        store_author_works(ada, draft, source="openalex")


def test_the_command_reads_one_person_or_the_backlog(
    ada, embedder, capsys, monkeypatch
):
    _works(ada, 1)
    monkeypatch.setattr(papers.works, "_settings_complete", _model([]))
    call_command("facet_author_works", "--user", str(ada.pk))
    assert json.loads(capsys.readouterr().out)["read"] == 1
    call_command("facet_author_works", "--lookups", "0")
    assert json.loads(capsys.readouterr().out)["read"] == 0
