"""The daily report: sectioned markdown synthesis, the freshness gate, fallback,
and the API."""

import pytest
from apps.accounts.models import WatchPreference
from apps.billing.testing import entitle_user
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from tools.delivery.briefing import CATEGORY_TYPES, generate_briefing_for_user
from tools.delivery.models import DailyBriefing
from tools.recommendation.models import RelevanceScore
from tools.retrieval.models import ContentItem

RUN = "2026-07-11T06:00:00"

# The report shows a reader's slate and calls new whatever entered it on the run
# date. ``today`` is the actual run date (no time is frozen), so a row that entered
# today is news and one that entered earlier is simply still on the page.
TODAY = timezone.now().date().isoformat()
OLD_SEEN = "2026-07-01T00:00:00"  # first ingested well before any test run

#: The implicit cluster every profile with no declared themes falls into.
CLUSTER = "c-all"

#: Signals for a row the reader was *already* being shown before today's run.
def settled(rank: int) -> dict:
    """Slate signals for a row that entered before today — standing, not news."""
    return {
        "entered_top_on": OLD_SEEN[:10],
        "is_new_top": False,
        "cluster_slates": {
            CLUSTER: {
                "label": "",
                "rank": rank,
                "entered_on": OLD_SEEN[:10],
                "is_new": False,
            }
        },
    }


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
    """A row the report shows by default: in the reader's slate, and new to it.

    The report shows a target's slate (``briefing.report_scores``) and calls new
    whatever entered it on the run date, so the defaults here put the row at
    ``top_rank`` = ``rank`` having entered today. A test about an item that is
    *already* being shown overrides ``entered_top_on`` / ``is_new_top``; one about an
    item outside the slate passes ``top_rank=None``.
    """
    title = content.metadata["title"]
    signals = {
        "suggested": suggested,
        "run_at": run_at,
        "rank": rank,
        "headline": f"Headline {title}",
        "reason": f"Why {title} fits you.",
        "verdict": "read",
        "caveat": f"Caveat for {title}.",
        "first_seen": TODAY,
        "embedding_match": 0.8,
        "top_rank": rank,
        "entered_top_on": TODAY,
        "is_new_top": True,
        **extra_signals,
    }
    if signals.get("top_rank") is None:
        signals.pop("top_rank")
        signals["entered_top_on"] = ""
        signals["is_new_top"] = False
    else:
        # The report reads per-theme slates now, so a row that is "in the slate"
        # has to say which theme's. These fixtures declare no clusters, so it is
        # the single implicit grouping every unclustered profile falls into.
        signals.setdefault(
            "cluster_slates",
            {
                CLUSTER: {
                    "label": "",
                    "rank": rank,
                    "entered_on": signals["entered_top_on"],
                    "is_new": signals["is_new_top"],
                }
            },
        )
        signals.setdefault(
            "writeups",
            {
                CLUSTER: {
                    "verdict": "read",
                    "beats": [f"Why {title} fits you."],
                    "caveat": f"Caveat for {title}.",
                    "bridge_note": "",
                    "source": "llm",
                }
            },
        )
    return RelevanceScore.objects.create(
        content=content, target_user=user, score=0.8, signals=signals
    )


def _watch(user, categories) -> None:
    WatchPreference.objects.create(user=user, categories=categories)


def _llm(text: str):
    """A stub completion (2-arg agent seam) that returns ``text`` for every agent."""
    return lambda system, user: text


def _is_summary(system: str) -> bool:
    """The lead editor's system prompt, told apart from the per-theme reads."""
    return "opening paragraph" in system


# --------------------------------------------------------------------------- #
# Synthesis
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_llm_report_is_theme_organised_and_counts_are_correct() -> None:
    user = User.objects.create_user("bre", password="x")
    entitle_user(user)
    _watch(user, ["papers", "grants"])
    _score(user, _content(ContentItem.Type.PAPER, "Paper A"), rank=1)
    _score(user, _content(ContentItem.Type.PAPER, "Paper B"), rank=2)
    _score(
        user,
        _content(ContentItem.Type.GRANT, "Grant X"),
        rank=1,
        deadline_date="2026-08-01",
    )

    calls: list[tuple[str, str]] = []

    def fake_complete(system: str, user_prompt: str) -> str:
        calls.append((system, user_prompt))
        if _is_summary(system):
            return "Start with the imaging grant."
        return "Today's papers converge on the same evaluation gap."

    briefing = generate_briefing_for_user(user, complete=fake_complete)

    assert briefing.origin == DailyBriefing.Origin.LLM
    # The lead paragraph opens the body; the theme section follows, and the
    # category listings sit inside it.
    assert briefing.body.startswith("Start with the imaging grant.")
    assert "## Your research" in briefing.body
    assert "### Papers" in briefing.body
    assert "### Grants" in briefing.body
    assert briefing.counts == {"papers": 2, "grants": 1}
    assert briefing.categories == ["papers", "grants"]
    # Showcase (UI grounding) still tracks the top items per area.
    assert [i["title"] for i in briefing.showcase["papers"]] == ["Paper A", "Paper B"]
    assert briefing.showcase["grants"][0]["deadline_date"] == "2026-08-01"
    # Grounding: the theme read is shown the real items, and never invents one.
    assert any("Paper A" in u for _s, u in calls)
    assert any("Grant X" in u for _s, u in calls)
    # The prose is stored as structure, so the PDF and the app read it back rather
    # than re-billing the model for the same paragraph.
    assert briefing.narrative["lead"] == "Start with the imaging grant."
    assert briefing.narrative["themes"][0]["read"].startswith("Today's papers")
    # No percentage survives anywhere in the document.
    assert "% match" not in briefing.body
    # The summary table's Personal row agrees with the sections above it.
    assert briefing.project_summary[0] == {
        "key": "personal",
        "label": "Personal",
        "kind": "personal",
        "scope": "",
        "counts": {"papers": 2, "grants": 1},
    }


@pytest.mark.django_db
def test_an_unentitled_reader_gets_the_same_document_without_the_prose() -> None:
    """The deterministic report is the baseline product, not a degraded one."""
    user = User.objects.create_user("free", password="x")
    _watch(user, ["papers"])
    _score(user, _content(ContentItem.Type.PAPER, "Paper A"), rank=1)

    calls: list[str] = []

    def fake_complete(system: str, user_prompt: str) -> str:
        calls.append(system)
        return "Should never be reached."

    briefing = generate_briefing_for_user(user, complete=fake_complete)

    assert calls == []  # gated before the prompt, not after
    assert briefing.origin == DailyBriefing.Origin.FALLBACK
    assert briefing.narrative == {}
    # Same shape, same sections, same navigation — quieter, not broken.
    assert "## Your research" in briefing.body
    assert "### Papers" in briefing.body
    assert "Paper A" in briefing.body


@pytest.mark.django_db
def test_category_gating_excludes_unwatched_categories() -> None:
    user = User.objects.create_user("gate", password="x")
    _watch(user, ["papers"])  # grants NOT watched
    _score(user, _content(ContentItem.Type.PAPER, "Kept"), rank=1)
    _score(user, _content(ContentItem.Type.GRANT, "Hidden"), rank=1)

    briefing = generate_briefing_for_user(user, complete=_llm("body"))

    assert set(briefing.counts) == {"papers"}
    assert "grants" not in briefing.showcase
    assert "### Papers" in briefing.body
    assert "### Grants" not in briefing.body


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
    assert "### Papers" in briefing.body


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
# What counts as new: entering the slate, not arriving in the corpus
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_new_counts_are_slate_entrants_and_only_they_are_written_up() -> None:
    user = User.objects.create_user("fresh-first", password="x")
    entitle_user(user)
    _watch(user, ["conferences"])
    _score(
        user,
        _content(ContentItem.Type.CONFERENCE, "Fresh Conf"),
        rank=1,
    )
    _score(
        user,
        _content(ContentItem.Type.CONFERENCE, "Old Conf A"),
        rank=2,
        **settled(2),
    )
    _score(
        user,
        _content(ContentItem.Type.CONFERENCE, "Old Conf B"),
        rank=3,
        **settled(3),
    )

    calls: list[tuple[str, str]] = []

    def fake_complete(system: str, user_prompt: str) -> str:
        calls.append((system, user_prompt))
        return "ok" if _is_summary(system) else "**Conf** — fits you."

    briefing = generate_briefing_for_user(user, complete=fake_complete)

    assert briefing.counts == {"conferences": 3}
    assert briefing.new_counts == {"conferences": 1}
    # The theme read details only what is new: the two standing calls are in the
    # reference block, not in the prompt that writes about the day's news.
    theme_prompts = [u for sys, u in calls if not _is_summary(sys)]
    assert theme_prompts
    assert "Fresh Conf" in theme_prompts[0]
    assert "Old Conf A" not in theme_prompts[0]


@pytest.mark.django_db
def test_a_standing_slate_member_is_not_re_announced() -> None:
    """Regression: the report re-announced the same items as new every morning.

    Every fellowship row is stamped ``is_new=True`` at scoring time and, being
    effectively never pruned, piles up — so any rule keyed on arrival re-announces a
    one-time bulk import for as long as it lingers. An item is news when it *enters*
    the reader's slate; after that it is simply still on their page, however recently
    it happened to reach the store.
    """
    user = User.objects.create_user("stale", password="x")
    _watch(user, ["fellowships"])
    # Ingested today and still inside its week-long feed pin window, but the reader
    # has been shown it since last week: not news.
    _score(
        user,
        _content(ContentItem.Type.FELLOWSHIP, "Already Showing"),
        rank=1,
        is_new=True,
        first_seen=TODAY,
        pinned_until="2999-01-01",
        **settled(1),
    )
    _score(
        user,
        _content(ContentItem.Type.FELLOWSHIP, "Also Showing"),
        rank=2,
        is_new=True,
        first_seen=OLD_SEEN,
        **settled(2),
    )
    # Ingested weeks ago; promoted into the slate only now — that is the news.
    _score(
        user,
        _content(ContentItem.Type.FELLOWSHIP, "Just Promoted"),
        rank=3,
        is_new=False,
        first_seen=OLD_SEEN,
    )

    briefing = generate_briefing_for_user(user, complete=_llm("body"))

    assert briefing.counts == {"fellowships": 3}
    assert briefing.new_counts == {"fellowships": 1}  # not 3
    # The showcase's per-item entrant flag agrees.
    flags = {i["title"]: i["is_entrant"] for i in briefing.showcase["fellowships"]}
    assert flags == {
        "Already Showing": False,
        "Also Showing": False,
        "Just Promoted": True,
    }


# --------------------------------------------------------------------------- #
# Fallback
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_quiet_theme_is_one_line_not_a_section() -> None:
    user = User.objects.create_user("fb-new", password="x")
    _watch(user, ["conferences"])
    _score(user, _content(ContentItem.Type.CONFERENCE, "Fresh Conf"), rank=1)
    _score(
        user,
        _content(ContentItem.Type.CONFERENCE, "Old Conf"),
        rank=2,
        **settled(2),
    )

    briefing = generate_briefing_for_user(user, complete=lambda s, u: None)

    assert briefing.origin == DailyBriefing.Origin.FALLBACK
    # The entrant leads its theme; the settled one is a reference row with no
    # commentary, under a header that says plainly what it is.
    assert "Fresh Conf" in briefing.body
    assert "Currently in your list" in briefing.body
    assert briefing.body.index("Fresh Conf") < briefing.body.index("Old Conf")


@pytest.mark.django_db
def test_fallback_when_llm_returns_nothing_still_grounds_items() -> None:
    user = User.objects.create_user("fb", password="x")
    _watch(user, ["papers"])
    _score(user, _content(ContentItem.Type.PAPER, "Solo"), rank=1)

    briefing = generate_briefing_for_user(user, complete=lambda s, u: None)

    assert briefing.origin == DailyBriefing.Origin.FALLBACK
    assert "Solo" in briefing.body  # the listing names the real item


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
    assert "### Papers" in briefing.body


@pytest.mark.django_db
def test_empty_day_writes_honest_fallback_without_calling_model() -> None:
    user = User.objects.create_user("empty", password="x")
    _watch(user, ["papers", "grants"])

    def boom(system: str, user_prompt: str) -> str:
        raise AssertionError("the model must not be called on an empty day")

    briefing = generate_briefing_for_user(user, complete=boom)

    assert briefing.origin == DailyBriefing.Origin.FALLBACK
    assert briefing.counts == {"papers": 0, "grants": 0}
    assert "Nothing has reached your top list yet" in briefing.body


@pytest.mark.django_db
def test_regeneration_replaces_in_place() -> None:
    user = User.objects.create_user("again", password="x")
    _watch(user, ["papers"])
    entitle_user(user)
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
        "project_summary": [],
        # Statistics are absent, not zero: a client must render "no numbers"
        # rather than "Mylo found nothing", which are different claims.
        "stats": {},
        "kind": "daily",
        "briefing": None,
    }


@pytest.mark.django_db
def test_api_returns_own_briefing_shape(client: APIClient) -> None:
    user = User.objects.create_user("owner", password="x")
    entitle_user(user)
    _watch(user, ["papers"])
    _score(user, _content(ContentItem.Type.PAPER, "Mine"), rank=1)
    generate_briefing_for_user(user, complete=_llm("hello body"))

    client.force_authenticate(user)
    resp = client.get("/api/daily-briefing/")

    assert resp.status_code == 200
    assert resp.data["generated_at"] is not None
    assert resp.data["categories"] == ["papers"]
    assert resp.data["counts"] == {"papers": 1}
    assert resp.data["new_counts"] == {"papers": 1}
    assert resp.data["briefing"]["origin"] == "llm"
    assert "hello body" in resp.data["briefing"]["body"]
    assert resp.data["showcase"]["papers"][0]["title"] == "Mine"
    # The report's summary table travels with the envelope (no projects here, so
    # the Personal row is the whole table).
    assert resp.data["project_summary"] == [
        {
            "key": "personal",
            "label": "Personal",
            "kind": "personal",
            "scope": "",
            "counts": {"papers": 1},
        }
    ]


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
