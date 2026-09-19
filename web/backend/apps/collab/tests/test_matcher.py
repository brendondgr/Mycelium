"""The matcher: lanes, the gate, the rerank, and what is never shown.

Plan CN-05's acceptance and Q4 (the fourth cross-entity query): a search from a
project that needs a method returns an opted-in person from another field whose
paper uses it, in the method-bridge lane — and every gate condition, negated
alone, removes the person it guards against.
"""

import json
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.accounts.models import AuthorWork, Lab, LabMembership
from apps.collab import consent, matcher
from apps.collab.models import Audience, CollaborationSetting, SearchLog
from apps.knowledge import demonstrated, service
from apps.knowledge.models import Relation, WorkFacets
from apps.research.models import Project, ProjectState


@pytest.fixture(autouse=True)
def _open_plans(settings):
    # Plan gating is exercised by its own test below; everything else searches
    # as someone allowed to.
    settings.BILLING_ENFORCE_ENTITLEMENTS = False
    settings.COLLAB_LANE_MATCH_COSINE = 0.9


def _person(
    username, email, *, openalex="", field="", method="", problem="", coauthors=()
):
    user = User.objects.create_user(username, email, "pw")
    user.profile.is_verified = True
    user.profile.openalex_id = openalex
    user.profile.save()
    if method or problem:
        work = AuthorWork.objects.create(
            user=user,
            source="openalex",
            source_id=f"W-{username}",
            title=f"{username}'s paper",
            year=timezone.now().year,
            openalex_field_id=field,
            coauthor_ids=list(coauthors),
        )
        facets = WorkFacets.objects.create(
            author_work=work,
            problem=problem,
            method=method,
            openalex_field_id=field,
            terms={
                "method": [method] if method else [],
                "problem": [problem] if problem else [],
            },
        )
        from apps.knowledge import works

        works.fill_vectors([facets])
        demonstrated.record_person(user)
    return user


def _open(user, audience=Audience.INSTITUTION):
    consent.update(user, open=True, audience=audience)


@pytest.fixture
def world(db, embedder):
    ada = _person(
        "ada",
        "ada@fsu.edu",
        openalex="A1",
        field="23",
        method="semantic segmentation",
        problem="coral bleaching",
        coauthors=["A4"],
    )
    lab = Lab.objects.create(name="Reef", slug="reef-matcher")
    LabMembership.objects.create(user=ada, lab=lab, is_lead=True)
    people = {
        # The right answer: another field, open, at the seeker's institution.
        "bo": _person("bo", "bo@fsu.edu", openalex="A2", field="27", method="kriging"),
        # A lab-mate: belongs in the team-fit line.
        "carol": _person(
            "carol", "carol@fsu.edu", openalex="A3", field="27", method="kriging"
        ),
        # An existing co-author.
        "dan": _person(
            "dan", "dan@fsu.edu", openalex="A4", field="27", method="kriging"
        ),
        # Closed.
        "eve": _person(
            "eve", "eve@fsu.edu", openalex="A5", field="27", method="kriging"
        ),
        # Another institution (the seeker searches their own).
        "frank": _person(
            "frank", "frank@ufl.edu", openalex="A6", field="27", method="kriging"
        ),
        # Expired.
        "gina": _person(
            "gina", "gina@fsu.edu", openalex="A7", field="27", method="kriging"
        ),
        # The same field as the seeker: not a bridge.
        "hal": _person(
            "hal", "hal@fsu.edu", openalex="A8", field="23", method="kriging"
        ),
    }
    LabMembership.objects.create(user=people["carol"], lab=lab)
    for key in ("bo", "carol", "dan", "frank", "gina", "hal"):
        _open(
            people[key], Audience.ANYWHERE if key == "frank" else Audience.INSTITUTION
        )
    CollaborationSetting.objects.filter(user=people["gina"]).update(
        expires_at=timezone.now() - timedelta(days=1)
    )
    project = Project.objects.create(name="Bleaching", scope_lab=lab)
    project.members.add(ada)
    ProjectState.objects.create(
        project=project, slow={"problem": "coral bleaching", "method": ["kriging"]}
    )
    service.project_declared(project)
    return ada, people, project


def _model(keep_all=True, extra=None):
    calls = []

    def complete(system, user):
        calls.append(user)
        ids = [
            line.split(":")[0]
            for line in user.splitlines()
            if line[:1] == "c" and ":" in line
        ]
        verdicts = [
            {"id": i, "keep": keep_all, "reason": f"{i} uses the method"} for i in ids
        ]
        if extra:
            verdicts.append(extra)
        return json.dumps({"verdicts": verdicts})

    complete.calls = calls
    return complete


def _names(result, lane="method_bridge"):
    return [row["username"] for row in result.lanes.get(lane, [])]


def test_q4_a_project_that_needs_a_method_finds_it_in_another_field(world):
    ada, people, project = world
    query = matcher.query_for_project(ada, project)
    result = matcher.search(ada, query, complete=_model())
    assert _names(result) == ["bo"]
    row = result.lanes["method_bridge"][0]
    assert row["matched"] == "kriging" and row["tier"] == "demonstrated"
    assert row["institution"] == "Florida State University"
    assert row["reason"]
    assert set(row) == {
        "username",
        "name",
        "institution",
        "lane",
        "slot",
        "facet",
        "matched",
        "tier",
        "reason",
    }


@pytest.mark.parametrize("excluded", ["carol", "dan", "eve", "frank", "gina", "hal"])
def test_each_gate_condition_removes_the_person_it_guards_against(world, excluded):
    ada, people, project = world
    result = matcher.search(
        ada, matcher.query_for_project(ada, project), complete=_model()
    )
    assert excluded not in _names(result)


def test_widening_the_scope_is_refused_at_launch(world, settings):
    ada, _, project = world
    query = matcher.query_for_project(ada, project, scope=Audience.ANYWHERE)
    with pytest.raises(matcher.SearchRefused):
        matcher.search(ada, query, complete=_model())
    settings.COLLAB_MAX_SCOPE = "anywhere"
    result = matcher.search(ada, query, complete=_model())
    assert "frank" in _names(result)


def test_conversation_never_finds_anyone(world, embedder):
    ada, people, project = world
    talker = _person("ivy", "ivy@fsu.edu", openalex="A9", field="27")
    _open(talker)
    view = service.record_conversational(
        talker, surface="kriging", relation=Relation.USES_METHOD
    )
    service.confirm(talker, view.concept_id, Relation.USES_METHOD)
    result = matcher.search(
        ada, matcher.query_for_project(ada, project), complete=_model()
    )
    assert all("ivy" not in _names(result, lane) for lane in result.lanes)


def test_the_model_may_drop_but_never_add(world):
    ada, _, project = world
    invented = {"id": "c99", "keep": True, "reason": "Someone the model made up"}
    result = matcher.search(
        ada, matcher.query_for_project(ada, project), complete=_model(extra=invented)
    )
    assert _names(result) == ["bo"]
    dropped = matcher.search(
        ada,
        matcher.query_for_project(ada, project, lanes=("method_bridge",)),
        complete=_model(keep_all=False),
    )
    assert _names(dropped) == []


def test_without_the_model_the_lanes_stand_unexplained(world):
    ada, _, project = world

    def down(system, user):
        raise ConnectionError("model down")

    result = matcher.search(ada, matcher.query_for_project(ada, project), complete=down)
    assert _names(result) == ["bo"] and result.explained is False
    assert result.lanes["method_bridge"][0]["reason"] == ""


def test_appearing_is_recorded_and_the_cap_is_respected(world, settings):
    ada, people, project = world
    matcher.search(ada, matcher.query_for_project(ada, project), complete=_model())
    from apps.collab.models import Appearance

    assert Appearance.objects.filter(candidate=people["bo"], seeker=ada).exists()
    settings.COLLAB_APPEARANCE_CAP = 1
    other = _person("zed", "zed@fsu.edu", openalex="A10", field="23")
    other_project = Project.objects.create(name="Other", scope_user=other)
    ProjectState.objects.create(project=other_project, slow={"method": ["kriging"]})
    service.project_declared(other_project)
    result = matcher.search(
        other, matcher.query_for_project(other, other_project), complete=_model()
    )
    assert "bo" not in _names(result)  # already shown to one seeker this week


def test_a_cached_answer_still_drops_someone_who_turned_it_off(world):
    ada, people, project = world
    query = matcher.query_for_project(ada, project)
    model = _model()
    assert _names(matcher.search(ada, query, complete=model)) == ["bo"]
    consent.update(people["bo"], open=False, audience=Audience.INSTITUTION)
    again = matcher.search(ada, query, complete=model)
    assert _names(again) == []
    assert len(model.calls) <= 4  # the cached answer did not call the model again


def test_the_search_log_is_private_and_holds_no_vectors(world):
    ada, _, project = world
    matcher.search(ada, matcher.query_for_project(ada, project), complete=_model())
    log = SearchLog.objects.get(seeker=ada)
    assert all(set(slot) == {"facet", "text"} for slot in log.slots)
    assert "vector" not in json.dumps(log.slots)


def test_refusals(world, settings):
    ada, _, project = world
    query = matcher.query_for_project(ada, project)
    unverified = User.objects.create_user("uv", "uv@fsu.edu", "pw")
    with pytest.raises(matcher.SearchRefused):
        matcher.search(unverified, query, complete=_model())
    settings.COLLAB_SEARCHES_PER_DAY = 0
    with pytest.raises(matcher.SearchRefused):
        matcher.search(ada, query, complete=_model())


def test_a_free_plan_cannot_search_while_plans_are_enforced(world, settings):
    ada, _, project = world
    settings.BILLING_ENFORCE_ENTITLEMENTS = True
    with pytest.raises(matcher.SearchRefused):
        matcher.search(ada, matcher.query_for_project(ada, project), complete=_model())


def test_a_project_the_seeker_cannot_see_is_refused(world):
    _, people, project = world
    with pytest.raises(matcher.SearchRefused):
        matcher.query_for_project(people["bo"], project)


def test_lanes_are_never_merged(world):
    ada, _, project = world
    result = matcher.search(
        ada, matcher.query_for_project(ada, project), complete=_model()
    )
    groups = result.groups()
    assert set(groups) == {"fills_a_gap", "shares_expertise"}
    assert all(
        row["lane"] in {"method_bridge", "problem_bridge", "resource"}
        for row in groups["fills_a_gap"]
    )


# --- the API ---------------------------------------------------------------


def _client(user):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user)
    return client


def test_the_search_api_is_off_until_switched_on(world, settings):
    ada, _, project = world
    settings.COLLAB_SEARCH_ENABLED = False
    response = _client(ada).post(
        "/api/collab/search/",
        {"entry": "project", "project_id": str(project.pk)},
        format="json",
    )
    assert response.status_code == 404


def test_the_search_api_runs_an_edited_query_and_takes_feedback(
    world, settings, monkeypatch
):
    ada, people, project = world
    settings.COLLAB_SEARCH_ENABLED = True
    monkeypatch.setattr(matcher, "_default_complete", _model())
    response = _client(ada).post(
        "/api/collab/search/",
        {
            "entry": "project",
            "project_id": str(project.pk),
            "slots": [{"facet": "method", "text": "kriging"}],
        },
        format="json",
    )
    body = response.json()
    assert response.status_code == 200
    assert [s["text"] for s in body["slots"]] == ["kriging"]
    assert "vector" not in json.dumps(body)
    assert [r["username"] for r in body["groups"]["fills_a_gap"]] == ["bo"]
    url = f"/api/collab/searches/{body['search_id']}/feedback/"
    ok = _client(ada).post(
        url, {"candidate": "bo", "lane": "method_bridge", "kind": "save"}, format="json"
    )
    assert ok.status_code == 201
    stranger = _client(ada).post(
        url,
        {"candidate": "eve", "lane": "method_bridge", "kind": "save"},
        format="json",
    )
    assert stranger.status_code == 400
    other = _client(people["bo"]).post(
        url, {"candidate": "bo", "lane": "method_bridge", "kind": "save"}, format="json"
    )
    assert other.status_code == 404


def test_a_refused_search_says_why(world, settings):
    ada, _, project = world
    settings.COLLAB_SEARCH_ENABLED = True
    response = _client(ada).post(
        "/api/collab/search/",
        {"entry": "project", "project_id": str(project.pk), "scope": "anywhere"},
        format="json",
    )
    assert response.status_code == 403 and "at most" in response.json()["detail"]


def test_availability_says_why_a_search_would_be_refused(world, settings):
    ada, _, _ = world
    settings.COLLAB_SEARCH_ENABLED = False
    assert _client(ada).get("/api/collab/search/").json()["code"] == "not_enabled"
    settings.COLLAB_SEARCH_ENABLED = True
    body = _client(ada).get("/api/collab/search/").json()
    assert body == {
        "available": True,
        "code": "",
        "reason": "",
        "max_scope": "institution",
    }
    settings.BILLING_ENFORCE_ENTITLEMENTS = True
    body = _client(ada).get("/api/collab/search/").json()
    assert body["available"] is False and body["code"] == "paid_plan"


def test_a_dry_run_returns_the_prefilled_query_and_searches_nothing(world, settings):
    ada, _, project = world
    settings.COLLAB_SEARCH_ENABLED = True
    body = (
        _client(ada)
        .post(
            "/api/collab/search/",
            {"entry": "project", "project_id": str(project.pk), "dry_run": True},
            format="json",
        )
        .json()
    )
    assert {s["text"] for s in body["slots"]} >= {"kriging"}
    assert "lanes" not in body
    assert not SearchLog.objects.exists()


def test_saved_people_drop_anyone_no_longer_reachable(world, settings, monkeypatch):
    ada, people, project = world
    settings.COLLAB_SEARCH_ENABLED = True
    monkeypatch.setattr(matcher, "_default_complete", _model())
    body = (
        _client(ada)
        .post(
            "/api/collab/search/",
            {"entry": "project", "project_id": str(project.pk)},
            format="json",
        )
        .json()
    )
    _client(ada).post(
        f"/api/collab/searches/{body['search_id']}/feedback/",
        {"candidate": "bo", "lane": "method_bridge", "kind": "save"},
        format="json",
    )
    saved = _client(ada).get("/api/collab/saved/").json()["people"]
    assert [p["username"] for p in saved] == ["bo"]
    consent.update(people["bo"], open=False, audience=Audience.INSTITUTION)
    assert _client(ada).get("/api/collab/saved/").json()["people"] == []
