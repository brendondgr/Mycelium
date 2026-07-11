"""The daily briefing: cross-category synthesis, gating, fallback, and the API."""

import json

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import WatchPreference
from apps.content.briefing import CATEGORY_TYPES, generate_briefing_for_user
from apps.content.models import ContentItem, DailyBriefing, RelevanceScore

RUN = "2026-07-11T06:00:00"


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _content(ctype: str, title: str, **metadata) -> ContentItem:
    metadata.setdefault("title", title)
    return ContentItem.objects.create(
        type=ctype,
        source="test",
        external_id=title,
        source_url="https://example.org/x",
        metadata=metadata,
    )


def _score(
    user,
    content,
    *,
    rank=1,
    run_at=RUN,
    suggested=True,
    match=80,
    **extra_signals,
) -> RelevanceScore:
    signals = {
        "suggested": suggested,
        "run_at": run_at,
        "rank": rank,
        "headline": f"Headline {content.metadata['title']}",
        "match_percent": match,
        **extra_signals,
    }
    return RelevanceScore.objects.create(
        content=content, target_user=user, score=0.8, signals=signals
    )


def _watch(user, categories) -> None:
    WatchPreference.objects.create(user=user, categories=categories)


def _llm(text: str):
    """A stub completion that returns the model's JSON with ``text`` as the body."""
    return lambda prompt: json.dumps({"briefing": text})


# --------------------------------------------------------------------------- #
# Synthesis
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_llm_briefing_is_grounded_and_counts_are_correct() -> None:
    user = User.objects.create_user("bre", password="x")
    _watch(user, ["papers", "grants"])
    _score(user, _content(ContentItem.Type.PAPER, "Paper A"), rank=1, match=91)
    _score(user, _content(ContentItem.Type.PAPER, "Paper B"), rank=2, match=70)
    _score(
        user,
        _content(ContentItem.Type.GRANT, "Grant X"),
        rank=1,
        match=88,
        deadline_date="2026-08-01",
    )

    captured = {}

    def fake_complete(prompt: str) -> str:
        captured["prompt"] = prompt
        return json.dumps({"briefing": "Two papers and a grant landed today."})

    briefing = generate_briefing_for_user(user, complete=fake_complete)

    assert briefing.origin == DailyBriefing.Origin.LLM
    assert briefing.body == "Two papers and a grant landed today."
    assert briefing.counts == {"papers": 2, "grants": 1}
    assert briefing.categories == ["papers", "grants"]
    # Showcase is grounding the prose talks about.
    assert [i["title"] for i in briefing.showcase["papers"]] == ["Paper A", "Paper B"]
    assert briefing.showcase["grants"][0]["deadline_date"] == "2026-08-01"
    # The prompt describes the real items (grounding), not free invention.
    assert "Paper A" in captured["prompt"]
    assert "Grant X" in captured["prompt"]


@pytest.mark.django_db
def test_category_gating_excludes_unwatched_categories() -> None:
    user = User.objects.create_user("gate", password="x")
    _watch(user, ["papers"])  # grants NOT watched
    _score(user, _content(ContentItem.Type.PAPER, "Kept"), rank=1)
    _score(user, _content(ContentItem.Type.GRANT, "Hidden"), rank=1)

    briefing = generate_briefing_for_user(user, complete=_llm("ok"))

    assert set(briefing.counts) == {"papers"}
    assert "grants" not in briefing.showcase


@pytest.mark.django_db
def test_no_watch_row_defaults_to_all_categories() -> None:
    user = User.objects.create_user("nowatch", password="x")
    _score(user, _content(ContentItem.Type.PAPER, "P"), rank=1)

    briefing = generate_briefing_for_user(user, complete=lambda p: None)

    assert set(briefing.categories) == set(CATEGORY_TYPES)
    assert briefing.counts["papers"] == 1
    assert briefing.counts["grants"] == 0


@pytest.mark.django_db
def test_only_latest_run_and_suggested_items_count() -> None:
    user = User.objects.create_user("latest", password="x")
    _watch(user, ["papers"])
    _score(
        user,
        _content(ContentItem.Type.PAPER, "Old"),
        rank=1,
        run_at="2026-07-01T00:00:00",
    )
    _score(user, _content(ContentItem.Type.PAPER, "New"), rank=1, run_at=RUN)
    _score(
        user,
        _content(ContentItem.Type.PAPER, "Unsuggested"),
        rank=2,
        run_at=RUN,
        suggested=False,
    )

    briefing = generate_briefing_for_user(user, complete=_llm("x"))

    assert briefing.counts["papers"] == 1  # only the latest-run suggested paper
    assert [i["title"] for i in briefing.showcase["papers"]] == ["New"]


@pytest.mark.django_db
def test_fallback_when_llm_returns_nothing() -> None:
    user = User.objects.create_user("fb", password="x")
    _watch(user, ["papers"])
    _score(user, _content(ContentItem.Type.PAPER, "Solo"), rank=1, match=84)

    briefing = generate_briefing_for_user(user, complete=lambda p: None)

    assert briefing.origin == DailyBriefing.Origin.FALLBACK
    assert "1 paper" in briefing.body
    assert "Solo" in briefing.body


@pytest.mark.django_db
def test_fallback_when_llm_raises() -> None:
    user = User.objects.create_user("boom", password="x")
    _watch(user, ["papers"])
    _score(user, _content(ContentItem.Type.PAPER, "Solo"), rank=1)

    def raises(prompt: str) -> str:
        raise RuntimeError("endpoint down")

    briefing = generate_briefing_for_user(user, complete=raises)
    assert briefing.origin == DailyBriefing.Origin.FALLBACK
    assert briefing.body


@pytest.mark.django_db
def test_empty_day_writes_honest_fallback() -> None:
    user = User.objects.create_user("empty", password="x")
    _watch(user, ["papers", "grants"])

    briefing = generate_briefing_for_user(user, complete=lambda p: "should not be used")

    assert briefing.origin == DailyBriefing.Origin.FALLBACK
    assert briefing.counts == {"papers": 0, "grants": 0}
    assert "No new research" in briefing.body


@pytest.mark.django_db
def test_regeneration_replaces_in_place() -> None:
    user = User.objects.create_user("again", password="x")
    _watch(user, ["papers"])
    _score(user, _content(ContentItem.Type.PAPER, "One"), rank=1)

    generate_briefing_for_user(user, complete=_llm("first"))
    generate_briefing_for_user(user, complete=_llm("second"))

    assert DailyBriefing.objects.filter(user=user).count() == 1
    assert DailyBriefing.objects.get(user=user).body == "second"


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_api_requires_authentication(client: APIClient) -> None:
    assert client.get("/api/daily-briefing/").status_code in (401, 403)


@pytest.mark.django_db
def test_api_empty_envelope_when_no_briefing(client: APIClient) -> None:
    user = User.objects.create_user("fresh", password="x")
    client.force_authenticate(user)

    resp = client.get("/api/daily-briefing/")

    assert resp.status_code == 200
    assert resp.data == {
        "generated_at": None,
        "categories": [],
        "counts": {},
        "showcase": {},
        "briefing": None,
    }


@pytest.mark.django_db
def test_api_returns_own_briefing_shape(client: APIClient) -> None:
    user = User.objects.create_user("owner", password="x")
    _watch(user, ["papers"])
    _score(user, _content(ContentItem.Type.PAPER, "Mine"), rank=1, match=90)
    generate_briefing_for_user(user, complete=_llm("hello"))

    client.force_authenticate(user)
    resp = client.get("/api/daily-briefing/")

    assert resp.status_code == 200
    assert resp.data["generated_at"] is not None
    assert resp.data["categories"] == ["papers"]
    assert resp.data["counts"] == {"papers": 1}
    assert resp.data["briefing"] == {"body": "hello", "origin": "llm"}
    assert resp.data["showcase"]["papers"][0]["title"] == "Mine"


@pytest.mark.django_db
def test_api_returns_only_the_callers_briefing(client: APIClient) -> None:
    me = User.objects.create_user("me", password="x")
    them = User.objects.create_user("them", password="x")
    _watch(them, ["papers"])
    _score(them, _content(ContentItem.Type.PAPER, "Theirs"), rank=1)
    generate_briefing_for_user(them, complete=_llm("theirs"))

    client.force_authenticate(me)
    resp = client.get("/api/daily-briefing/")

    assert resp.data["briefing"] is None  # me has no briefing; can't see theirs
