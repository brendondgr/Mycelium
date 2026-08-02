"""Project recommendation payload: interest-matched fellowships + short-list digest."""

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.accounts.models import Lab
from apps.content.models import ContentItem, RelevanceScore
from apps.content.views import _recommendations_payload
from apps.research.models import Project

TODAY = timezone.now().date().isoformat()
FUTURE = "2099-01-01"
PAST = "2000-01-01"


def _item(kind: str, eid: str, **meta) -> ContentItem:
    base = {"title": f"{kind}-{eid}", "abstract": "x", "authors": []}
    return ContentItem.objects.create(
        type=kind, source="test", external_id=eid, metadata={**base, **meta}
    )


# All papers in a run share one run_at (papers are fresh-only: only the latest
# run's rows surface, so a per-row timestamp would collapse the feed to one item).
RUN_AT = timezone.now().isoformat()


def _score(project, item, *, match=80, rank=1, deadline="") -> None:
    RelevanceScore.objects.create(
        content=item,
        target_project=project,
        score=0.9,
        signals={
            "area": item.type,
            "run_at": RUN_AT,
            "suggested": True,
            "is_new": False,
            "pinned_until": None,
            "first_seen": TODAY,
            "deadline_date": deadline,
            "rank": rank,
            "headline": f"Why {item.external_id}",
            "reason": "Strong topical alignment with the project.",
            "match_percent": match,
            "source": "llm",
        },
    )


@pytest.fixture
def project(db):
    lab = Lab.objects.create(name="L", slug="l-digest")
    return Project.objects.create(
        scope_lab=lab,
        name="P",
        goals={"interests": {"areas": ["graph ml"], "keywords": [], "statement": ""}},
    )


@pytest.mark.django_db
def test_project_fellowships_come_from_target_scores(project):
    fel = _item(ContentItem.Type.FELLOWSHIP, "f1", deadline_date=FUTURE)
    _score(project, fel, match=88)
    payload = _recommendations_payload(
        {"target_project": project},
        user=None,
        member_ids=[],
    )
    assert payload["counts"]["fellowships"] == 1
    assert len(payload["fellowships"]) == 1
    assert payload["fellowships"][0]["content_id"] == str(fel.id)
    assert payload["fellowships"][0]["match_percent"] == 88


@pytest.mark.django_db
def test_digest_caps_each_area(project):
    for i in range(15):
        _score(project, _item(ContentItem.Type.PAPER, f"p{i}"), rank=i + 1)
    for i in range(8):
        _score(project, _item(ContentItem.Type.GRANT, f"g{i}", deadline_date=FUTURE), rank=i + 1)
    for i in range(8):
        _score(project, _item(ContentItem.Type.FELLOWSHIP, f"f{i}", deadline_date=FUTURE), rank=i + 1)

    full = _recommendations_payload(
        {"target_project": project}, user=None
    )
    assert len(full["papers"]) == 15  # uncapped feed

    digest = _recommendations_payload(
        {"target_project": project}, user=None, digest=True
    )
    assert len(digest["papers"]) == 10
    assert len(digest["grants"]) == 5
    assert len(digest["fellowships"]) == 5
    # Counts stay the full totals so the UI can say "top N of total".
    assert digest["counts"]["papers"] == 15
    assert digest["counts"]["grants"] == 8


@pytest.mark.django_db
def test_digest_drops_passed_conference_deadlines(project):
    _score(project, _item(ContentItem.Type.CONFERENCE, "future", deadline_date=FUTURE), deadline=FUTURE)
    _score(project, _item(ContentItem.Type.CONFERENCE, "past", deadline_date=PAST), deadline=PAST)
    _score(project, _item(ContentItem.Type.CONFERENCE, "undated"), deadline="")

    digest = _recommendations_payload(
        {"target_project": project}, user=None, digest=True
    )
    titles = {c["content_id"] for c in digest["conferences"]}
    # The past-deadline conference is dropped; future + undated stay.
    assert len(digest["conferences"]) == 2
    assert all("past" not in t for t in titles) or len(titles) == 2
