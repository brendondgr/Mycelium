"""The report is project-aware, and it is built from each part's Top-25 slate.

Two things are asserted here that the rest of the briefing tests take for granted:

* **Which projects a report covers.** A person's report covers the projects that
  are theirs — one they own outright, and a lab project a PI assigned them to —
  and nobody else's. A lab's report covers the lab's own projects.
* **What may appear at all.** A feed accumulates; the report shows the slate. A row
  has to be *in* the slate to appear, the summary table counts only what entered it
  on this run, and a day with no entrants carries yesterday's report forward rather
  than re-writing it to say the same thing.
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


def _score(
    target: dict,
    content: ContentItem,
    *,
    match=0.8,
    first_seen=TODAY,
    rank=1,
    entered_on=TODAY,
    **extra,
):
    """A row in the target's slate at ``rank``, entering on ``entered_on``.

    ``entered_on=None`` puts the row in the feed but outside the slate — the case
    the report must leave out.
    """
    signals = {
        "suggested": True,
        "run_at": RUN,
        "rank": rank,
        "headline": f"Headline {content.metadata['title']}",
        "reason": f"Why {content.metadata['title']} fits.",
        "match_percent": 85,
        "embedding_match": match,
        "first_seen": first_seen,
        **(
            {}
            if entered_on is None
            else {
                "top_rank": rank,
                "entered_top_on": entered_on,
                "is_new_top": entered_on == TODAY,
            }
        ),
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
    project = Project.objects.create(
        scope_lab=lab, name="Reef Atlas", share_in_lab_reports=True
    )
    _score({"target_project": project}, _content(ContentItem.Type.PAPER, "Reef Paper"))

    briefing = generate_briefing_for_lab(lab, complete=lambda _s, _u: None)

    assert _rows(briefing)["Reef Atlas"]["counts"]["papers"] == 1
    assert "## Project · Reef Atlas" in briefing.body
    assert "Reef Paper" in briefing.body


@pytest.mark.django_db
def test_lab_report_excludes_unshared_projects() -> None:
    """A lab surface shows only projects shared into it (plan 0.2, invariant 6).

    A lab report is read by every lab member and posted to the lab's channel, while
    ``Project.visible_to`` grants a lab project to its members and lab heads only.
    """
    lab = Lab.objects.create(name="Reyes Lab", slug="reyes-lab")
    shared = Project.objects.create(
        scope_lab=lab, name="Reef Atlas", share_in_lab_reports=True
    )
    private = Project.objects.create(scope_lab=lab, name="Unpublished Coral Genome")
    _score({"target_project": shared}, _content(ContentItem.Type.PAPER, "Reef Paper"))
    _score({"target_project": private}, _content(ContentItem.Type.PAPER, "Secret Paper"))

    briefing = generate_briefing_for_lab(lab, complete=lambda _s, _u: None)

    assert "Reef Atlas" in _rows(briefing)
    assert "Unpublished Coral Genome" not in _rows(briefing)
    assert "Unpublished Coral Genome" not in briefing.body
    assert "Secret Paper" not in briefing.body
    # Partial, and honest about it — a count, never a name.
    assert "1 private project not shown" in briefing.body


@pytest.mark.django_db
def test_lab_member_without_project_access_never_sees_project_part() -> None:
    """The private project still reaches its own member's personal report.

    Sharing governs the *lab's* surfaces. Scoping it to one reader is what
    ``report_projects_for_user`` already does, so a member loses nothing.
    """
    lab = Lab.objects.create(name="Reyes Lab", slug="reyes-lab")
    member = User.objects.create_user("member", password="x")
    WatchPreference.objects.create(user=member, categories=["papers"])
    LabMembership.objects.create(user=member, lab=lab)
    outsider = User.objects.create_user("outsider", password="x")
    WatchPreference.objects.create(user=outsider, categories=["papers"])
    LabMembership.objects.create(user=outsider, lab=lab)

    private = Project.objects.create(scope_lab=lab, name="Unpublished Coral Genome")
    ProjectMember.objects.create(project=private, user=member)
    _score({"target_project": private}, _content(ContentItem.Type.PAPER, "Secret Paper"))

    mine = generate_briefing_for_user(member, complete=lambda _s, _u: None)
    assert "Unpublished Coral Genome" in _rows(mine)
    assert "Secret Paper" in mine.body

    theirs = generate_briefing_for_user(outsider, complete=lambda _s, _u: None)
    assert "Unpublished Coral Genome" not in _rows(theirs)
    assert "Secret Paper" not in theirs.body

    lab_report = generate_briefing_for_lab(lab, complete=lambda _s, _u: None)
    assert "Unpublished Coral Genome" not in lab_report.body


# --------------------------------------------------------------------------- #
# What may appear at all
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_row_outside_the_slate_never_reaches_the_report(reader: User) -> None:
    """The feed can afford a long tail; a once-a-day report cannot."""
    _score({"target_user": reader}, _content(ContentItem.Type.PAPER, "In The Top"))
    _score(
        {"target_user": reader},
        _content(ContentItem.Type.PAPER, "Down The List"),
        entered_on=None,
    )

    briefing = generate_briefing_for_user(reader, complete=lambda _s, _u: None)

    assert _rows(briefing)["Personal"]["counts"]["papers"] == 1
    assert "In The Top" in briefing.body
    assert "Down The List" not in briefing.body
    # The feed-level counts are untouched — the Daily page's summary zone links
    # straight to those pages, and both papers really are in the feed.
    assert briefing.counts["papers"] == 2


@pytest.mark.django_db
def test_the_whole_slate_is_shown_and_only_entrants_are_counted(reader: User) -> None:
    """The reader keeps their best matches on the page; the table counts the change.

    Showing only the day's entrants was the old behaviour and it hid a reader's
    strongest matches behind whatever happened to have arrived.
    """
    _score(
        {"target_user": reader},
        _content(ContentItem.Type.PAPER, "Standing Best"),
        rank=1,
        entered_on=OLD_SEEN[:10],
    )
    _score(
        {"target_user": reader},
        _content(ContentItem.Type.PAPER, "Just Promoted"),
        rank=2,
    )

    briefing = generate_briefing_for_user(reader, complete=lambda _s, _u: None)

    assert _rows(briefing)["Personal"]["counts"]["papers"] == 1  # one entrant
    assert "Standing Best" in briefing.body  # …and both are on the page
    assert "Just Promoted" in briefing.body


@pytest.mark.django_db
def test_a_quiet_day_carries_yesterdays_report_forward(reader: User) -> None:
    """Nothing entered the top list, so the report is the same one as yesterday.

    Re-writing it would spend a model call to reach the same conclusions in
    different words, and cost the reader a full read to discover nothing changed.
    """
    from datetime import timedelta

    from apps.content.models import DailyBriefing

    DailyBriefing.objects.create(
        user=reader,
        generated_on=timezone.localdate() - timedelta(days=1),
        body="Yesterday's report, in full.",
        origin=DailyBriefing.Origin.LLM,
    )
    _score(
        {"target_user": reader},
        _content(ContentItem.Type.PAPER, "Standing Best"),
        entered_on=OLD_SEEN[:10],
    )

    def boom(_system: str, _user: str) -> str:
        raise AssertionError("the model must not be called when nothing entered")

    briefing = generate_briefing_for_user(reader, complete=boom)

    assert briefing.body == "Yesterday's report, in full."
    assert briefing.origin == DailyBriefing.Origin.CARRIED


@pytest.mark.django_db
def test_a_reader_with_no_report_yet_gets_an_honest_note(reader: User) -> None:
    """With nothing in the slate and no earlier report, say so — do not pad."""

    def boom(_system: str, _user: str) -> str:
        raise AssertionError("the model must not be called on an empty day")

    briefing = generate_briefing_for_user(reader, complete=boom)

    assert "Nothing has reached your top list yet" in briefing.body
