"""Project recommendation payload: interest-matched fellowships + short-list digest."""

import pytest
from django.utils import timezone
from tools.retrieval.models import ContentItem, RelevanceScore

from apps.accounts.models import Lab
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
            "verdict": "read" if match >= 75 else "skim",
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
    assert payload["fellowships"][0]["verdict"] == "read"


@pytest.mark.django_db
def test_digest_caps_each_area(project):
    for i in range(15):
        _score(project, _item(ContentItem.Type.PAPER, f"p{i}"), rank=i + 1)
    for i in range(8):
        grant = _item(ContentItem.Type.GRANT, f"g{i}", deadline_date=FUTURE)
        _score(project, grant, rank=i + 1)
    for i in range(8):
        fellowship = _item(ContentItem.Type.FELLOWSHIP, f"f{i}", deadline_date=FUTURE)
        _score(project, fellowship, rank=i + 1)

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
def test_a_conference_that_is_over_is_hidden_from_every_read_not_just_the_digest(
    project,
):
    """The headline rule: a passed conference is shown to nobody.

    This used to be a digest-only filter that additionally *kept* undated rows
    ("we don't hide what we can't date"). Both halves were wrong for a
    conference: the full feed showed passed venues until the nightly prune
    caught up, and an undated conference — no deadline, no event date — is not
    something a reader can act on at all, and could never be pruned either. See
    :mod:`tools.retrieval.liveness`.
    """
    live = _item(ContentItem.Type.CONFERENCE, "future", prune_after=FUTURE)
    over = _item(ContentItem.Type.CONFERENCE, "past", prune_after=PAST)
    undated = _item(ContentItem.Type.CONFERENCE, "undated")
    for item in (live, over, undated):
        _score(project, item)

    for digest in (True, False):
        payload = _recommendations_payload(
            {"target_project": project}, user=None, digest=digest
        )
        shown = {c["content_id"] for c in payload["conferences"]}
        assert shown == {str(live.id)}
        # The count is the honest total of what is shown, not of what is stored.
        assert payload["counts"]["conferences"] == 1


@pytest.mark.django_db
def test_a_rolling_grant_with_no_date_is_still_shown(project):
    """A dateless *grant* means "rolling, never expires" — the opposite of a
    dateless conference. Hiding it would delete every continuously-open funding
    call from the product."""
    rolling = _item(ContentItem.Type.GRANT, "rolling")
    _score(project, rolling)

    payload = _recommendations_payload({"target_project": project}, user=None)
    assert [g["content_id"] for g in payload["grants"]] == [str(rolling.id)]
