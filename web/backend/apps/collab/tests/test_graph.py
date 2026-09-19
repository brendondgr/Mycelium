"""Plan CN-07: the co-authorship graph, introduction paths, "outside my
network", and team formation.

The world: Sam searches. Ivy is Sam's co-author and open to collaboration; Jo
published with Ivy and uses kriging. Lee is Sam's co-author and *not* open;
Max published with Lee. Kim uses kriging too and knows nobody. Nia does
remote sensing.
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.accounts.models import AuthorWork, Lab, LabMembership
from apps.collab import matcher
from apps.collab.models import Audience, SearchLog
from apps.collab.tests.test_matcher import _client, _open, _person
from apps.knowledge import coauthorship
from apps.knowledge.models import Coauthorship
from apps.knowledge.read import coauthor_distances, introduction_paths, network_of


@pytest.fixture(autouse=True)
def _open_plans(settings):
    settings.BILLING_ENFORCE_ENTITLEMENTS = False
    settings.COLLAB_LANE_MATCH_COSINE = 0.9
    settings.COLLAB_SEARCH_ENABLED = True


def _names(users):
    return {u.get_username() for u in users}


@pytest.fixture
def graph(db, embedder):
    people = {
        "sam": _person(
            "sam",
            "sam@fsu.edu",
            openalex="A10",
            field="23",
            method="segmentation",
            coauthors=["A11", "A14"],
        ),
        "ivy": _person(
            "ivy",
            "ivy@fsu.edu",
            openalex="A11",
            field="27",
            method="field survey",
            coauthors=["A12"],
        ),
        "jo": _person("jo", "jo@fsu.edu", openalex="A12", field="27", method="kriging"),
        "kim": _person(
            "kim", "kim@fsu.edu", openalex="A13", field="25", method="kriging"
        ),
        "lee": _person(
            "lee",
            "lee@fsu.edu",
            openalex="A14",
            field="27",
            method="field survey",
            coauthors=["A15"],
        ),
        "max": _person(
            "max",
            "max@fsu.edu",
            openalex="A15",
            field="27",
            method="bayesian calibration",
        ),
        "nia": _person(
            "nia", "nia@fsu.edu", openalex="A16", field="26", method="remote sensing"
        ),
    }
    lab = Lab.objects.create(name="Sam's lab", slug="sam-lab")
    LabMembership.objects.create(user=people["sam"], lab=lab, is_lead=True)
    for key in ("ivy", "jo", "kim", "max", "nia"):
        _open(people[key], Audience.INSTITUTION)
    coauthorship.rebuild()
    return people


def _ids(people, *keys):
    return [people[k].pk for k in keys]


# --- the table ---------------------------------------------------------------


def test_rebuild_links_named_coauthors_and_shared_works_and_nothing_else(graph):
    pairs = {(r.a_id, r.b_id) for r in Coauthorship.objects.all()}
    expected = {
        tuple(sorted(_ids(graph, x, y)))
        for x, y in (("sam", "ivy"), ("sam", "lee"), ("ivy", "jo"), ("lee", "max"))
    }
    assert pairs == expected

    # The same work held by two people links them with no co-author ids.
    for key in ("kim", "nia"):
        AuthorWork.objects.create(
            user=graph[key], source="openalex", source_id="W-shared", year=2024
        )
    result = coauthorship.rebuild()
    assert result.created == 1 and result.removed == 0
    assert Coauthorship.objects.filter(
        a_id=min(_ids(graph, "kim", "nia")), b_id=max(_ids(graph, "kim", "nia"))
    ).exists()

    AuthorWork.objects.filter(source_id="W-shared").delete()
    assert coauthorship.rebuild().removed == 1
    assert coauthorship.rebuild().as_dict() == {
        "pairs": 4,
        "created": 0,
        "updated": 0,
        "removed": 0,
    }


def test_the_walks_follow_the_graph(graph):
    sam = graph["sam"].pk
    assert network_of(sam, hops=1) == set(_ids(graph, "ivy", "lee"))
    assert network_of(sam, hops=2) == set(_ids(graph, "ivy", "lee", "jo", "max"))
    distances = coauthor_distances(sam)
    assert distances[graph["jo"].pk] == 2 and graph["kim"].pk not in distances

    everyone = _ids(graph, "ivy", "lee", "jo", "max", "kim", "nia")
    paths = introduction_paths(sam, _ids(graph, "jo", "max"), everyone)
    assert paths[graph["jo"].pk] == [sam, graph["ivy"].pk, graph["jo"].pk]
    # A path may only pass through people the caller allows.
    only_ivy = introduction_paths(sam, _ids(graph, "jo", "max"), _ids(graph, "ivy"))
    assert graph["max"].pk not in only_ivy and graph["jo"].pk in only_ivy


# --- outside my network ------------------------------------------------------


def test_outside_my_network_leaves_out_coauthors_of_coauthors(graph):
    sam = graph["sam"]
    inside = _names(matcher.eligible_candidates(sam, "institution"))
    outside = _names(
        matcher.eligible_candidates(sam, "institution", outside_network=True)
    )
    assert {"jo", "max", "kim", "nia"} <= inside
    assert "ivy" not in inside  # a co-author is never a candidate
    assert outside == {"kim", "nia"}


# --- introductions -----------------------------------------------------------


def _search_showing(seeker, *usernames):
    return SearchLog.objects.create(
        seeker=seeker,
        entry="manual",
        scope="institution",
        query_hash="x",
        cached={
            "lanes": {"method_bridge": [{"username": u} for u in usernames]},
        },
    )


def test_an_introduction_names_only_people_open_to_the_seeker(graph):
    sam = graph["sam"]
    log = _search_showing(sam, "jo", "max")
    via = matcher.introduce(sam, log.pk, "jo")
    assert via["hops"] == 2
    assert [p["username"] for p in via["path"]] == ["ivy"]
    assert set(via["path"][0]) == {"username", "name", "institution"}
    # Max is reachable only through Lee, who has not opted in: no path, and
    # Lee is never named.
    assert matcher.introduce(sam, log.pk, "max") == {"path": None, "hops": None}


def test_an_introduction_is_only_for_someone_the_search_showed(graph):
    sam = graph["sam"]
    log = _search_showing(sam, "jo")
    with pytest.raises(matcher.SearchRefused):
        matcher.introduce(sam, log.pk, "kim")
    other = _search_showing(graph["kim"], "jo")
    with pytest.raises(matcher.SearchRefused):
        matcher.introduce(sam, other.pk, "jo")  # someone else's search
    # Ivy turns the setting off: the path through her is gone at once.
    from apps.collab import consent

    consent.update(graph["ivy"], open=False, audience=Audience.INSTITUTION)
    assert matcher.introduce(sam, log.pk, "jo")["path"] is None


# --- team formation ----------------------------------------------------------


def _need(*methods):
    return matcher.Query(
        "manual",
        matcher._with_vectors([{"facet": "method", "text": m} for m in methods]),
        need_fields=frozenset({"23"}),
    )


def test_a_team_covers_every_gap_it_can_and_prefers_the_closer_person(graph):
    sam = graph["sam"]
    result = matcher.assemble_team(
        sam, _need("kriging", "bayesian calibration", "remote sensing", "lidar")
    )
    members = {m["username"]: m for m in result.team}
    # Jo and Kim both do kriging; Jo is two co-authorships away, Kim unknown.
    assert set(members) == {"jo", "max", "nia"}
    assert result.uncovered == ["lidar"]
    assert members["jo"]["distance"] == 2 and members["nia"]["distance"] is None
    assert [c["slot"] for c in members["max"]["covers"]] == ["bayesian calibration"]
    eligible = _names(matcher.eligible_candidates(sam, "institution"))
    assert set(members) <= eligible
    log = SearchLog.objects.get(pk=result.search_id)
    assert log.lanes == ["team"] and log.results == 3


def test_a_team_never_includes_someone_the_gate_removes(graph):
    sam = graph["sam"]
    from apps.collab.models import CollaborationSetting

    CollaborationSetting.objects.filter(user=graph["jo"]).update(
        expires_at=timezone.now()
    )
    result = matcher.assemble_team(
        sam, _need("kriging", "bayesian calibration", "remote sensing")
    )
    assert "jo" not in {m["username"] for m in result.team}
    assert "kim" in {m["username"] for m in result.team}


def test_a_team_needs_three_gaps(graph):
    with pytest.raises(matcher.SearchRefused) as refused:
        matcher.assemble_team(graph["sam"], _need("kriging", "remote sensing"))
    assert refused.value.code == "too_few_gaps"


def test_a_search_is_never_answered_from_a_team_log(graph, monkeypatch):
    sam = graph["sam"]
    need = _need("kriging", "bayesian calibration", "remote sensing")
    matcher.assemble_team(sam, need)
    result = matcher.search(sam, need, complete=lambda s, u: None)
    assert result.lanes.get("method_bridge")


# --- the API -----------------------------------------------------------------


def test_the_team_and_introduction_api(graph):
    sam = graph["sam"]
    client = _client(sam)
    slots = [
        {"facet": "method", "text": t}
        for t in ("kriging", "bayesian calibration", "remote sensing")
    ]
    body = client.post(
        "/api/collab/team/", {"entry": "manual", "slots": slots}, format="json"
    ).json()
    assert set(body) == {"slots", "team", "uncovered", "search_id"}
    assert {m["username"] for m in body["team"]} == {"jo", "max", "nia"}
    assert set(body["team"][0]) == {
        "username",
        "name",
        "institution",
        "covers",
        "distance",
    }
    via = client.get(
        f"/api/collab/searches/{body['search_id']}/introduction/jo/"
    ).json()
    assert [p["username"] for p in via["path"]] == ["ivy"]
    refused = client.post(
        "/api/collab/team/", {"entry": "manual", "slots": slots[:2]}, format="json"
    )
    assert refused.status_code == 403 and refused.json()["code"] == "too_few_gaps"
    missing = client.get(f"/api/collab/searches/{body['search_id']}/introduction/kim/")
    assert missing.status_code == 404
