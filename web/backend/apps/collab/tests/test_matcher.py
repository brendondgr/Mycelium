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
            verified=True,
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
    query = matcher.query_for_project(ada, project, scope=Audience.COUNTRY)
    with pytest.raises(matcher.SearchRefused):
        matcher.search(ada, query, complete=_model())
    settings.COLLAB_MAX_SCOPE = "country"
    result = matcher.search(ada, query, complete=_model())
    assert "frank" in _names(result)  # UF: another institution, the same country


def test_a_seeker_never_looks_past_their_own_country(world, settings):
    """People are suggested only from the seeker's institution or country — a
    setting cannot widen search to anywhere, and a person abroad who is open to
    anyone is still not shown."""
    ada, _, project = world
    abroad = _person(
        "olu", "olu@ox.ac.uk", openalex="A11", field="27", method="kriging"
    )
    _open(abroad, Audience.ANYWHERE)
    settings.COLLAB_MAX_SCOPE = "anywhere"
    anywhere = matcher.query_for_project(ada, project, scope=Audience.ANYWHERE)
    with pytest.raises(matcher.SearchRefused):
        matcher.search(ada, anywhere, complete=_model())
    country = matcher.query_for_project(ada, project, scope=Audience.COUNTRY)
    assert "olu" not in _names(matcher.search(ada, country, complete=_model()))
    everyone = {c.get_username() for c in matcher.eligible_candidates(ada, "anywhere")}
    assert "olu" not in everyone and "frank" in everyone  # clamped to country


def test_a_verified_personal_address_cannot_search(world):
    ada, _, project = world
    personal = _person("pat", "pat@gmail.com", openalex="A12", field="23")
    query = matcher.query_for_project(ada, project)
    with pytest.raises(matcher.SearchRefused) as refused:
        matcher.search(personal, query, complete=_model())
    assert refused.value.code == "no_institution"
    assert matcher.eligible_candidates(personal, "institution") == []


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


def test_availability_tells_a_personal_address_why(world, settings):
    settings.COLLAB_SEARCH_ENABLED = True
    personal = _person("quin", "quin@gmail.com", openalex="A13", field="23")
    body = _client(personal).get("/api/collab/search/").json()
    assert body["available"] is False and body["code"] == "no_institution"


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


def test_manual_search_with_edited_slots_does_not_read_the_words_again(
    world, settings, monkeypatch
):
    from apps.collab import slots as slot_reader

    ada, _, _ = world
    settings.COLLAB_SEARCH_ENABLED = True
    monkeypatch.setattr(matcher, "_default_complete", _model())

    def boom(*args, **kwargs):
        raise AssertionError("the slot reader ran for slots already given")

    monkeypatch.setattr(slot_reader, "extract", boom)
    response = _client(ada).post(
        "/api/collab/search/",
        {
            "entry": "manual",
            "text": "someone for spatial interpolation",
            "slots": [{"facet": "method", "text": "kriging"}],
        },
        format="json",
    )
    assert response.status_code == 200
    assert [s["text"] for s in response.json()["slots"]] == ["kriging"]


def test_concept_matches_follow_their_own_threshold(world, settings):
    ada, people, project = world
    query = matcher.query_for_project(ada, project)
    candidates = matcher.eligible_candidates(ada, "institution")
    gaps = [s for s in query.slots if s["text"] == "kriging"]
    fields = {people["bo"].pk: {"27"}}
    settings.COLLAB_CONCEPT_MATCH_COSINE = 0.9
    assert matcher._concept_hits(query, candidates, gaps, [], fields)
    # Raised past any similarity: no concept hit, while the sentence
    # threshold is untouched.
    settings.COLLAB_CONCEPT_MATCH_COSINE = 1.01
    assert matcher._concept_hits(query, candidates, gaps, [], fields) == []
    assert settings.COLLAB_LANE_MATCH_COSINE == 0.9


def test_a_lane_gives_every_slot_a_place_before_any_slot_a_second():
    H = matcher.Hit
    hits = [
        H(1, "method_bridge", 0.99, "kriging", "method", "kriging", "demonstrated"),
        H(2, "method_bridge", 0.98, "kriging", "method", "kriging", "demonstrated"),
        H(3, "method_bridge", 0.97, "kriging", "method", "kriging", "demonstrated"),
        H(4, "method_bridge", 0.80, "lidar", "method", "lidar", "declared"),
        H(1, "method_bridge", 0.75, "survival", "method", "survival", "demonstrated"),
        H(5, "method_bridge", 0.74, "survival", "method", "survival", "declared"),
    ]
    chosen = matcher._slot_rounds(hits, 3)
    # One per slot, each slot's best — and person 1, already chosen for
    # kriging, is never offered twice (survival goes to person 5).
    assert [(h.slot, h.user_id) for h in chosen] == [
        ("kriging", 1),
        ("lidar", 4),
        ("survival", 5),
    ]
    assert [h.user_id for h in matcher._slot_rounds(hits, 5)] == [1, 4, 5, 2, 3]


def test_the_rerank_reads_the_first_answer_and_ignores_what_follows():
    shortlist = [
        matcher.Hit(
            7, "method_bridge", 0.9, "kriging", "method", "kriging", "demonstrated"
        )
    ]
    query = matcher.Query("manual", [{"facet": "method", "text": "kriging"}])

    def chatty(system, user):
        answer = '{"verdicts": [{"id": "c1", "keep": true, "reason": "Uses kriging."}]}'
        return answer + '\n{"note": 1}'

    kept, reasons, explained = matcher._rerank(
        query, "method_bridge", shortlist, chatty
    )
    assert explained and reasons == {7: "Uses kriging."} and kept == shortlist


def test_a_short_need_in_ones_own_words_is_read_not_refused(world):
    ada, _, _ = world
    asked = []

    def model(system, user):
        asked.append(user)
        return '{"slots": [{"facet": "method", "text": "kriging", "required": true}]}'

    query = matcher.query_for_text(
        ada, "Someone who can do kriging on our reef data.", complete=model
    )
    assert asked, "the call floor refused a person's short statement of need"
    assert [s["text"] for s in query.slots] == ["kriging"]
