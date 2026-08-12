"""The report is project-aware, and narrow: new today, and relevant enough.

Two things are asserted here that the rest of the briefing tests take for granted:

* **Which projects a report covers.** A person's report covers the projects that
  are theirs — one they own outright, and a lab project a PI assigned them to —
  and nobody else's. A lab's report covers the lab's own projects.
* **What may appear at all.** A feed accumulates; the report does not. A row has to
  have first surfaced on the run date *and* clear the relevance floor, and when
  nothing does, the report says so instead of padding itself out.
"""

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.accounts.models import Lab, LabMembership, WatchPreference
from apps.content.briefing import (
    generate_briefing_for_lab,
    generate_briefing_for_user,
    report_projects_for_user,
)
from apps.content.models import ContentItem, RelevanceScore
from apps.research.models import Project, ProjectMember

RUN = "2026-07-11T06:00:00"
TODAY = timezone.now().date().isoformat()
OLD_SEEN = "2026-07-01T00:00:00"


def _content(ctype: str, title: str) -> ContentItem:
    return ContentItem.objects.create(
        type=ctype,
        source="test",
        external_id=title,
        source_url="https://example.org/x",
        metadata={"title": title},
    )


def _score(target: dict, content: ContentItem, *, match=0.8, first_seen=TODAY, **extra):
    signals = {
        "suggested": True,
        "run_at": RUN,
        "rank": 1,
        "headline": f"Headline {content.metadata['title']}",
        "reason": f"Why {content.metadata['title']} fits.",
        "match_percent": 85,
        "embedding_match": match,
        "first_seen": first_seen,
        **extra,
    }
    return RelevanceScore.objects.create(
        content=content, score=0.8, signals=signals, **target
    )


def _rows(briefing) -> dict[str, dict]:
    return {row["label"]: row for row in briefing.project_summary}


@pytest.fixture
def reader(db) -> User:
    user = User.objects.create_user("reader", password="x")
    WatchPreference.objects.create(user=user, categories=["papers", "grants"])
    return user


# --------------------------------------------------------------------------- #
# Which projects a report covers
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_report_covers_owned_and_assigned_projects(reader: User) -> None:
    """Both ways a project is yours: you own it, or a PI put you on the lab's."""
    lab = Lab.objects.create(name="Reyes Lab", slug="reyes-lab")
    LabMembership.objects.create(user=reader, lab=lab)
    mine = Project.objects.create(scope_user=reader, name="Solo Study")
    assigned = Project.objects.create(scope_lab=lab, name="Lab Study")
    ProjectMember.objects.create(project=assigned, user=reader)
    Project.objects.create(scope_lab=lab, name="Someone Else's")

    assert [p.name for p in report_projects_for_user(reader)] == [
        "Lab Study",
        "Solo Study",
    ]

    _score({"target_project": mine}, _content(ContentItem.Type.PAPER, "Solo Paper"))
    _score({"target_project": assigned}, _content(ContentItem.Type.GRANT, "Lab Grant"))

    briefing = generate_briefing_for_user(reader, complete=lambda _s, _u: None)

    assert set(_rows(briefing)) == {"Personal", "Solo Study", "Lab Study"}
    assert _rows(briefing)["Solo Study"]["counts"] == {"papers": 1, "grants": 0}
    assert _rows(briefing)["Lab Study"]["counts"] == {"papers": 0, "grants": 1}
    assert "## Project · Solo Study" in briefing.body
    assert "Solo Paper" in briefing.body
    assert "Lab Grant" in briefing.body


@pytest.mark.django_db
def test_an_archived_project_is_left_out(reader: User) -> None:
    """Archiving stops new work, so an archived project can only ever read empty."""
    Project.objects.create(scope_user=reader, name="Shelved", is_archived=True)

    briefing = generate_briefing_for_user(reader, complete=lambda _s, _u: None)

    assert set(_rows(briefing)) == {"Personal"}


@pytest.mark.django_db
def test_a_quiet_project_keeps_its_row_but_gets_no_section(reader: User) -> None:
    """"Nothing for this project today" is an answer; a bare heading is noise."""
    Project.objects.create(scope_user=reader, name="Quiet")

    briefing = generate_briefing_for_user(reader, complete=lambda _s, _u: None)

    assert _rows(briefing)["Quiet"]["counts"] == {"papers": 0, "grants": 0}
    assert "## Project · Quiet" not in briefing.body


@pytest.mark.django_db
def test_a_labs_report_covers_the_labs_projects() -> None:
    lab = Lab.objects.create(name="Reyes Lab", slug="reyes-lab")
    project = Project.objects.create(scope_lab=lab, name="Reef Atlas")
    _score({"target_project": project}, _content(ContentItem.Type.PAPER, "Reef Paper"))

    briefing = generate_briefing_for_lab(lab, complete=lambda _s, _u: None)

    assert _rows(briefing)["Reef Atlas"]["counts"]["papers"] == 1
    assert "## Project · Reef Atlas" in briefing.body
    assert "Reef Paper" in briefing.body


# --------------------------------------------------------------------------- #
# What may appear at all
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_weak_match_never_reaches_the_report(reader: User) -> None:
    """Below the floor an item is left for search, not pushed into the report."""
    _score(
        {"target_user": reader},
        _content(ContentItem.Type.PAPER, "Strong"),
        match=0.71,
    )
    _score(
        {"target_user": reader},
        _content(ContentItem.Type.PAPER, "Weak"),
        match=0.51,
    )

    briefing = generate_briefing_for_user(reader, complete=lambda _s, _u: None)

    assert _rows(briefing)["Personal"]["counts"]["papers"] == 1
    assert "Strong" in briefing.body
    assert "Weak" not in briefing.body
    # The feed-level counts are untouched — the Daily page's summary zone links
    # straight to those pages, and both papers really are in the feed.
    assert briefing.counts["papers"] == 2


@pytest.mark.django_db
def test_a_row_with_no_relevance_signal_is_left_out(reader: User) -> None:
    """Nothing to judge relevance by is not the same as passing the bar."""
    score = _score({"target_user": reader}, _content(ContentItem.Type.PAPER, "Blind"))
    score.signals.pop("embedding_match")
    score.signals.pop("match_percent")
    score.save(update_fields=["signals"])

    briefing = generate_briefing_for_user(reader, complete=lambda _s, _u: None)

    assert _rows(briefing)["Personal"]["counts"]["papers"] == 0
    assert "Blind" not in briefing.body


@pytest.mark.django_db
def test_a_row_without_an_embedding_falls_back_to_its_match_percent(
    reader: User,
) -> None:
    """A rule-matched fellowship still has a judgement to stand on."""
    paper = _content(ContentItem.Type.PAPER, "Rule Kept")
    kept = _score({"target_user": reader}, paper)
    kept.signals.pop("embedding_match")
    kept.signals["match_percent"] = 90
    kept.save(update_fields=["signals"])
    dropped = _score(
        {"target_user": reader}, _content(ContentItem.Type.PAPER, "Rule Dropped")
    )
    dropped.signals.pop("embedding_match")
    dropped.signals["match_percent"] = 61
    dropped.save(update_fields=["signals"])

    briefing = generate_briefing_for_user(reader, complete=lambda _s, _u: None)

    assert "Rule Kept" in briefing.body
    assert "Rule Dropped" not in briefing.body


@pytest.mark.django_db
def test_yesterdays_backlog_is_not_re_announced(reader: User) -> None:
    _score(
        {"target_user": reader},
        _content(ContentItem.Type.GRANT, "Standing Grant"),
        first_seen=OLD_SEEN,
    )

    briefing = generate_briefing_for_user(reader, complete=lambda _s, _u: None)

    assert _rows(briefing)["Personal"]["counts"]["grants"] == 0
    assert "Standing Grant" not in briefing.body


@pytest.mark.django_db
def test_a_day_where_nothing_clears_the_bar_says_so(reader: User) -> None:
    """The alternative — relaxing the floor until the page fills — trains the
    reader to stop opening the report."""
    _score(
        {"target_user": reader},
        _content(ContentItem.Type.PAPER, "Marginal"),
        match=0.4,
    )

    def boom(_system: str, _user: str) -> str:
        raise AssertionError("the model must not be called on an empty day")

    briefing = generate_briefing_for_user(reader, complete=boom)

    assert "Nothing new cleared the relevance bar" in briefing.body
    assert "Marginal" not in briefing.body
