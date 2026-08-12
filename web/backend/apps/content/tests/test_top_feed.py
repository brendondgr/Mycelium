"""The Top-25 slate: membership, the entrant diff, and retirement.

The slate is what the daily report shows and what "new" means. These pin the two
properties that decide whether a report is worth reading: an item is announced when
it *enters* the slate (not when it is ingested), and it is announced once.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from apps.content import top_feed
from apps.content.models import ContentItem, RelevanceScore
from apps.content.opportunities import _persist as persist_opportunities
from apps.content.pipeline import _persist as persist_papers


def _grant(external_id: str, title: str) -> ContentItem:
    return ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="pivot",
        external_id=external_id,
        metadata={"title": title},
    )


def _suggestion(item: ContentItem, rank: int) -> dict:
    return {
        "content_id": str(item.id),
        "rank": rank,
        "headline": item.metadata["title"],
        "reason": "because",
        "match_percent": None,
        "source": "fallback",
    }


def _run(user: User, items: list[ContentItem], *, today: str, retire=False) -> None:
    """Persist one run's ranking for ``user`` — ``items`` best first."""
    suggestions = [_suggestion(item, n) for n, item in enumerate(items, start=1)]
    persist_opportunities(
        {"target_user": user},
        ContentItem.Type.GRANT,
        [(item, 1.0 - n / 100, {}) for n, item in enumerate(items)],
        suggestions,
        {s["content_id"] for s in suggestions},
        {},
        today=today,
        retire_missing=retire,
    )


def _signals(user: User, item: ContentItem) -> dict:
    return RelevanceScore.objects.get(target_user=user, content=item).signals


@pytest.mark.django_db
def test_first_run_makes_the_whole_slate_new():
    """A target's first report is all new — none of it has been shown before."""
    user = User.objects.create_user("first", password="x")
    items = [_grant(f"g{n}", f"Grant {n}") for n in range(3)]

    _run(user, items, today="2026-08-12")

    for rank, item in enumerate(items, start=1):
        signals = _signals(user, item)
        assert signals["top_rank"] == rank
        assert signals["is_new_top"] is True
        assert signals["entered_top_on"] == "2026-08-12"


@pytest.mark.django_db
def test_an_unchanged_slate_announces_nothing_the_next_day():
    """Re-running over the same corpus reports nothing new — the report holds still.

    This is the failure the change exists to fix: the same items were re-announced
    as new every morning because newness was read off the ingest date.
    """
    user = User.objects.create_user("steady", password="x")
    items = [_grant(f"g{n}", f"Grant {n}") for n in range(3)]

    _run(user, items, today="2026-08-12")
    _run(user, items, today="2026-08-13")

    for item in items:
        signals = _signals(user, item)
        assert signals["is_new_top"] is False
        # And the date still answers "when did this first appear in your report".
        assert signals["entered_top_on"] == "2026-08-12"


@pytest.mark.django_db
def test_promotion_into_the_slate_is_what_counts_as_new():
    """An item that climbs into the Top-N is new; the ones already there are not."""
    user = User.objects.create_user("promoted", password="x")
    settled = [_grant(f"g{n}", f"Grant {n}") for n in range(top_feed.top_n())]
    climber = _grant("climber", "Climber Grant")

    _run(user, settled, today="2026-08-12")
    # A profile edit re-ranks: the climber displaces the weakest settled item.
    _run(user, [climber, *settled[:-1], settled[-1]], today="2026-08-13")

    assert _signals(user, climber)["is_new_top"] is True
    assert _signals(user, climber)["entered_top_on"] == "2026-08-13"
    assert _signals(user, settled[0])["is_new_top"] is False
    # The one pushed out keeps its verdict but is no longer in the slate.
    dropped = _signals(user, settled[-1])
    assert "top_rank" not in dropped
    assert dropped["entered_top_on"] == ""


@pytest.mark.django_db
def test_re_entry_after_dropping_out_is_new_again():
    """An item the reader stopped seeing is news again when it comes back."""
    user = User.objects.create_user("returner", password="x")
    a, b = _grant("a", "Grant A"), _grant("b", "Grant B")

    _run(user, [a, b], today="2026-08-12")
    _run(user, [a], today="2026-08-13", retire=True)  # b falls out
    _run(user, [a, b], today="2026-08-14", retire=True)  # …and returns

    signals = _signals(user, b)
    assert signals["is_new_top"] is True
    assert signals["entered_top_on"] == "2026-08-14"


@pytest.mark.django_db
def test_items_below_the_slate_carry_no_rank():
    user = User.objects.create_user("deep", password="x")
    items = [_grant(f"g{n}", f"Grant {n}") for n in range(top_feed.top_n() + 3)]

    _run(user, items, today="2026-08-12")

    assert "top_rank" not in _signals(user, items[top_feed.top_n()])
    assert _signals(user, items[top_feed.top_n()])["is_new_top"] is False
    assert _signals(user, items[top_feed.top_n() - 1])["top_rank"] == top_feed.top_n()


@pytest.mark.django_db
def test_retiring_keeps_the_verdict_it_already_paid_for():
    """A dropped-out row leaves the feed but keeps its write-up, so re-entry is free."""
    user = User.objects.create_user("retire", password="x")
    a, b = _grant("a", "Grant A"), _grant("b", "Grant B")

    suggestions = [_suggestion(a, 1), _suggestion(b, 2)]
    suggestions[1].update(source="llm", match_percent=88, reason="A real write-up.")
    persist_opportunities(
        {"target_user": user},
        ContentItem.Type.GRANT,
        [(a, 0.9, {}), (b, 0.8, {})],
        suggestions,
        {s["content_id"] for s in suggestions},
        {},
        today="2026-08-12",
    )
    _run(user, [a], today="2026-08-13", retire=True)

    signals = _signals(user, b)
    assert signals["suggested"] is False
    assert "top_rank" not in signals
    assert signals["reason"] == "A real write-up."
    assert signals["source"] == "llm"


@pytest.mark.django_db
def test_papers_record_the_slate_too():
    """The paper pipeline maintains the same slate signals — one report, one rule."""
    user = User.objects.create_user("papers", password="x")
    papers = [
        ContentItem.objects.create(
            type=ContentItem.Type.PAPER,
            source=f"p{n}",
            external_id=f"p{n}",
            metadata={"title": f"Paper {n}"},
        )
        for n in range(3)
    ]
    suggestions = [_suggestion(p, n) for n, p in enumerate(papers, start=1)]

    persist_papers(
        {"target_user": user},
        ContentItem.Type.PAPER,
        [(p, 1.0 - n / 10, {}) for n, p in enumerate(papers)],
        suggestions,
        {s["content_id"] for s in suggestions},
        today="2026-08-12",
    )

    assert _signals(user, papers[0])["top_rank"] == 1
    assert _signals(user, papers[0])["is_new_top"] is True


@pytest.mark.django_db
def test_is_entrant_reads_the_run_date():
    assert top_feed.is_entrant({"entered_top_on": "2026-08-12"}, "2026-08-12") is True
    assert top_feed.is_entrant({"entered_top_on": "2026-08-11"}, "2026-08-12") is False
    assert top_feed.is_entrant({}, "2026-08-12") is False
    # A datetime written by an older build still compares by its date part.
    assert (
        top_feed.is_entrant({"entered_top_on": "2026-08-12T04:00:00Z"}, "2026-08-12")
        is True
    )
