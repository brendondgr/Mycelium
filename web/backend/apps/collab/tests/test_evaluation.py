"""Plan CN-08: the counts, the harm checks, and readiness to widen.

Every harm check is proven two ways: zero on a real search, and non-zero when
exactly the harm it names is planted.
"""

from __future__ import annotations

import json

import pytest
from django.utils import timezone
from tools.retrieval.models import Notification

from apps.collab import evaluation, matcher
from apps.collab.models import MatchFeedback, SearchLog
from apps.collab.tests.test_matcher import _model, world  # noqa: F401
from apps.knowledge.models import Concept, Edge, Facet, Relation, Scope, Tier


@pytest.fixture(autouse=True)
def _search_on(settings):
    settings.COLLAB_SEARCH_ENABLED = True
    settings.BILLING_ENFORCE_ENTITLEMENTS = False
    settings.COLLAB_LANE_MATCH_COSINE = 0.9


def _real_search(ada, project):
    query = matcher.query_for_project(ada, project)
    return matcher.search(ada, query, complete=_model())


def _planted(seeker, row, scope="institution"):
    return SearchLog.objects.create(
        seeker=seeker,
        entry="manual",
        scope=scope,
        query_hash="planted",
        results=1,
        cached={"lanes": {"method_bridge": [row]}},
    )


def _row(username, matched="kriging", tier="demonstrated"):
    return {
        "username": username,
        "lane": "method_bridge",
        "matched": matched,
        "tier": tier,
    }


def test_a_real_search_passes_every_harm_check(world):  # noqa: F811
    ada, _, project = world
    result = _real_search(ada, project)
    assert any(result.lanes.values())
    harm = evaluation.harm_checks()
    assert harm["searches_checked"] == 1
    assert {k: v for k, v in harm.items() if k != "searches_checked" and v} == {}


@pytest.mark.parametrize(
    ("plant", "check"),
    [
        (
            lambda ada, p: _planted(ada, _row("bo", matched="a private topic")),
            "untraceable_evidence",
        ),
        (
            lambda ada, p: _planted(ada, _row("bo", tier="conversational")),
            "untraceable_evidence",
        ),
        (lambda ada, p: _planted(ada, _row("frank")), "outside_scope"),
        (lambda ada, p: _planted(ada, _row("gina")), "shown_while_off"),
        (lambda ada, p: _planted(ada, _row("eve")), "not_from_shortlist"),
        (lambda ada, p: _planted(ada, _row("ada")), "not_from_shortlist"),
    ],
)
def test_each_harm_check_fires_on_its_harm(world, plant, check):  # noqa: F811
    ada, people, _ = world
    plant(ada, people)
    harm = evaluation.harm_checks()
    assert harm[check] >= 1
    others = {
        k: v for k, v in harm.items() if k not in (check, "searches_checked") and v
    }
    assert others == {}


def test_telling_a_candidate_is_caught(world):  # noqa: F811
    _, people, _ = world
    Notification.objects.create(
        user=people["bo"],
        kind=Notification.Kind.COLLAB_RENEWAL,
        title="Someone searched for you this week",
        dedupe_key="collab-renewal-bo-x",
    )
    assert evaluation.harm_checks()["candidate_told"] == 1


def test_a_global_concept_held_only_in_conversation_is_caught(world):  # noqa: F811
    _, people, _ = world
    concept = Concept.objects.create(
        label="a private worry", facet=Facet.PROBLEM, scope=Scope.GLOBAL
    )
    Edge.objects.create(
        user=people["bo"],
        concept=concept,
        relation=Relation.INTERESTED_IN,
        tier=Tier.CONVERSATIONAL,
    )
    assert evaluation.harm_checks()["private_concept_global"] == 1


def test_the_daily_counts_name_nobody(world):  # noqa: F811
    ada, people, project = world
    result = _real_search(ada, project)
    row = next(r for rows in result.lanes.values() for r in rows)
    MatchFeedback.objects.create(
        seeker=ada,
        candidate=people[row["username"]],
        lane=row["lane"],
        kind="save",
        search_id=result.search_id,
    )
    counts = evaluation.daily_counts(timezone.localdate())
    assert counts["searches"] == 1 and counts["saved"] == 1
    assert counts["not_relevant_rate"] == 0.0
    text = json.dumps(counts)
    for name in ["ada", *people]:
        assert f'"{name}"' not in text


def test_readiness_needs_ratings_a_low_not_relevant_rate_and_no_harm(
    world,  # noqa: F811
    settings,
):
    ada, people, project = world
    settings.COLLAB_WIDEN_MIN_RATINGS = 10
    result = _real_search(ada, project)
    first = evaluation.readiness()
    assert not first["ready"] and "rated results" in first["reasons"][0]

    def rate(kind, n):
        for _ in range(n):
            MatchFeedback.objects.create(
                seeker=ada,
                candidate=people["bo"],
                lane="method_bridge",
                kind=kind,
                search_id=result.search_id,
            )

    rate("save", 10)
    readiness = evaluation.readiness()
    assert readiness["ready"] and readiness["next_scope"] == "country"
    rate("not_relevant", 15)
    readiness = evaluation.readiness()
    assert not readiness["ready"]
    assert any("not-relevant" in r for r in readiness["reasons"])


def test_the_analytics_report_carries_the_counts(world):  # noqa: F811
    from apps.content.run_analytics import collect_run_analytics

    ada, _, project = world
    _real_search(ada, project)
    snapshot = collect_run_analytics().as_dict()
    assert snapshot["collaboration"]["searches"] == 1
    assert snapshot["collaboration"]["harm"]["untraceable_evidence"] == 0
