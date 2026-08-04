"""The daily report: sectioned markdown synthesis, the freshness gate, fallback,
and the API."""

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import WatchPreference
from apps.content.briefing import CATEGORY_TYPES, generate_briefing_for_user
from apps.content.models import ContentItem, DailyBriefing, RelevanceScore

RUN = "2026-07-11T06:00:00"

# The daily report counts an item as "new" only when it first surfaced on the run
# date, so a genuinely-new row carries today's ``first_seen`` and an accumulated one
# carries an older date. ``today`` is the actual run date (no time is frozen).
TODAY = timezone.now().date().isoformat()
OLD_SEEN = "2026-07-01T00:00:00"  # first seen well before any test run


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
        "reason": f"Why {content.metadata['title']} fits you.",
        "match_percent": match,
        **extra_signals,
    }
    return RelevanceScore.objects.create(
        content=content, target_user=user, score=0.8, signals=signals
    )


def _watch(user, categories) -> None:
    WatchPreference.objects.create(user=user, categories=categories)


def _llm(text: str):
    """A stub completion (2-arg agent seam) that returns ``text`` for every agent."""
    return lambda system, user: text


def _is_summary(system: str) -> bool:
    """The summary agent's system prompt, distinguished from the area specialists."""
    return "opening paragraph" in system


# --------------------------------------------------------------------------- #
# Synthesis
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_llm_report_is_grounded_sectioned_and_counts_are_correct() -> None:
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

    calls: list[tuple[str, str]] = []

    def fake_complete(system: str, user_prompt: str) -> str:
        calls.append((system, user_prompt))
        if _is_summary(system):
            return "Two papers and a grant landed today."
        return "**A great match** — this fits your work."

    briefing = generate_briefing_for_user(user, complete=fake_complete)

    assert briefing.origin == DailyBriefing.Origin.LLM
    # Markdown body: the summary paragraph leads, then a section per area.
    assert briefing.body.startswith("Two papers and a grant landed today.")
    assert "## Papers" in briefing.body
    assert "## Grants" in briefing.body
    assert briefing.counts == {"papers": 2, "grants": 1}
    assert briefing.categories == ["papers", "grants"]
    # Showcase (UI grounding) still tracks the top items per area.
    assert [i["title"] for i in briefing.showcase["papers"]] == ["Paper A", "Paper B"]
    assert briefing.showcase["grants"][0]["deadline_date"] == "2026-08-01"
    # Grounding: the specialists are shown the real items (by title), never invent.
    assert any("Paper A" in u for _s, u in calls)
    assert any("Grant X" in u for _s, u in calls)
    # The editor is shown the day's counts to summarize over.
    summary_prompts = [u for s, u in calls if _is_summary(s)]
    assert summary_prompts and "Papers: 0 new, 2 matched in total" in summary_prompts[0]


@pytest.mark.django_db
def test_category_gating_excludes_unwatched_categories() -> None:
    user = User.objects.create_user("gate", password="x")
    _watch(user, ["papers"])  # grants NOT watched
    _score(user, _content(ContentItem.Type.PAPER, "Kept"), rank=1)
    _score(user, _content(ContentItem.Type.GRANT, "Hidden"), rank=1)

    briefing = generate_briefing_for_user(user, complete=_llm("body"))

    assert set(briefing.counts) == {"papers"}
    assert "grants" not in briefing.showcase
    assert "## Papers" in briefing.body
    assert "## Grants" not in briefing.body


@pytest.mark.django_db
def test_no_watch_row_defaults_to_all_categories() -> None:
    user = User.objects.create_user("nowatch", password="x")
    _score(user, _content(ContentItem.Type.PAPER, "P"), rank=1)

    briefing = generate_briefing_for_user(user, complete=lambda s, u: None)

    assert set(briefing.categories) == set(CATEGORY_TYPES)
    assert briefing.counts["papers"] == 1
    assert briefing.counts["grants"] == 0
    # Model down => deterministic markdown section for the one area with items.
    assert briefing.origin == DailyBriefing.Origin.FALLBACK
    assert "## Papers" in briefing.body


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


# --------------------------------------------------------------------------- #
# The freshness gate (the "87 new of 87 matched" bug)
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_new_counts_gate_on_run_date_and_lead_the_prompt() -> None:
    user = User.objects.create_user("fresh-first", password="x")
    _watch(user, ["conferences"])
    _score(
        user,
        _content(ContentItem.Type.CONFERENCE, "Fresh Conf"),
        rank=1,
        is_new=True,
        first_seen=TODAY,
    )
    _score(
        user,
        _content(ContentItem.Type.CONFERENCE, "Old Conf A"),
        rank=2,
        first_seen=OLD_SEEN,
    )
    _score(
        user,
        _content(ContentItem.Type.CONFERENCE, "Old Conf B"),
        rank=3,
        first_seen=OLD_SEEN,
    )

    calls: list[tuple[str, str]] = []

    def fake_complete(system: str, user_prompt: str) -> str:
        calls.append((system, user_prompt))
        return "ok" if _is_summary(system) else "**Conf** — fits you."

    briefing = generate_briefing_for_user(user, complete=fake_complete)

    assert briefing.counts == {"conferences": 3}
    assert briefing.new_counts == {"conferences": 1}
    # The editor is told the new/total split, not just a raw total.
    summary_prompts = [u for s, u in calls if _is_summary(s)]
    assert summary_prompts
    assert "Conferences: 1 new, 3 matched in total" in summary_prompts[0]


@pytest.mark.django_db
def test_accumulated_older_items_are_not_re_announced_as_new() -> None:
    """Regression: the daily report re-announced the same set as "new" for a week.

    Every fellowship row is stamped ``is_new=True`` at scoring time and (being
    effectively never pruned) piles up. The old gate counted the whole 7-day pin
    window, so a one-time bulk import read "78 new" every day until the pins
    expired. Now only a row first seen *on the run date* counts as new, so an
    accumulated feed is announced once, the day it arrives — never re-announced.
    """
    user = User.objects.create_user("stale", password="x")
    _watch(user, ["fellowships"])
    # Still inside its week-long feed pin window (pinned_until in the future) yet
    # first seen days ago: the feed still badges it "New", but the daily report
    # must not re-announce it — this is exactly the case the old gate got wrong.
    _score(
        user,
        _content(ContentItem.Type.FELLOWSHIP, "Seen Days Ago"),
        rank=1,
        is_new=True,
        first_seen=OLD_SEEN,
        pinned_until="2999-01-01",
    )
    _score(
        user,
        _content(ContentItem.Type.FELLOWSHIP, "No First Seen"),
        rank=2,
        is_new=True,
    )
    _score(
        user,
        _content(ContentItem.Type.FELLOWSHIP, "Surfaced Today"),
        rank=3,
        is_new=True,
        first_seen=TODAY,
    )

    briefing = generate_briefing_for_user(user, complete=_llm("body"))

    assert briefing.counts == {"fellowships": 3}
    assert briefing.new_counts == {"fellowships": 1}  # not 3
    # The showcase's per-item "new" flag is gated the same way.
    flags = {i["title"]: i["is_new"] for i in briefing.showcase["fellowships"]}
    assert flags == {
        "Seen Days Ago": False,
        "No First Seen": False,
        "Surfaced Today": True,
    }


# --------------------------------------------------------------------------- #
# Fallback
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_fallback_summary_leads_with_new_counts() -> None:
    user = User.objects.create_user("fb-new", password="x")
    _watch(user, ["conferences"])
    _score(
        user,
        _content(ContentItem.Type.CONFERENCE, "Fresh Conf"),
        rank=1,
        is_new=True,
        first_seen=TODAY,
    )
    _score(
        user,
        _content(ContentItem.Type.CONFERENCE, "Old Conf"),
        rank=2,
        first_seen=OLD_SEEN,
    )

    briefing = generate_briefing_for_user(user, complete=lambda s, u: None)

    assert briefing.origin == DailyBriefing.Origin.FALLBACK
    assert "1 new conference (2 matched in total)" in briefing.body


@pytest.mark.django_db
def test_fallback_when_llm_returns_nothing_still_grounds_items() -> None:
    user = User.objects.create_user("fb", password="x")
    _watch(user, ["papers"])
    _score(user, _content(ContentItem.Type.PAPER, "Solo"), rank=1, match=84)

    briefing = generate_briefing_for_user(user, complete=lambda s, u: None)

    assert briefing.origin == DailyBriefing.Origin.FALLBACK
    assert "1 paper" in briefing.body  # summary fallback
    assert "Solo" in briefing.body  # section fallback names the real item


@pytest.mark.django_db
def test_fallback_when_llm_raises() -> None:
    user = User.objects.create_user("boom", password="x")
    _watch(user, ["papers"])
    _score(user, _content(ContentItem.Type.PAPER, "Solo"), rank=1)

    def raises(system: str, user_prompt: str) -> str:
        raise RuntimeError("endpoint down")

    briefing = generate_briefing_for_user(user, complete=raises)
    assert briefing.origin == DailyBriefing.Origin.FALLBACK
    assert briefing.body
    assert "## Papers" in briefing.body


@pytest.mark.django_db
def test_empty_day_writes_honest_fallback_without_calling_model() -> None:
    user = User.objects.create_user("empty", password="x")
    _watch(user, ["papers", "grants"])

    def boom(system: str, user_prompt: str) -> str:
        raise AssertionError("the model must not be called on an empty day")

    briefing = generate_briefing_for_user(user, complete=boom)

    assert briefing.origin == DailyBriefing.Origin.FALLBACK
    assert briefing.counts == {"papers": 0, "grants": 0}
    assert "No new research" in briefing.body


@pytest.mark.django_db
def test_regeneration_replaces_in_place() -> None:
    user = User.objects.create_user("again", password="x")
    _watch(user, ["papers"])
    _score(user, _content(ContentItem.Type.PAPER, "One"), rank=1)

    generate_briefing_for_user(user, complete=_llm("first body"))
    generate_briefing_for_user(user, complete=_llm("second body"))

    assert DailyBriefing.objects.filter(user=user).count() == 1
    body = DailyBriefing.objects.get(user=user).body
    assert "second body" in body
    assert "first body" not in body


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
        "generated_on": None,
        "categories": [],
        "counts": {},
        "new_counts": {},
        "showcase": {},
        "briefing": None,
    }


@pytest.mark.django_db
def test_api_returns_own_briefing_shape(client: APIClient) -> None:
    user = User.objects.create_user("owner", password="x")
    _watch(user, ["papers"])
    _score(user, _content(ContentItem.Type.PAPER, "Mine"), rank=1, match=90)
    generate_briefing_for_user(user, complete=_llm("hello body"))

    client.force_authenticate(user)
    resp = client.get("/api/daily-briefing/")

    assert resp.status_code == 200
    assert resp.data["generated_at"] is not None
    assert resp.data["categories"] == ["papers"]
    assert resp.data["counts"] == {"papers": 1}
    assert resp.data["new_counts"] == {"papers": 0}
    assert resp.data["briefing"]["origin"] == "llm"
    assert "hello body" in resp.data["briefing"]["body"]
    assert resp.data["showcase"]["papers"][0]["title"] == "Mine"


@pytest.mark.django_db
def test_api_returns_only_the_callers_briefing(client: APIClient) -> None:
    me = User.objects.create_user("me", password="x")
    them = User.objects.create_user("them", password="x")
    _watch(them, ["papers"])
    _score(them, _content(ContentItem.Type.PAPER, "Theirs"), rank=1)
    generate_briefing_for_user(them, complete=_llm("theirs body"))

    client.force_authenticate(me)
    resp = client.get("/api/daily-briefing/")

    assert resp.data["briefing"] is None  # me has no briefing; can't see theirs
